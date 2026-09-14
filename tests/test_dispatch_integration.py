"""Real dispatch boundaries; all model-free material and extension code are synthetic."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_diagnostic_repetitions import Workspace, ROOT
from runtime_support import file_hash

ENTRY = ROOT / 'src' / 'runtime_entry.py'


class DispatchIntegrationTests(unittest.TestCase):
    def workspace(self, directory):
        w = Workspace(directory)
        for module in w.config['pipeline']['modules']:
            module['enabled'] = module['id'] == 'coverage'
        w.save()
        return w

    def dispatch(self, directory, *args):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('WORKFLOW_', 'MOCK_'))
               and key not in ('QUALITATIVE_MANAGED_OLLAMA_HOST', 'OLLAMA_HOST')}
        env.update(PYTHONUTF8='1', MPLBACKEND='Agg', LOCALAPPDATA=str(directory/'unused-appdata'))
        return subprocess.run([sys.executable, str(ENTRY), *map(str, args)],
                              cwd=directory, env=env, capture_output=True,
                              text=True, encoding='utf-8', timeout=30)

    def test_real_source_dispatch_runs_coverage_outside_installation_and_resumes_same_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); study = root/'Synthetic study ä'; study.mkdir()
            elsewhere = root/'Different cwd'; elsewhere.mkdir(); w = self.workspace(study)
            before = {p.name:file_hash(p) for p in study.iterdir()}
            first = self.dispatch(elsewhere, '--internal-script', '00_WORKFLOW_RUNNER.py', '--config', w.path)
            self.assertEqual(first.returncode, 0, first.stderr[-3500:])
            run = next(study.glob('QualitativeAnalyse_*'))
            manifest = json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'], 'success')
            self.assertEqual(manifest['completed_steps'], ['coverage'])
            coverage = json.loads((run/'coverage.json').read_text(encoding='utf-8'))
            self.assertEqual(coverage['model_calls'], 0)
            self.assertEqual(coverage['material']['material_units'], 2)
            self.assertTrue((run/'gesamtbericht.html').is_file())
            expected = file_hash(run/'coverage.json')
            resumed = self.dispatch(elsewhere, '--internal-script', '00_WORKFLOW_RUNNER.py',
                                    '--config', w.path, '--resume', run)
            self.assertEqual(resumed.returncode, 0, resumed.stderr[-3500:])
            self.assertEqual(file_hash(run/'coverage.json'), expected)
            self.assertEqual(len(list(study.glob('QualitativeAnalyse_*'))), 1)
            self.assertEqual({name:file_hash(study/name) for name in before}, before)
            self.assertEqual(list(elsewhere.iterdir()), [], 'Internal CLI must not initialize desktop app data')

    def test_invalid_internal_targets_fail_without_executing_external_source_or_starting_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); marker = root/'executed.txt'; script = root/'outside.py'
            script.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("executed")\n', encoding='utf-8')
            for args in (['--internal-script'], ['--internal-script', str(script)],
                         ['--internal-script', '../outside.py'], ['--internal-script', 'runtime_entry.py']):
                with self.subTest(args=args):
                    result = self.dispatch(root, *args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(marker.exists())
                    self.assertFalse((root/'unused-appdata').exists())
            self.assertEqual({p.name for p in root.iterdir()}, {'outside.py'})

    def test_frozen_runner_rejects_unbundled_enabled_module_before_runtime_or_output(self):
        runner = importlib.import_module('00_WORKFLOW_RUNNER')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); w = self.workspace(root)
            custom = root/'custom.py'; custom.write_text('raise AssertionError("Must not execute")\n', encoding='utf-8')
            w.config['pipeline']['modules'] = [{'id':'custom', 'script':str(custom),
                'enabled':True, 'requires_model':True, 'depends_on':[], 'args':[], 'outputs':['custom.json']}]
            w.save(); before = {p.name:file_hash(p) for p in root.iterdir()}
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(ROOT), create=True), \
                 patch('managed_ollama.ManagedOllama') as managed, patch.object(runner.subprocess, 'run') as child:
                with self.assertRaises(ValueError):
                    runner.main(['--config', str(w.path), '--output-dir', str(root/'outputs')])
                managed.assert_not_called(); child.assert_not_called()
            self.assertEqual({p.name:file_hash(p) for p in root.iterdir()}, before)

    def test_source_runner_still_executes_explicit_model_free_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); w = self.workspace(root)
            custom = root/'extension ä.py'
            custom.write_text('from pathlib import Path\nPath("custom.json").write_text(\'{"synthetic": true}\', encoding="utf-8")\n', encoding='utf-8')
            w.config['pipeline']['modules'] = [{'id':'custom', 'script':str(custom),
                'enabled':True, 'requires_model':False, 'depends_on':[], 'args':[], 'outputs':['custom.json']}]
            w.save()
            result = self.dispatch(root, '--internal-script', '00_WORKFLOW_RUNNER.py', '--config', w.path)
            self.assertEqual(result.returncode, 0, result.stderr[-3500:])
            run = next(root.glob('QualitativeAnalyse_*'))
            self.assertEqual(json.loads((run/'custom.json').read_text()), {'synthetic':True})
            manifest = json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['completed_steps'], ['custom'])
            self.assertEqual(manifest['status'], 'success')
            self.assertFalse((root/'unused-appdata').exists())


if __name__ == '__main__':
    unittest.main()
