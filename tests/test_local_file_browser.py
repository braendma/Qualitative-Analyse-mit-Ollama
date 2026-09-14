from contextlib import contextmanager
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import local_file_browser as browser


class LocalFileBrowserTests(unittest.TestCase):
    def test_direct_sorted_children_and_extensions_without_contents_or_mutation(self):
        with tempfile.TemporaryDirectory(prefix='Ä Auswahl ') as temp:
            root = Path(temp)
            for name in ('Zeta', 'alpha', '.hidden'): (root / name).mkdir()
            for name in ('z.XLSX', 'a.csv', 'secret.txt', '.hidden.csv'):
                (root / name).write_bytes(b'unchanged')
            (root / 'alpha/nested.csv').write_bytes(b'nested')
            before = {str(p): p.stat().st_mtime_ns for p in root.rglob('*')}
            with patch.object(Path, 'home', return_value=root), patch.object(Path, 'read_bytes', side_effect=AssertionError('No content reads')):
                result = browser.browse('', 'segments')
                self.assertEqual([x['name'] for x in result['directories']], ['alpha', 'Zeta'])
                self.assertEqual([x['name'] for x in result['files']], ['a.csv', 'z.XLSX'])
                self.assertEqual(result['path'], str(root.resolve()))
                self.assertFalse(result['truncated'])
                self.assertEqual(browser.browse(root, 'directory')['files'], [])
                self.assertEqual(browser.browse(root, 'codebook')['files'], result['files'])
            self.assertEqual({str(p): p.stat().st_mtime_ns for p in root.rglob('*')}, before)

    def test_explicit_bad_path_does_not_fall_back_to_home(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'file.csv'; source.write_bytes(b'data')
            for value in ('relative', root / 'missing', source, None):
                with self.subTest(value=value), patch.object(Path, 'home', side_effect=AssertionError('No fallback')):
                    with self.assertRaises(ValueError): browser.browse(value, 'segments')
            with self.assertRaises(ValueError): browser.browse(root, 'unknown')
            with patch('local_file_browser.os.scandir', side_effect=PermissionError('synthetic')):
                with self.assertRaisesRegex(ValueError, 'Zugriffsrechte'): browser.browse(root)

    def test_scan_budget_includes_hidden_entries_and_does_not_consume_more(self):
        inspected = []
        def entries():
            for i in range(1100):
                inspected.append(i)
                yield SimpleNamespace(name='.' + str(i))
        @contextmanager
        def scanning(path): yield entries()
        with tempfile.TemporaryDirectory() as temp, patch('local_file_browser.os.scandir', scanning):
            result = browser.browse(Path(temp), 'segments')
        self.assertEqual(len(inspected), 1000)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['files'], [])

    def test_windows_roots_use_drive_mask_without_filesystem_probes(self):
        import ctypes
        backend = SimpleNamespace(kernel32=SimpleNamespace(GetLogicalDrives=lambda: (1 << 2) | (1 << 25)))
        with patch.object(ctypes, 'windll', backend, create=True), \
             patch.object(Path, 'exists', side_effect=AssertionError('No drive probing')), \
             patch.object(Path, 'is_dir', side_effect=AssertionError('No drive probing')):
            self.assertEqual(browser._windows_roots(), [{'name': 'C:', 'path': 'C:\\'}, {'name': 'Z:', 'path': 'Z:\\'}])

    def test_symlink_or_reparse_children_are_skipped(self):
        @contextmanager
        def scanning(path):
            yield iter([SimpleNamespace(name='link.csv', stat=lambda **_: SimpleNamespace(st_mode=0o120777)),
                        SimpleNamespace(name='junction', stat=lambda **_: SimpleNamespace(st_mode=0o040777, st_file_attributes=0x400)),
                        SimpleNamespace(name='hidden.csv', stat=lambda **_: SimpleNamespace(st_mode=0o100666, st_file_attributes=2))])
        with tempfile.TemporaryDirectory() as temp, patch('local_file_browser.os.scandir', scanning):
            result = browser.browse(Path(temp), 'segments')
        self.assertEqual(result['directories'], [])
        self.assertEqual(result['files'], [])

    def test_cloud_reparse_placeholder_is_not_confused_with_junction(self):
        regular = 0o100666
        self.assertFalse(browser._linked(SimpleNamespace(st_mode=regular, st_file_attributes=0x400,
                                                        st_reparse_tag=0x9000001A)))
        for tag in (0xA000000C, 0xA0000003):
            self.assertTrue(browser._linked(SimpleNamespace(st_mode=regular, st_file_attributes=0x400,
                                                           st_reparse_tag=tag)))

    def test_read_input_returns_original_canonical_path_and_exact_bytes(self):
        with tempfile.TemporaryDirectory(prefix='Ä Test ') as temp:
            path = Path(temp) / 'Original Daten.CSV'; raw = 'Code;Text\nA;Äußerung\n'.encode('utf-8'); path.write_bytes(raw)
            before = path.stat()
            selected, content = browser.read_input(path, len(raw))
            self.assertEqual(selected, path.resolve()); self.assertEqual(content, raw)
            self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_fresh_xlsx_and_api_specific_ctime_are_not_reported_as_changes(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.xlsx'
            book = Workbook(); book.active.append(['Code', 'Text']); book.save(path); book.close()
            expected = path.read_bytes()
            self.assertEqual(browser.read_input(path, 100000), (path.resolve(), expected))
            info = path.lstat()
            path_info = SimpleNamespace(**{name: getattr(info, name) for name in
                ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_mode')}, st_ctime_ns=1)
            with patch.object(Path, 'lstat', return_value=path_info):
                self.assertEqual(browser.read_input(path, 100000), (path.resolve(), expected))

    def test_oversized_file_is_rejected_without_open_and_bad_kinds_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'big.csv'; path.write_bytes(b'x' * 5000)
            with patch.object(Path, 'open', side_effect=AssertionError('Must not read oversized data')):
                with self.assertRaisesRegex(ValueError, 'Größenlimit'): browser.read_input(path, 10)
            for value in (0, -1, True, '10'):
                with self.assertRaises(ValueError): browser.read_input(path, value)
            for value in ('relative.csv', path.with_suffix('.txt'), Path(temp), path.with_name('missing.csv')):
                with self.assertRaises(ValueError): browser.read_input(value, 100)

    def test_file_read_is_bounded_and_detects_change_during_read(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.csv'; path.write_bytes(b'original')
            before = path.stat()
            real_open = Path.open; requested = []
            @contextmanager
            def opened(selected, mode):
                with real_open(selected, mode) as handle:
                    def read(limit):
                        requested.append(limit)
                        result = handle.read(limit)
                        # Same length but changed timestamps/content after read.
                        with real_open(path, 'wb') as writer: writer.write(b'changed!')
                        # Filesystem timestamp/writeback granularity must not
                        # make the mutation fixture nondeterministic.
                        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
                        return result
                    yield SimpleNamespace(fileno=handle.fileno, read=read)
            with patch.object(Path, 'open', opened), self.assertRaisesRegex(ValueError, 'verändert'):
                browser.read_input(path, 20)
            self.assertEqual(requested, [21])

    def test_read_rejects_symlink_regular_file_replacement_and_permission_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.csv'; path.write_bytes(b'original')
            with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=0o120777)):
                with self.assertRaisesRegex(ValueError, 'Verknüpfungen'): browser.read_input(path, 20)
            with patch.object(Path, 'open', side_effect=PermissionError('private detail')):
                with self.assertRaisesRegex(ValueError, 'Zugriffsrechte') as caught: browser.read_input(path, 20)
                self.assertNotIn('private detail', str(caught.exception))


if __name__ == '__main__': unittest.main()
