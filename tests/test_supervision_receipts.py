from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import managed_ollama
from runtime_support import atomic_json, fingerprint
from supervision_receipts import validate_receipt


def receipt():
    return {'schema_version': 1, 'ticket': 'attempt-one', 'command_sha256': 'a' * 64,
            'supervisor_pid': 1234, 'status': 'finished', 'exit_code': 75,
            'cleanup_confirmed': True, 'cleanup_scope': 'process_group'}


class ReceiptTests(unittest.TestCase):
    def check(self, value, **kwargs):
        return validate_receipt(value, ticket='attempt-one', command_sha256='a' * 64, **kwargs)

    def test_matching_attempt_preserves_pause_or_failure_and_does_not_mutate(self):
        for scope in ('process_group', 'windows_job'):
            for code in (0, 1, 7, 75, 130):
                value = {**receipt(), 'cleanup_scope': scope, 'exit_code': code}
                result = self.check(value, supervisor_pid=1234)
                self.assertEqual(result, value)
                self.assertIsNot(result, value)

    def test_missing_wrong_or_weakly_typed_fields_fail(self):
        for key in receipt():
            value = receipt(); value.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError):
                self.check(value)
        invalid = {'schema_version': [True, 2, '1'], 'ticket': ['', 'old-attempt', None],
                   'command_sha256': ['b' * 64, 'a' * 63], 'supervisor_pid': [0, -1, True, '1234'],
                   'status': ['running', 'cleanup_unconfirmed'], 'exit_code': [None, True, '0'],
                   'cleanup_confirmed': [False, 1, 'true'], 'cleanup_scope': ['pid_only', None]}
        for key, values in invalid.items():
            for invalid_value in values:
                with self.subTest(key=key, value=invalid_value), self.assertRaises(ValueError):
                    self.check({**receipt(), key: invalid_value})
        for value in (None, [], 'finished'):
            with self.assertRaises(ValueError): self.check(value)
        for pid in (True, 0, '1234', 9999):
            with self.assertRaises(ValueError): self.check(receipt(), supervisor_pid=pid)

    def test_request_identity_and_parent_are_still_checked_by_diagnostic_wrapper(self):
        from diagnostic_series import _confirmed_supervision
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'child.log'
            request = {'ticket': 'attempt-one', 'command_sha256': 'a' * 64,
                       'execution_fingerprint': 'expected-source', 'run_parent': 'bound-parent'}
            atomic_json(log.with_suffix('.supervision.request.json'), request)
            atomic_json(log.with_suffix('.supervision.json'), receipt())
            self.assertEqual(_confirmed_supervision(log, 'expected-source', 'bound-parent'), receipt())
            with self.assertRaises(ValueError): _confirmed_supervision(log, 'other-source', 'bound-parent')
            with self.assertRaises(ValueError): _confirmed_supervision(log, 'expected-source', 'other-parent')


class SupervisorFailureTests(unittest.TestCase):
    def harness(self, stack, popen):
        records = []
        def save(path, value): records.append(copy.deepcopy(value))
        stack.enter_context(patch('runtime_support.atomic_json', side_effect=save))
        stack.enter_context(patch.object(managed_ollama.subprocess, 'Popen', popen))
        stack.enter_context(patch.object(managed_ollama.threading, 'Thread'))
        job = Mock()
        stack.enter_context(patch('windows_process_job.SupervisorJob', return_value=job))
        stack.enter_context(patch.object(managed_ollama.os, 'killpg', side_effect=ProcessLookupError, create=True))
        return records, job

    def test_known_no_child_start_has_terminal_receipt_and_original_error(self):
        failure = FileNotFoundError('synthetic missing executable')
        with ExitStack() as stack:
            records, job = self.harness(stack, Mock(side_effect=failure))
            with self.assertRaises(FileNotFoundError) as caught:
                managed_ollama.supervise_command(['synthetic-missing'], 'receipt.json', 'attempt-one')
            self.assertIs(caught.exception, failure)
            terminal = records[-1]
            self.assertEqual(terminal['child_start'], 'not_started')
            self.assertNotIn('child_pid', terminal)
            self.assertNotEqual(terminal['exit_code'], 0)
            validate_receipt(terminal, ticket='attempt-one', command_sha256=fingerprint(['synthetic-missing']))

    def test_unknown_spawn_is_not_inferred_clean_without_tree_proof(self):
        failure = RuntimeError('unknown constructor state')
        with ExitStack() as stack:
            records, job = self.harness(stack, Mock(side_effect=failure))
            # Even Windows must withhold confirmation if its job cannot prove cleanup.
            if os.name == 'nt': job.stop_descendants.side_effect = RuntimeError('not confirmed')
            with self.assertRaises(RuntimeError) as caught:
                managed_ollama.supervise_command(['synthetic'], 'receipt.json', 'attempt-one')
            self.assertIs(caught.exception, failure)
            self.assertEqual(records[-1]['child_start'], 'unknown')
            self.assertIs(records[-1]['cleanup_confirmed'], False)
            with self.assertRaises(ValueError):
                validate_receipt(records[-1], ticket='attempt-one', command_sha256=fingerprint(['synthetic']))

    def test_running_receipt_write_failure_still_reaps_child(self):
        failure = OSError('synthetic receipt publication failure')
        child = Mock(pid=4567, returncode=0)
        with ExitStack() as stack:
            records, job = self.harness(stack, Mock(return_value=child))
            def save(path, value):
                records.append(copy.deepcopy(value))
                if value['status'] == 'running': raise failure
            stack.enter_context(patch('runtime_support.atomic_json', side_effect=save))
            with self.assertRaises(OSError) as caught:
                managed_ollama.supervise_command(['synthetic'], 'receipt.json', 'attempt-one')
            self.assertIs(caught.exception, failure)
            child.wait.assert_called()
            if os.name == 'nt': job.stop_descendants.assert_called_once()
            terminal = records[-1]
            self.assertEqual(terminal['exit_code'], 1)
            validate_receipt(terminal, ticket='attempt-one', command_sha256=fingerprint(['synthetic']))

    def test_initial_write_failure_does_not_start_child(self):
        failure = OSError('synthetic initial write failure')
        popen = Mock()
        with ExitStack() as stack:
            records, job = self.harness(stack, popen)
            stack.enter_context(patch('runtime_support.atomic_json', side_effect=failure))
            with self.assertRaises(OSError) as caught:
                managed_ollama.supervise_command(['synthetic'], 'receipt.json', 'attempt-one')
            self.assertIs(caught.exception, failure)
            popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
