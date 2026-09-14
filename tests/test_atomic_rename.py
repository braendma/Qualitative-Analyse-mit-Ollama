"""Atomic writes survive brief Windows readers, never persistent denial."""
import os
from pathlib import Path
import sys
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import runtime_support as runtime
from filesystem_paths import io_path


def permission_error(code):
    error = PermissionError('Synthetic rename denied')
    error.winerror = code
    return error


class AtomicRenameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='atomic rename ä ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # tempfile's Windows cleanup starts from an ordinary path. Delete our
        # own known root through IO syntax first so deep test data is removed.
        self.addCleanup(lambda: shutil.rmtree(io_path(self.root)) if io_path(self.root).exists() else None)
        self.path = self.root / 'workflow_manifest.json'
        self.path.write_text('original\n', encoding='utf-8')

    def os_proxy(self, replace, platform='nt'):
        # Change only runtime_support's OS view, not pathlib/tempfile's platform.
        return SimpleNamespace(name=platform, replace=replace, fdopen=os.fdopen,
            fsync=Mock(wraps=os.fsync), path=os.path, unlink=Mock(wraps=os.unlink))

    def test_short_transient_denials_replace_same_fsynced_file_without_rewriting(self):
        attempts = []
        real_replace = os.replace
        def replace(source, destination):
            attempts.append((str(source), io_path(source).read_bytes()))
            if len(attempts) < 3:
                raise permission_error(32)
            real_replace(source, destination)
        proxy = self.os_proxy(replace)
        with patch.object(runtime, 'os', proxy), patch.object(runtime.time, 'sleep') as sleep:
            runtime.atomic_text(self.path, 'new ä\n')
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'new ä\n')
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(set(attempts)), 1)
        self.assertEqual(attempts[0][1], 'new ä\n'.encode('utf-8'))
        self.assertEqual(proxy.fsync.call_count, 1)
        self.assertEqual(sleep.call_count, 2)
        proxy.unlink.assert_not_called()
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_persistent_denial_has_bounded_deadline_preserves_original_and_cleans_temp(self):
        for code in (5, 32, 33):
            with self.subTest(winerror=code):
                elapsed = [0.0]
                attempts = []
                error = permission_error(code)
                def deny(source, destination):
                    attempts.append((str(source), io_path(source).read_bytes()))
                    raise error
                def sleep(seconds):
                    elapsed[0] += seconds
                proxy = self.os_proxy(deny)
                with patch.object(runtime, 'os', proxy), \
                     patch.object(runtime.time, 'monotonic', side_effect=lambda: elapsed[0]), \
                     patch.object(runtime.time, 'sleep', side_effect=sleep), \
                     self.assertRaises(PermissionError) as caught:
                    runtime.atomic_text(self.path, 'must not replace original')
                self.assertIs(caught.exception, error)
                self.assertAlmostEqual(elapsed[0], .75)
                self.assertGreater(len(attempts), 1)
                self.assertLessEqual(len(attempts), 17)
                self.assertEqual(len(set(attempts)), 1)
                self.assertEqual(self.path.read_text(encoding='utf-8'), 'original\n')
                self.assertEqual(proxy.fsync.call_count, 1)
                proxy.unlink.assert_called_once()
                self.assertFalse(list(self.root.glob('*.tmp')))

    def test_unrelated_errors_and_non_windows_permissions_are_not_retried(self):
        cases = [('nt', permission_error(87)), ('nt', PermissionError('No winerror')),
                 ('nt', FileNotFoundError('Missing parent')), ('posix', permission_error(5))]
        for platform, error in cases:
            with self.subTest(platform=platform, error=type(error).__name__):
                replace = Mock(side_effect=error)
                proxy = self.os_proxy(replace, platform)
                with patch.object(runtime, 'os', proxy), \
                     patch.object(runtime.time, 'sleep') as sleep, \
                     self.assertRaises(type(error)) as caught:
                    runtime.atomic_text(self.path, 'uncommitted')
                self.assertIs(caught.exception, error)
                replace.assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(self.path.read_text(encoding='utf-8'), 'original\n')
                self.assertFalse(list(self.root.glob('*.tmp')))

    @unittest.skipUnless(os.name == 'nt', 'Windows reader/delete sharing contract')
    def test_real_held_reader_releases_then_atomic_replace_succeeds(self):
        for directory in (self.root, self.root.joinpath(*(['synthetic long folder ä'] * 9))):
            with self.subTest(deep=directory != self.root):
                path = io_path(directory / 'reader_manifest.json')
                runtime.atomic_text(path, 'original\n')
                ready, release = threading.Event(), threading.Event()
                errors = []
                def reader():
                    try:
                        with path.open('rb') as handle:
                            self.assertEqual(handle.read(), b'original\n')
                            ready.set()
                            if not release.wait(3):
                                raise TimeoutError('Test release signal missing')
                            time.sleep(.10)
                    except BaseException as exc:
                        errors.append(exc)
                        ready.set()
                thread = threading.Thread(target=reader)
                thread.start()
                failures, attempts = [], []
                real_replace = os.replace
                def replace(source, destination):
                    attempts.append((str(source), io_path(source).read_bytes()))
                    try:
                        return real_replace(source, destination)
                    except PermissionError as exc:
                        failures.append(exc.winerror)
                        self.assertEqual(path.read_bytes(), b'original\n')
                        release.set()
                        raise
                try:
                    self.assertTrue(ready.wait(2))
                    self.assertFalse(errors)
                    with patch.object(runtime, 'os', self.os_proxy(replace)):
                        runtime.atomic_text(path, 'completed ä\n')
                finally:
                    release.set()
                    thread.join(timeout=4)
                self.assertFalse(thread.is_alive())
                self.assertFalse(errors)
                self.assertTrue(failures, 'An actual open reader must deny the first rename')
                self.assertTrue(all(code in (5, 32, 33) for code in failures))
                self.assertGreater(len(attempts), 1)
                self.assertEqual(len(set(attempts)), 1)
                self.assertEqual(path.read_text(encoding='utf-8'), 'completed ä\n')
                self.assertFalse(list(path.parent.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
