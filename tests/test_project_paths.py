import os
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import project_paths as paths


class ProjectPathsTests(unittest.TestCase):
    def test_source_resources_are_independent_of_cwd_and_constants_preserved(self):
        expected = Path(paths.__file__).resolve().parent.parent
        with patch.object(sys, 'frozen', False, create=True), patch.object(Path, 'cwd', return_value=Path('/unrelated')):
            self.assertEqual(paths.resource_root(), expected)
        self.assertEqual(paths.SOURCE_DIR, expected / 'src')
        self.assertEqual(paths.DEFAULT_CONFIG, expected / 'config/config_v2.yaml')
        self.assertEqual(paths.DEFAULT_OUTPUT, expected / 'workflow_output')
        self.assertEqual(paths.DEMO_DIR, expected / 'demo')

    def test_frozen_root_is_central_and_missing_bundle_fails(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, '_MEIPASS', temp, create=True):
                self.assertEqual(paths.resource_root(), Path(temp).resolve())
                spec = importlib.util.spec_from_file_location('frozen_paths_probe', paths.__file__)
                bundled = importlib.util.module_from_spec(spec); spec.loader.exec_module(bundled)
                self.assertEqual(bundled.SOURCE_DIR, Path(temp).resolve() / 'src')
                self.assertEqual(bundled.DEFAULT_CONFIG, Path(temp).resolve() / 'config/config_v2.yaml')
                self.assertEqual(bundled.DEMO_DIR, Path(temp).resolve() / 'demo')
            for invalid in (None, '', 'relative_bundle', str(Path(temp) / 'missing')):
                with patch.object(sys, '_MEIPASS', invalid, create=True), self.assertRaises(ValueError):
                    paths.resource_root()

    def test_frozen_outputs_cannot_enter_resource_tree_but_external_target_works(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); bundle = root / '_internal'; bundle.mkdir()
            demo = bundle / 'demo'; demo.mkdir(); source = demo / 'export.csv'; source.write_bytes(b'original')
            external = root / 'Forschung'; external.mkdir()
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(bundle), create=True):
                for args in ({'input_path': source}, {'output_dir': bundle}, {'output_dir': demo},
                             {'output_dir': demo / '..' / 'demo'}):
                    with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'Programmressourcen'):
                        paths.resolve_output_parent(**args, check_write=True)
                self.assertEqual(paths.resolve_output_parent(source, external, True), external.resolve())
            with patch.object(sys, 'frozen', False, create=True):
                self.assertEqual(paths.resolve_output_parent(source, check_write=True), demo.resolve())
            self.assertEqual(source.read_bytes(), b'original')
            self.assertEqual(list(demo.iterdir()), [source])
            self.assertEqual(list(external.iterdir()), [])

    def test_new_platform_defaults_create_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = [('win32', {'LOCALAPPDATA': str(root / 'local')}, root / 'local'),
                     ('darwin', {}, root / 'Library/Application Support'),
                     ('linux', {'XDG_DATA_HOME': str(root / 'xdg')}, root / 'xdg'),
                     ('linux', {'XDG_DATA_HOME': 'relative-invalid'}, root / '.local/share')]
            for platform, env, parent in cases:
                with self.subTest(platform=platform, env=env), patch.object(sys, 'platform', platform), \
                     patch.object(Path, 'home', return_value=root), patch.dict(os.environ, env, clear=True):
                    self.assertEqual(paths.default_data_dir(), (parent / 'QualitativeAnalyse').resolve())
                    self.assertEqual(list(root.iterdir()), [])

    def test_location_guard_checks_missing_bundle_child_before_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); bundle = root / '_internal'; bundle.mkdir()
            blocked = bundle / 'new' / 'results'; allowed = root / 'research' / 'results'
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(bundle), create=True):
                with self.assertRaisesRegex(ValueError, 'Programmressourcen'):
                    paths.validate_output_location(blocked)
                self.assertEqual(paths.validate_output_location(allowed), allowed.resolve())
            self.assertFalse(blocked.parent.exists())
            self.assertFalse(allowed.parent.exists())

    def test_legacy_windows_and_macos_are_found_without_migration(self):
        for platform in ('win32', 'darwin', 'linux'):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                parent = root / 'local' if platform == 'win32' else root / '.local/share'
                legacy = parent / 'QualitativeOllama'; legacy.mkdir(parents=True)
                marker = legacy / 'project.json'; marker.write_text('legacy', encoding='utf-8')
                env = {'LOCALAPPDATA': str(parent)} if platform == 'win32' else {}
                with patch.object(sys, 'platform', platform), patch.object(Path, 'home', return_value=root), patch.dict(os.environ, env, clear=True):
                    self.assertEqual(paths.default_data_dir(), legacy.resolve())
                    self.assertEqual(marker.read_text(encoding='utf-8'), 'legacy')
                    self.assertFalse((parent / 'QualitativeAnalyse').exists())

    def test_multiple_existing_data_dirs_require_explicit_choice(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('QualitativeAnalyse', 'QualitativeOllama'): (root / name).mkdir()
            with patch.object(sys, 'platform', 'win32'), patch.dict(os.environ, {'LOCALAPPDATA': str(root)}, clear=True):
                with self.assertRaisesRegex(ValueError, '--data-dir'):
                    paths.default_data_dir()
            self.assertEqual(len(list(root.iterdir())), 2)

    def test_existing_regular_file_is_not_treated_as_new_data_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'QualitativeAnalyse').write_text('keep', encoding='utf-8')
            with patch.object(sys, 'platform', 'win32'), patch.dict(os.environ, {'LOCALAPPDATA': str(root)}, clear=True):
                with self.assertRaisesRegex(ValueError, 'kein Ordner'): paths.default_data_dir()

    def test_legacy_location_outside_new_platform_parent_and_explicit_ambiguity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); legacy = root / '.local/share/QualitativeOllama'; legacy.mkdir(parents=True)
            for platform, env, parent in [('darwin', {}, root / 'Library/Application Support'),
                                          ('linux', {'XDG_DATA_HOME': str(root / 'xdg')}, root / 'xdg'),
                                          ('win32', {}, root / 'AppData/Local')]:
                with self.subTest(platform=platform), patch.object(sys, 'platform', platform), \
                     patch.object(Path, 'home', return_value=root), patch.dict(os.environ, env, clear=True):
                    self.assertEqual(paths.default_data_dir(), legacy.resolve())
                    preferred = parent / 'QualitativeAnalyse'; preferred.mkdir(parents=True)
                    with self.assertRaisesRegex(ValueError, 'Mehrere bestehende'):
                        paths.default_data_dir()
                    preferred.rmdir()

    def test_input_parent_and_explicit_output_preserve_original_and_leave_no_probe(self):
        with tempfile.TemporaryDirectory(prefix='Prüfung mit Leerzeichen ') as temp:
            root = Path(temp); source = root / 'Äußerungen export.xlsx'; source.write_bytes(b'unchanged-original')
            target = root / 'Andere Ergebnisse'; target.mkdir()
            before = set(root.rglob('*'))
            self.assertEqual(paths.resolve_output_parent(source, check_write=True), root.resolve())
            self.assertEqual(paths.resolve_output_parent(source, target, True), target.resolve())
            self.assertEqual(paths.resolve_output_parent(output_dir=target), target.resolve())
            self.assertEqual(source.read_bytes(), b'unchanged-original')
            self.assertEqual(set(root.rglob('*')), before)

    def test_unknown_fakepath_missing_input_and_missing_target_never_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for args in ({}, {'input_path': ''}, {'input_path': r'C:\fakepath\export.csv'},
                         {'input_path': r'C:\FAKEPATH\export.xlsx'}, {'input_path': root / 'missing.csv'},
                         {'input_path': root}, {'output_dir': root / 'missing'}, {'output_dir': ''}):
                with self.subTest(args=args), self.assertRaises(ValueError): paths.resolve_output_parent(**args)
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual(paths.resolve_output_parent(r'C:\fakepath\export.csv', root), root.resolve())

    def test_write_failure_is_clear_and_does_not_pick_another_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'original.csv'; source.write_bytes(b'original')
            with patch('project_paths.tempfile.NamedTemporaryFile', side_effect=PermissionError('synthetic denied')) as probe:
                with self.assertRaisesRegex(ValueError, 'nicht beschreibbar'):
                    paths.resolve_output_parent(source, check_write=True)
                self.assertEqual(probe.call_args.kwargs['dir'], root.resolve())
            self.assertEqual(list(root.iterdir()), [source])
            self.assertEqual(source.read_bytes(), b'original')


if __name__ == '__main__': unittest.main()
