"""Check the user-facing entry points after the directory reorganization."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectLayoutTests(unittest.TestCase):
    def test_cli_defaults_work_outside_installation_directory(self):
        with tempfile.TemporaryDirectory(prefix='layout test ') as tmp:
            result = subprocess.run(
                [sys.executable, '-X', 'utf8', str(ROOT/'run_workflow.py'), '--validate-only'],
                cwd=tmp, capture_output=True, text=True, encoding='utf-8',
                env={**os.environ, 'PYTHONUTF8':'1'})
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            self.assertFalse(list(Path(tmp).iterdir()), 'Validation must not start an analysis or create outputs.')

    def test_runner_accepts_explicit_config_relative_to_working_directory(self):
        result = subprocess.run(
            [sys.executable, '-X', 'utf8', str(ROOT/'run_workflow.py'), '--config', 'config/config_v2.yaml', '--validate-only'],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
            env={**os.environ, 'PYTHONUTF8':'1'})
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])


if __name__ == '__main__':
    unittest.main()
