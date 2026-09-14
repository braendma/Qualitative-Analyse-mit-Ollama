"""Live series status tests use synthetic counters only; no child inference."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import diagnostic_series as series
import progress_events
from progress_presentation import safe_series_progress
from runtime_support import atomic_json, fingerprint
from telegram_progress import format_progress


class SeriesProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.parent = self.root / 'repeat-001'
        self.run = self.parent / 'synthetic-run'
        self.run.mkdir(parents=True)
        self.provenance = {'config_sha256': 'a' * 64, 'source_sha256': 'b' * 64}
        self.identity = fingerprint(self.provenance)
        self.modules = [{'id': 'clusterer'}, {'id': 'blind_coding'}]
        self.manifest = {'run_id': self.run.name, 'fingerprint': self.identity,
            'provenance': self.provenance, 'status': 'running', 'completed_steps': ['clusterer'],
            'current_module': 'blind_coding', 'module_status': {'blind_coding': 'running'}}
        self.detail = {'run_id': self.run.name, 'fingerprint': self.identity,
            'module': 'blind_coding', 'completed': 3, 'total': 8, 'requests': 4,
            'active_requests': 2, 'request_active': True, 'updated_at': 900,
            'request_started_at': 880, 'last_response_at': 890, 'unit': 'passages',
            'phase': 'analysis', 'private': 'PRIVATE', 'error': 'PRIVATE'}
        self.save()

    def save(self):
        atomic_json(self.run / 'workflow_manifest.json', self.manifest)
        atomic_json(self.run / 'progress.json', self.detail)

    def read(self):
        return series._child_progress(self.parent, self.identity, self.modules)

    def test_projects_bound_child_status_without_any_artifact_hashing(self):
        with patch.object(series, 'file_hash', side_effect=AssertionError('No file hashes during polling')):
            value = self.read()
        self.assertEqual(value['module'], 'blind_coding')
        self.assertEqual((value['modules_completed'], value['modules_total']), (1, 2))
        self.assertEqual(value['detail']['completed'], 3)
        self.assertNotIn('PRIVATE', json.dumps(value))
        self.assertNotIn('run_id', value['detail'])
        self.assertNotIn('fingerprint', value['detail'])

    def test_rejects_other_run_provenance_and_ambiguous_children(self):
        for key, value in (('run_id', 'other'), ('fingerprint', '0' * 64),
                           ('provenance', {'different': True}), ('completed_steps', ['unknown']),
                           ('completed_steps', ['clusterer', 'clusterer'])):
            with self.subTest(key=key, value=value):
                bad = {**self.manifest, key: value}
                atomic_json(self.run / 'workflow_manifest.json', bad)
                self.assertEqual(self.read(), {'state': 'unavailable'})
        self.save()
        (self.parent / 'other-run').mkdir()
        self.assertEqual(self.read(), {'state': 'unavailable'})

    def test_unbound_old_or_wrong_module_progress_never_reuses_counts(self):
        for key, value in (('run_id', 'other'), ('fingerprint', ''), ('module', 'clusterer')):
            with self.subTest(key=key):
                atomic_json(self.run / 'progress.json', {**self.detail, key: value})
                self.assertNotIn('detail', self.read())
        old = {k: v for k, v in self.detail.items() if k not in ('run_id', 'fingerprint')}
        atomic_json(self.run / 'progress.json', old)
        self.assertNotIn('detail', self.read())

    def test_missing_partial_and_oversized_progress_are_nonfatal(self):
        for raw in ('{', '[]', '{' + ' ' * 17000 + '}'):
            (self.run / 'progress.json').write_text(raw, encoding='utf-8')
            self.assertEqual(self.read()['module'], 'blind_coding')
            self.assertNotIn('detail', self.read())
        (self.run / 'progress.json').unlink()
        self.assertNotIn('detail', self.read())
        (self.run / 'workflow_manifest.json').write_text('{' + ' ' * (2 * 1024 * 1024) + '}', encoding='utf-8')
        self.assertEqual(self.read(), {'state': 'unavailable'})

    def test_transition_cannot_mix_two_modules(self):
        original = series._bounded_status
        reads = 0
        def changing(path, root, limit):
            nonlocal reads
            value = original(path, root, limit)
            if path.name == 'workflow_manifest.json':
                reads += 1
                if reads == 2:
                    value['current_module'] = 'clusterer'
            return value
        with patch.object(series, '_bounded_status', side_effect=changing):
            self.assertEqual(self.read(), {'state': 'unavailable'})

    def test_finished_child_is_not_yet_verified_series_success(self):
        self.manifest.update(status='success', current_module=None, completed_steps=['clusterer', 'blind_coding'])
        self.save()
        value = self.read()
        self.assertEqual(value['state'], 'finishing')
        self.assertNotIn('detail', value)

    def test_no_child_is_starting_and_invalid_paths_are_not_followed(self):
        self.assertEqual(series._child_progress(self.root / 'future', self.identity, self.modules), {'state': 'starting'})
        with patch.object(series, '_inside', side_effect=ValueError('outside')):
            self.assertEqual(self.read(), {'state': 'unavailable'})

    def test_nested_projection_rejects_private_strings_bool_counts_and_nonfinite_numbers(self):
        value = safe_series_progress({'configuration_id': 'PRIVATE', 'module': 'PRIVATE', 'state': 'PRIVATE',
            'sample_number': True, 'modules_total': float('inf'), 'detail': {'completed': True,
            'total': -1, 'requests': 'PRIVATE', 'phase': 'PRIVATE', 'unit': 'PRIVATE',
            'last_response_at': float('nan'), 'error': 'PRIVATE', 'text': 'PRIVATE', 'active_requests': 2}})
        self.assertEqual(value, {'detail': {'active_requests': 2}})

    def test_progress_file_is_identity_bound_and_nested_state_clears_on_next_phase(self):
        path = self.root / 'parent-progress.json'
        with patch.dict(os.environ, {'WORKFLOW_PROGRESS_FILE': str(path), 'WORKFLOW_MODULE': 'stability',
                                    'WORKFLOW_RUN_ID': 'parent', 'WORKFLOW_FINGERPRINT': 'c' * 64}):
            progress_events.update_progress(series_current={'sample_number': 1, 'error': 'PRIVATE'}, completed=0, total=2)
            value = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(value['run_id'], 'parent')
            self.assertEqual(value['fingerprint'], 'c' * 64)
            self.assertEqual(value['series_current'], {'sample_number': 1})
            progress_events.begin_phase('comparison')
            self.assertIsNone(json.loads(path.read_text(encoding='utf-8'))['series_current'])

    def test_non_object_old_progress_cannot_break_analysis_events(self):
        path = self.root / 'parent-progress.json'
        with patch.dict(os.environ, {'WORKFLOW_PROGRESS_FILE': str(path), 'WORKFLOW_MODULE': 'blind_coding'}):
            path.write_text('[]', encoding='utf-8')
            progress_events.update_progress(completed=1)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['completed'], 1)
            path.write_text('[]', encoding='utf-8')
            with patch.object(progress_events, 'ACTIVE_REQUESTS', 0):
                progress_events.request_event(start=True)
                progress_events.request_event()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['requests'], 1)

    def test_telegram_distinguishes_outer_and_inner_counts_without_private_labels(self):
        text = format_progress(3, 20, {'module': 'sensitivity', 'phase': 'repetitions',
            'completed': 1, 'total': 6, 'unit': 'repetitions', 'requests': 0,
            'series_current': {'sample_number': 2, 'sample_total': 6, 'configuration_number': 1,
                'configuration_total': 3, 'repetition_number': 2, 'repetition_total': 2,
                'modules_completed': 1, 'modules_total': 2, 'state': 'running',
                'module': 'blind_coding', 'configuration_id': 'PRIVATE', 'detail': self.detail}}, now=1000)
        for expected in ('1 von 6 Wiederholungen', 'Einstellung: 1/3', 'Wiederholung dieser Einstellung: 2/2',
                         'Module: 1/2', 'Blind-Coding', '3/8 Passagen', 'Modellantworten: 4', 'gleichzeitig aktiv: 2'):
            self.assertIn(expected, text)
        self.assertNotIn('Modellantworten: 0', text)
        self.assertNotIn('PRIVATE', text)
        self.assertLess(len(text), 4096)

    def test_unknown_total_and_stale_inner_status_are_explicit(self):
        text = format_progress(3, 20, {'module': 'stability', 'phase': 'repetitions',
            'completed': 0, 'total': 2, 'unit': 'repetitions',
            'series_current': {'state': 'running', 'module': 'overall_synthesis',
                'detail': {'total': None, 'requests': 12, 'request_active': True, 'updated_at': 100}}}, now=1000)
        self.assertIn('Gesamtzahl noch unbekannt', text)
        self.assertIn('Modellantworten: 12', text)
        self.assertIn('drei Minuten unverändert', text)
        self.assertNotIn('12 %', text)

    def test_polling_keeps_supervisor_and_pipe_cleanup_contract(self):
        process = MagicMock()
        process.wait.side_effect = [subprocess.TimeoutExpired('synthetic', 2), 0]
        process.poll.return_value = 0
        calls = []
        token = series._PROGRESS_POLL.set(lambda: calls.append('poll'))
        try:
            with patch.object(series.subprocess, 'Popen', return_value=process), patch.object(series, '_confirmed_supervision') as cleanup:
                self.assertEqual(series._execute(['synthetic'], self.root, self.root / 'synthetic.log', dict(os.environ)), 0)
            self.assertEqual(len(calls), 3)
            self.assertEqual(process.wait.call_count, 2)
            process.stdin.close.assert_called_once()
            cleanup.assert_called_once()
        finally:
            series._PROGRESS_POLL.reset(token)

    def test_display_callback_error_does_not_abort_supervised_process(self):
        process = MagicMock()
        process.wait.return_value = 0
        process.poll.return_value = 0
        def broken():
            raise ValueError('Transient status read')
        token = series._PROGRESS_POLL.set(broken)
        try:
            with patch.object(series.subprocess, 'Popen', return_value=process), patch.object(series, '_confirmed_supervision'):
                self.assertEqual(series._execute(['synthetic'], self.root, self.root / 'synthetic.log', dict(os.environ)), 0)
            process.stdin.close.assert_called_once()
        finally:
            series._PROGRESS_POLL.reset(token)

    def test_keyboard_interrupt_still_closes_lease_and_confirms_cleanup(self):
        process = MagicMock()
        process.wait.side_effect = [KeyboardInterrupt(), 0]
        process.poll.return_value = None
        token = series._PROGRESS_POLL.set(lambda: None)
        try:
            with patch.object(series.subprocess, 'Popen', return_value=process), patch.object(series, '_confirmed_supervision') as cleanup:
                with self.assertRaises(KeyboardInterrupt):
                    series._execute(['synthetic'], self.root, self.root / 'synthetic.log', dict(os.environ))
            process.stdin.close.assert_called_once()
            cleanup.assert_called_once()
            self.assertEqual(process.wait.call_count, 2)
        finally:
            series._PROGRESS_POLL.reset(token)


if __name__ == '__main__':
    unittest.main()
