"""Real CLI output placement and explicit/legacy desktop data selection."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from test_diagnostic_repetitions import Workspace, ROOT
from runtime_support import file_hash


class EntryPointPathsTests(unittest.TestCase):
    def workspace(self, root):
        w = Workspace(root)
        for module in w.config['pipeline']['modules']:
            module['enabled'] = module['id'] == 'coverage'
        w.save()
        return w

    def run_cli(self, w, *args, cwd=None):
        result = subprocess.run([sys.executable, str(ROOT/'src/00_WORKFLOW_RUNNER.py'),
            '--config', str(w.path), *map(str, args)], cwd=cwd or w.root,
            env={**os.environ, 'PYTHONUTF8':'1', 'MPLBACKEND':'Agg'},
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        return result

    def test_default_runs_beside_original_from_unrelated_cwd_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); study = root/'Studie mit Umlaut ä'; study.mkdir()
            elsewhere = root/'Arbeitsordner'; elsewhere.mkdir()
            w = self.workspace(study)
            before = {p.name:file_hash(p) for p in study.iterdir()}
            self.run_cli(w, '--validate-only', cwd=elsewhere)
            self.assertEqual({p.name for p in study.iterdir()}, set(before))
            self.run_cli(w, cwd=elsewhere)
            first = next(study.glob('QualitativeAnalyse_*'))
            manifest = json.loads((first/'workflow_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'], 'success')
            self.assertTrue((first/'gesamtbericht.html').is_file())
            artifacts = dict(manifest['output_hashes'])
            self.run_cli(w, cwd=elsewhere)
            self.assertEqual(len(list(study.glob('QualitativeAnalyse_*'))), 2)
            self.run_cli(w, '--resume', first, cwd=elsewhere)
            self.assertEqual(len(list(study.glob('QualitativeAnalyse_*'))), 2)
            resumed = json.loads((first/'workflow_manifest.json').read_text(encoding='utf-8'))
            # The aggregate report is rebuilt with the current timestamp on resume;
            # completed analytical artifacts must stay byte-for-byte unchanged.
            for name, digest in artifacts.items():
                if name not in ('gesamtbericht.md', 'gesamtbericht.html'):
                    self.assertEqual(resumed['output_hashes'][name], digest)
                self.assertEqual(resumed['output_hashes'][name], file_hash(first/name))
            self.assertEqual({name:file_hash(study/name) for name in before}, before)
            self.assertEqual(list(elsewhere.iterdir()), [])

    def test_csv_override_places_results_by_actual_input_and_explicit_root_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); study = root/'Original'; study.mkdir()
            w = self.workspace(study); other = root/'Andere Daten'; other.mkdir()
            csv = other/'anders benannt.csv'; csv.write_bytes((study/'input.csv').read_bytes())
            before = file_hash(csv)
            self.run_cli(w, '--csv', csv)
            self.assertEqual(len(list(other.glob('QualitativeAnalyse_*'))), 1)
            self.assertEqual(list(study.glob('QualitativeAnalyse_*')), [])
            explicit = root/'Auswertung'/'neues Ziel'
            self.run_cli(w, '--csv', csv, '--output-dir', explicit)
            runs = list(explicit.iterdir())
            self.assertEqual(len(runs), 1)
            self.assertTrue((runs[0]/'workflow_manifest.json').is_file())
            self.assertEqual(file_hash(csv), before)

    def test_invalid_explicit_output_stops_without_fallback_or_model(self):
        runner = importlib.import_module('00_WORKFLOW_RUNNER')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); w = self.workspace(root)
            output = root/'existing.txt'; output.write_text('keep', encoding='utf-8')
            before = {p.name:file_hash(p) for p in root.iterdir()}
            with patch('managed_ollama.ManagedOllama.start', side_effect=AssertionError('Must not start model')):
                with self.assertRaisesRegex(ValueError, 'Ergebnisordner'):
                    runner.main(['--config', str(w.path), '--output-dir', str(output)])
            self.assertEqual({p.name:file_hash(p) for p in root.iterdir()}, before)

    def test_desktop_explicit_data_dir_bypasses_ambiguous_defaults(self):
        import local_app
        server = MagicMock(); server.server_port=12345; server.token='synthetic'
        server.serve_forever.side_effect=KeyboardInterrupt
        with tempfile.TemporaryDirectory() as tmp:
            chosen=Path(tmp)/'chosen'
            with patch.object(sys, 'argv', ['app', '--no-browser', '--data-dir', str(chosen)]), \
                 patch.object(local_app, 'default_data_dir', side_effect=AssertionError('Explicit wins')), \
                 patch.object(local_app, 'App') as app, patch.object(local_app, 'make_server', return_value=server), \
                 contextlib.redirect_stdout(io.StringIO()):
                app.return_value.runtime_status.return_value={'state':'open','active':None}
                def close_idle(mode):
                    self.assertEqual(mode,'idle')
                    app.return_value.runtime_status.return_value={'state':'closed','active':None}
                app.return_value.shutdown.side_effect=close_idle
                local_app.main()
            app.assert_called_once_with(chosen.resolve(), None)
            app.return_value.shutdown.assert_called_once_with('idle')
        server.server_close.assert_called_once()

    def test_frozen_explicit_output_does_not_create_directory_inside_bundle(self):
        runner = importlib.import_module('00_WORKFLOW_RUNNER')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); study = root/'study'; study.mkdir()
            w = self.workspace(study); bundle = root/'bundle'; bundle.mkdir()
            output = bundle/'must not be created'
            with patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, '_MEIPASS', str(bundle), create=True):
                with self.assertRaises(ValueError):
                    runner.main(['--config', str(w.path), '--output-dir', str(output)])
            self.assertEqual(list(bundle.iterdir()), [])
            self.assertEqual(list(study.glob('QualitativeAnalyse_*')), [])

    def test_desktop_reports_ambiguous_defaults_before_initialization(self):
        import local_app
        with patch.object(sys, 'argv', ['app', '--no-browser']), \
             patch.object(local_app, 'default_data_dir', side_effect=ValueError('Bitte --data-dir wählen')), \
             patch.object(local_app, 'App') as app, contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as caught:
                local_app.main()
        self.assertEqual(caught.exception.code, 2)
        app.assert_not_called()
        self.assertIn('--data-dir', error.getvalue())


if __name__ == '__main__':
    unittest.main()
