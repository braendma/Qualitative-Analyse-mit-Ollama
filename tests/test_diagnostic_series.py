import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from test_diagnostic_repetitions import Workspace, ROOT
import diagnostic_series as series
from diagnostic_repetitions import prepare_repetitions
from runtime_support import atomic_json, exclusive_file_lock


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = Workspace(Path(self.tmp.name))
        self.plan = prepare_repetitions(self.w.path, ['blind_coding'], repetitions=2)
        self.root = self.w.root / 'series'
        self.trace = self.w.root / 'trace.jsonl'
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('MOCK_', 'WORKFLOW_')) and k != 'QUALITATIVE_MANAGED_OLLAMA_HOST'}
        env.update(MOCK_TRACE_PATH=str(self.trace), MPLBACKEND='Agg')
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, env, clear=True).start()
        self.command = patch.object(series, '_runner_command', return_value=[sys.executable, str(ROOT/'tests/mock_pipeline.py')]).start()

    def execute(self, **kwargs):
        return series.execute_repetitions(self.plan, self.root, **kwargs)

    def manifest(self, sample='repeat-001'):
        run = next((self.root / sample).iterdir())
        return run, json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))

    def test_two_fresh_runs_and_completed_resume_without_dispatch(self):
        result = self.execute()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['completed_samples'], 2)
        first, a = self.manifest(); second, b = self.manifest('repeat-002')
        self.assertNotEqual(a['run_id'], b['run_id'])
        self.assertEqual(a['fingerprint'], b['fingerprint'])
        self.assertTrue((first/'blind_coding_checkpoint.json').is_file())
        self.assertTrue((second/'blind_coding_checkpoint.json').is_file())
        calls = self.trace.read_bytes()
        self.assertGreater(len(calls), 0)
        with patch.object(series, '_execute', side_effect=AssertionError('Completed run dispatched')):
            self.assertEqual(self.execute(resume=True)['completed_samples'], 2)
        self.assertEqual(self.trace.read_bytes(), calls)
        with self.assertRaises(FileExistsError):
            self.execute()

    def test_failure_stops_series_then_resumes_same_child_and_starts_next_fresh(self):
        with patch.dict(os.environ, {'MOCK_FAIL_MODULE': 'blind_coding', 'MOCK_FAIL_AFTER': '1'}):
            failed = self.execute()
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['completed_samples'], 0)
        self.assertFalse((self.root/'repeat-002').exists())
        run, before = self.manifest()
        self.assertIn('clusterer', before['completed_steps'])
        result = self.execute(resume=True)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(self.manifest()[1]['run_id'], before['run_id'])
        self.assertEqual(self.manifest()[1]['status'], 'success')
        self.assertNotEqual(self.manifest('repeat-002')[1]['run_id'], before['run_id'])

    def test_pause_before_dispatch_and_inside_child_runner(self):
        pause = self.w.root/'pause'
        pause.touch()
        self.assertEqual(self.execute(pause_file=pause)['status'], 'paused')
        self.assertFalse((self.root/'repeat-001').exists())
        pause.unlink()
        original = series._execute
        def pausing(command, directory, log, env):
            pause.touch()  # Runner starts but pauses before its first module.
            return original(command, directory, log, env)
        with patch.object(series, '_execute', side_effect=pausing):
            self.assertEqual(self.execute(resume=True, pause_file=pause)['status'], 'paused')
        self.assertEqual(self.manifest()[1]['status'], 'paused')
        self.assertFalse((self.root/'repeat-002').exists())
        pause.unlink()
        self.assertEqual(self.execute(resume=True, pause_file=pause)['status'], 'success')

    def test_altered_plan_input_config_or_execution_identity_refuses_dispatch(self):
        with patch.object(series, '_execute', side_effect=AssertionError('Must not dispatch')):
            altered = copy.deepcopy(self.plan); altered['samples'][0]['sample_id'] = '../other'
            with self.assertRaisesRegex(ValueError, 'Plan|plan'):
                series.execute_repetitions(altered, self.root)
            pause = self.w.root/'pause'; pause.touch()
            self.execute(pause_file=pause)
            with patch.object(series, '_identity', return_value='changed-code'):
                with self.assertRaisesRegex(ValueError, 'Code, Abhängigkeiten'):
                    self.execute(resume=True)
            original = self.w.path.read_bytes()
            self.w.path.write_bytes(original+b'\n')
            with self.assertRaisesRegex(ValueError, 'Plan|plan'):
                self.execute(resume=True)
            self.w.path.write_bytes(original)
            (self.root/'repetition_config.yaml').write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Serienkonfiguration'):
                self.execute(resume=True)

    def test_outputs_reports_and_snapshot_tampering_refuse_resume(self):
        self.execute()
        run, _ = self.manifest()
        for name in ('blind_coding.json', 'gesamtbericht.html', 'config_snapshot.yaml'):
            path = run/name
            if name == 'blind_coding.json':
                # Use the configured filename rather than assuming a module convention.
                module = next(m for m in self.plan['config']['pipeline']['modules'] if m['id']=='blind_coding')
                path = run/next(n for n in module['outputs'] if n.endswith('.json'))
            before = path.read_bytes(); path.write_bytes(before+b'changed')
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.execute(resume=True)
            path.write_bytes(before)

    def test_ambiguous_corrupt_and_running_children_fail_closed(self):
        self.execute()
        run, original = self.manifest()
        extra = run.parent/'unexpected'; extra.mkdir()
        with self.assertRaisesRegex(ValueError, 'Mehrdeutiger'):
            self.execute(resume=True)
        extra.rmdir()
        path = run/'workflow_manifest.json'; path.write_text('{', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'beschädigt'):
            self.execute(resume=True)
        data = copy.deepcopy(original); data['status'] = 'running'; atomic_json(path, data)
        with self.assertRaisesRegex(ValueError, 'Doppelstart'):
            self.execute(resume=True)
        data['status'] = 'success'; data['completed_steps'] = []; atomic_json(path, data)
        with self.assertRaisesRegex(ValueError, 'Erfolg ohne'):
            self.execute(resume=True)

    def test_outer_progress_and_checkpoint_environment_is_not_inherited(self):
        observed = {}
        def failing(command, directory, log, env):
            observed.update(env)
            return 1
        with patch.dict(os.environ, {'WORKFLOW_RUN_ID':'parent', 'WORKFLOW_CHECKPOINT_DIR':'parent-cache', 'WORKFLOW_PROGRESS_FILE':'parent-progress'}):
            with patch.object(series, '_execute', side_effect=failing):
                result = self.execute()
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(any(k.startswith('WORKFLOW_') for k in observed))
        self.assertFalse((self.root/'repeat-002').exists())

    def test_parent_managed_server_rejected_before_creating_series(self):
        with patch.dict(os.environ, {'QUALITATIVE_MANAGED_OLLAMA_HOST':'http://127.0.0.1:12345'}):
            with self.assertRaisesRegex(ValueError, 'übergeordneten'):
                self.execute()
        self.assertFalse(self.root.exists())

    def test_lock_excludes_other_process_and_releases_after_exception(self):
        lock = self.w.root/'lock'
        command = [sys.executable, '-c',
            'import sys;sys.path.insert(0,sys.argv[1]);from runtime_support import exclusive_file_lock;'
            '\nwith exclusive_file_lock(sys.argv[2]): pass', str(ROOT/'src'), str(lock)]
        with self.assertRaisesRegex(RuntimeError, 'intentional'):
            with exclusive_file_lock(lock):
                attempt = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
                self.assertNotEqual(attempt.returncode, 0)
                self.assertIn('anderen Prozess', attempt.stderr)
                raise RuntimeError('intentional')
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_process_tree_is_reaped_on_keyboard_interrupt(self):
        process = MagicMock(); process.wait.side_effect = [KeyboardInterrupt(), 0]
        process.poll.return_value = None
        with patch.object(series.subprocess, 'Popen', return_value=process), patch.object(series, 'stop_tree') as stop:
            with self.assertRaises(KeyboardInterrupt):
                series._execute(['synthetic'], self.w.root, self.w.root/'log', dict(os.environ))
        stop.assert_called_once_with(process)
        self.assertEqual(process.wait.call_count, 2)


if __name__ == '__main__':
    unittest.main()
