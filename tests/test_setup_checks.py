"""Distribution-specific setup advice without installers or model processes."""
import importlib.metadata
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from setup_checks import check_setup


class SetupChecksTests(unittest.TestCase):
    def run_check(self, *, frozen, platform='win32', missing='pandas', offline=False, cloud=False):
        def version(package):
            if package == missing:
                raise importlib.metadata.PackageNotFoundError(package)
            return '1.2.3'
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(directory=Path(directory), models=Mock(), authorize_llm=Mock())
            app.models.return_value = {'models': ['synthetic-model']}
            if offline:
                app.models.side_effect = ValueError('Ollama ist nicht erreichbar.')
            selected = {'provider': 'openai', 'model': 'synthetic-model'} if cloud else None
            app.authorize_llm.return_value = selected
            with patch('coding_validation_common.default_llm') as llm, \
                    patch('setup_checks.sys.frozen', frozen, create=True), \
                    patch('setup_checks.sys.platform', platform), \
                    patch('setup_checks.importlib.metadata.version', side_effect=version), \
                    patch('subprocess.Popen') as process:
                result = check_setup(app, 'synthetic-model', selected, 'synthetic-project')
                process.assert_not_called()
                llm.assert_not_called()
            return result, app

    def test_frozen_missing_dependency_requires_complete_package_not_source_setup(self):
        result, _ = self.run_check(frozen=True)
        checks = {row['name']: row for row in result['checks']}
        self.assertTrue(checks['Python (im Programmpaket)']['ok'])
        self.assertFalse(checks['pandas']['ok'])
        self.assertIn('vollständige Programmpaket', checks['pandas']['detail'])
        self.assertIn('neuen Ordner', checks['pandas']['detail'])
        self.assertIn('QualitativeAnalyse.exe', checks['pandas']['detail'])
        self.assertNotIn('Einrichtung.cmd', checks['pandas']['detail'])
        self.assertNotIn('pip', checks['pandas']['detail'])
        self.assertTrue(checks['numpy']['ok'])
        self.assertEqual(result['model_calls'], 0)

    def test_source_repair_uses_current_platform_launcher(self):
        for platform, expected, absent in (
            ('win32', 'Einrichtung.cmd', 'Einrichtung.command'),
            ('darwin', 'start/macos/Einrichtung.command', 'Einrichtung.cmd'),
            ('linux', 'requirements.txt', 'Einrichtung.cmd'),
        ):
            with self.subTest(platform=platform):
                result, _ = self.run_check(frozen=False, platform=platform)
                checks = {row['name']: row for row in result['checks']}
                self.assertTrue(checks['Python']['ok'])
                self.assertIn(expected, checks['pandas']['detail'])
                self.assertNotIn(absent, checks['pandas']['detail'])
                self.assertNotIn('QualitativeAnalyse.exe', checks['pandas']['detail'])

    def test_frozen_python_client_and_ollama_server_are_independent_checks(self):
        result, _ = self.run_check(frozen=True, missing='ollama', offline=True)
        checks = {row['name']: row for row in result['checks']}
        self.assertFalse(checks['ollama']['ok'])
        self.assertIn('Programmpaket', checks['ollama']['detail'])
        self.assertFalse(checks['Ollama']['ok'])
        self.assertIn('Oberfläche', checks['Ollama']['detail'])
        self.assertIn('reine Diagnosen ohne Modellbedarf nutzbar', checks['Ollama']['detail'])
        self.assertNotIn('Programmpaket', checks['Ollama']['detail'])
        self.assertEqual(result['models'], [])
        self.assertEqual(result['model_calls'], 0)

    def test_authorized_cloud_does_not_probe_local_ollama(self):
        result, app = self.run_check(frozen=True, missing=None, cloud=True, offline=True)
        app.models.assert_not_called()
        app.authorize_llm.assert_called_once_with('synthetic-project',
            {'provider': 'openai', 'model': 'synthetic-model'}, installed=False)
        checks = {row['name']: row for row in result['checks']}
        self.assertTrue(checks['KI-Anbieter']['ok'])
        self.assertNotIn('Ollama', checks)
        self.assertEqual(result['model_calls'], 0)


if __name__ == '__main__':
    unittest.main()
