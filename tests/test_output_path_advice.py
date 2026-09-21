import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from output_path_advice import output_path_check, output_check_message


class OutputPathAdviceTests(unittest.TestCase):
    def test_diagnostics_reserve_generated_nested_names_without_creating_them(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            normal = output_path_check(base, diagnostics=False)
            deep = output_path_check(base, diagnostics=True)
            self.assertGreater(deep['example_utf16_length'], normal['example_utf16_length'])
            self.assertIn('_sensitivity_repetitions/', deep['example_relative_path'])
            self.assertIn('Schätzung', deep['note'])
            self.assertIn('keine Cloud-Synchronisation', deep['note'])
            self.assertEqual(list(base.iterdir()), [])

    def test_unicode_lengths_and_cli_prefix_are_counted_without_app_wrapper(self):
        root = Path(tempfile.gettempdir()) / ('Ä😀' * 20)
        one = output_path_check(root, app_layout=False, diagnostics=False)
        two = output_path_check(root, app_layout=False, diagnostics=False, run_prefix='QualitativeAnalyse_')
        expected = root.resolve() / one['example_relative_path']
        self.assertEqual(one['example_utf16_length'], len(str(expected).encode('utf-16-le')) // 2)
        self.assertEqual(one['example_utf8_bytes'], len(str(expected).encode('utf-8')))
        self.assertEqual(two['example_utf16_length'] - one['example_utf16_length'], len('QualitativeAnalyse_'))
        self.assertNotIn('/runs/', one['example_relative_path'])

    def test_windows_long_path_is_advisory_and_existing_resolver_still_accepts_folder(self):
        from project_paths import resolve_output_parent
        with tempfile.TemporaryDirectory() as temp, patch('output_path_advice.sys.platform', 'win32'):
            root = Path(temp) / ('synthetic' * 10) / ('nested' * 10)
            root.mkdir(parents=True)
            check = output_path_check(root)
            self.assertTrue(check['warnings'])
            self.assertIn('kürzeren Ergebnisordner', check['warnings'][0])
            self.assertEqual(resolve_output_parent(output_dir=root, check_write=True), root.resolve())
            self.assertEqual(list(root.iterdir()), [])

    def test_onedrive_root_requires_real_ancestry_not_name_prefix(self):
        root = Path(tempfile.gettempdir()) / 'synthetic-cloud'
        long = Path(*(['d' * 60] * 5))
        with patch.dict(os.environ, {'OneDrive': str(root), 'OneDriveConsumer': '', 'OneDriveCommercial': ''}):
            inside = output_path_check(root / long)
            sibling = output_path_check(root.with_name(root.name + '-other') / long)
            self.assertGreaterEqual(inside['onedrive_relative_utf16_length'], 400)
            self.assertTrue(any('OneDrive' in w for w in inside['warnings']))
            self.assertIsNone(sibling['onedrive_relative_utf16_length'])
            self.assertFalse(any('OneDrive' in w for w in sibling['warnings']))

    def test_short_cli_destination_has_no_generic_false_cloud_success(self):
        with patch('output_path_advice.sys.platform', 'win32'), patch.dict(os.environ, {}, clear=True):
            result = output_path_check(Path(tempfile.gettempdir()).anchor, app_layout=False, diagnostics=False)
            self.assertEqual(result['warnings'], [])
            self.assertIn('keine Cloud-Synchronisation', output_check_message(result))

    def test_non_windows_utf8_warning_does_not_apply_windows_cutoff(self):
        with patch('output_path_advice.sys.platform', 'darwin'), patch.dict(os.environ, {}, clear=True):
            small = output_path_check(Path(tempfile.gettempdir()) / ('a' * 140))
            large = output_path_check(Path(tempfile.gettempdir()) / Path(*(['漢' * 90] * 4)))
            self.assertGreater(small['example_utf16_length'], 260)
            self.assertEqual(small['warnings'], [])
            self.assertTrue(any('UTF-8-Bytes' in w for w in large['warnings']))


if __name__ == '__main__':
    unittest.main()
