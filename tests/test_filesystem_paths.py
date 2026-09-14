from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import filesystem_paths as paths
import project_paths
from runtime_support import atomic_text, file_hash, exclusive_file_lock


@contextmanager
def local_directory():
    temporary = tempfile.TemporaryDirectory(prefix='qa-path-')
    root = Path(temporary.name).resolve()
    try:
        yield root
    finally:
        # This exclusively created synthetic tree can exceed MAX_PATH. Use
        # its checked extended root for cleanup too; never delete input data.
        if paths.io_path(root).exists():
            shutil.rmtree(paths.io_path(root))
        temporary.cleanup()


class FilesystemPathTests(unittest.TestCase):
    def test_source_relative_inputs_still_resolve_against_current_directory(self):
        relative = Path('synthetic folder') / 'file.csv'
        self.assertEqual(paths.absolute_path(relative), Path.cwd() / relative)
        self.assertEqual(paths.canonical_path(relative), (Path.cwd() / relative).resolve())

    def test_lexical_path_does_not_follow_a_mocked_redirect(self):
        with local_directory() as root:
            expected, outside = root / 'research' / 'redirect', root / 'outside'
            lexical = paths.absolute_path(expected)
            with patch.object(Path, 'resolve', return_value=outside):
                actual = paths.canonical_path(expected)
            self.assertEqual(lexical, expected)
            self.assertEqual(actual, outside)
            self.assertNotEqual(lexical, actual)


@unittest.skipUnless(os.name == 'nt', 'Native Windows path semantics')
class WindowsFilesystemPathTests(unittest.TestCase):
    def test_drive_prefix_is_idempotent_and_same_file_identity(self):
        with local_directory() as root:
            target = root / 'Leerzeichen und ä' / 'Daten.csv'
            target.parent.mkdir(); target.write_bytes(b'synthetic')
            extended = paths.io_path(target)
            self.assertTrue(str(extended).startswith('\\\\?\\'))
            self.assertEqual(paths.io_path(extended), extended)
            self.assertEqual(paths.absolute_path(extended), target)
            self.assertEqual(paths.canonical_path(extended), paths.canonical_path(target))
            self.assertTrue(extended.samefile(target))
            self.assertEqual(paths.canonical_path(str(target).swapcase()), paths.canonical_path(target))

    def test_unc_translation_is_lexical_and_never_resolves_or_contacts_server(self):
        ordinary = r'\\synthetic-server\synthetic-share\Beispielstudie\input.csv'
        extended = r'\\?\UNC\synthetic-server\synthetic-share\Beispielstudie\input.csv'
        with (patch.object(Path, 'resolve', side_effect=AssertionError('No UNC filesystem resolution')),
              patch.object(Path, 'stat', side_effect=AssertionError('No UNC network probe'))):
            self.assertEqual(str(paths.io_path(ordinary)), extended)
            self.assertEqual(str(paths.io_path(extended)), extended)
            self.assertEqual(str(paths.absolute_path(extended)), ordinary)

    def test_namespace_and_ambiguous_components_are_rejected(self):
        invalid = [r'\\.\PhysicalDrive0', r'\\.\pipe\synthetic', r'\??\C:\data',
                   r'\\?\GLOBALROOT\Device\HarddiskVolume1\data', r'\\?\Volume{synthetic}\data',
                   r'\\?\\\?\C:\data', r'\\synthetic-server', r'\\?\UNC\synthetic-server',
                   r'C:relative', r'\drive-relative', r'C:\data\report.html:stream',
                   r'C:\data\ending.', 'C:\\data\\ending ', r'C:\data\CON', r'C:\data\NUL.csv',
                   r'C:\data\LPT1.txt', r'C:\data\COM1', 'C:\\data\\bad\x00name',
                   'C:\\data\\bad\nname']
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError): paths.io_path(value)

    def test_extended_parent_components_are_not_silently_reinterpreted(self):
        for value in (r'\\?\C:\research\..\elsewhere', r'\\?\C:\research\.\file.csv',
                      r'\\?\UNC\server\share\..\file.csv'):
            with self.subTest(value=value), self.assertRaises(ValueError): paths.io_path(value)

    def test_containment_unifies_prefixes_without_string_prefix_false_positives(self):
        with local_directory() as root:
            inside, sibling = root / 'study' / 'child', root / 'study2'
            inside.mkdir(parents=True); sibling.mkdir()
            for base in (root / 'study', paths.io_path(root / 'study')):
                for child in (inside, paths.io_path(inside)):
                    self.assertTrue(paths.canonical_path(child).is_relative_to(paths.canonical_path(base)))
                self.assertFalse(paths.canonical_path(sibling).is_relative_to(paths.canonical_path(base)))

    def test_frozen_output_guard_rejects_both_resource_representations_before_mkdir(self):
        with local_directory() as root:
            bundle, outside = root / 'bundle', root / 'research'
            bundle.mkdir(); outside.mkdir()
            for bound in (bundle, paths.io_path(bundle)):
                with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(bound), create=True):
                    for target in (bundle / 'not-created', paths.io_path(bundle / 'not-created')):
                        with self.assertRaisesRegex(ValueError, 'Programmressourcen'):
                            project_paths.validate_output_location(target)
                    self.assertEqual(project_paths.validate_output_location(paths.io_path(outside)), outside)
            self.assertFalse((bundle / 'not-created').exists())

    def test_native_symlink_keeps_lexical_and_canonical_identity_distinct(self):
        with local_directory() as root:
            destination = root / 'outside'; destination.mkdir()
            expected = root / 'link'
            try:
                expected.symlink_to(destination, target_is_directory=True)
            except OSError as exc:
                if getattr(exc, 'winerror', None) == 1314:
                    self.skipTest('Windows account lacks symlink creation privilege; mocked redirect case remains covered')
                raise
            try:
                for alias in (expected, paths.io_path(expected)):
                    self.assertEqual(paths.absolute_path(alias), expected)
                    self.assertEqual(paths.canonical_path(alias), destination)
                    self.assertNotEqual(paths.absolute_path(alias), paths.canonical_path(alias))
            finally:
                expected.unlink()

    def test_real_long_file_atomic_write_read_hash_glob_and_lock(self):
        with local_directory() as root:
            directory = root
            while len(str(directory)) < 330:
                directory /= 'synthetisch_ä_' + 'x' * 33
            target = directory / 'Bericht mit Leerzeichen.html'
            self.assertGreater(len(str(target)), 260)
            first = '<html>Nur synthetischer Text ä.</html>\n'
            atomic_text(target, first)
            self.assertEqual(paths.io_path(target).read_text(encoding='utf-8'), first)
            self.assertEqual(file_hash(target), hashlib.sha256(first.encode('utf-8')).hexdigest())
            second = '<html>Geänderte synthetische Fassung.</html>\n'
            atomic_text(paths.io_path(target), second)
            self.assertEqual(paths.io_path(target).read_text(encoding='utf-8'), second)
            self.assertEqual(list(paths.io_path(directory).glob('*.html')), [paths.io_path(target)])
            self.assertEqual(list(paths.io_path(directory).glob('*.tmp')), [])
            with exclusive_file_lock(paths.io_path(directory / '.test.lock')): pass
            self.assertEqual(paths.canonical_path(paths.io_path(target)), paths.canonical_path(target))
            paths.io_path(target).unlink()
            self.assertFalse(paths.io_path(target).exists())

    def test_long_file_support_does_not_claim_long_process_cwd_support(self):
        with local_directory() as root:
            directory = root
            while len(str(directory)) < 270:
                directory /= 'process-directory-' + 'x' * 27
            paths.io_path(directory).mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'kürzeren Ordner'):
                paths.process_directory(directory)
            self.assertEqual(paths.process_directory(root), root)


if __name__ == '__main__': unittest.main()
