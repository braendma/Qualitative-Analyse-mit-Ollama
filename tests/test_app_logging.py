"""Technical log retention and privacy; no application/network/model processes."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app_logging import AppLog
import local_app


class AppLoggingTests(unittest.TestCase):
    def read_logs(self, directory):
        return [json.loads(line) for path in sorted((Path(directory) / 'logs').glob('app.log*'))
                for line in path.read_text(encoding='utf-8').splitlines()]

    def test_private_exception_message_context_and_paths_are_absent(self):
        secret = 'sk-synthetic-secret-NOT-TO-LOG'
        interview = 'Ich habe vertrauliche Interviewdetails genannt.'
        url = 'http://127.0.0.1:12345/#synthetic-session-secret'
        with tempfile.TemporaryDirectory() as tmp:
            log = AppLog(tmp)
            try:
                try:
                    raise ValueError(secret + ' ' + url)
                except ValueError as first:
                    raise RuntimeError(interview + ' ' + tmp) from first
            except RuntimeError as error:
                log.event('unhandled_error', error)
            log.event(secret)  # Unknown event names cannot become log messages.
            log.close()
            path = Path(tmp) / 'logs' / 'app.log'
            raw = path.read_text(encoding='utf-8')
            for private in (secret, interview, url, tmp):
                self.assertNotIn(private, raw)
            rows = self.read_logs(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['exception_type'], 'RuntimeError')
            self.assertEqual(set(rows[0]), {'timestamp', 'event', 'version', 'exception_type', 'frames'})
            frame = rows[0]['frames'][-1]
            self.assertEqual(set(frame), {'file', 'function', 'line'})
            self.assertEqual(frame['file'], 'test_app_logging.py')
            self.assertEqual(frame['function'], 'test_private_exception_message_context_and_paths_are_absent')
            self.assertGreater(frame['line'], 0)

    def test_selected_folder_rotation_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            version = Path(tmp) / 'VERSION'; version.write_text('0.4.0-beta.1', encoding='utf-8')
            selected = Path(tmp) / 'chosen app data'
            log = AppLog(selected, version, max_bytes=350, backup_count=2)
            for _ in range(30):
                log.event('start')
            log.event('closed'); log.close()
            self.assertEqual({p.name for p in (selected / 'logs').iterdir()}, {'app.log', 'app.log.1', 'app.log.2'})
            rows = self.read_logs(selected)
            self.assertLess(len(rows), 31)
            self.assertTrue(all(row['version'] == '0.4.0-beta.1' for row in rows))
            self.assertEqual(json.loads((selected / 'logs' / 'app.log').read_text().splitlines()[-1])['event'], 'closed')

    def test_unavailable_log_folder_is_nonfatal_and_warns_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'logs').write_text('synthetic preserved file', encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                log = AppLog(tmp); log.event('start'); log.event('closed'); log.close()
            self.assertEqual(stderr.getvalue().count('Technisches App-Protokoll'), 1)
            self.assertNotIn(tmp, stderr.getvalue())
            self.assertEqual((Path(tmp) / 'logs').read_text(), 'synthetic preserved file')

    def test_rotation_write_failure_does_not_print_record_or_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AppLog(tmp)
            with patch.object(log.handler, 'shouldRollover', side_effect=OSError('sk-secret interview text')), \
                    contextlib.redirect_stderr(io.StringIO()) as stderr:
                log.event('start'); log.event('closed')
            log.close()
            self.assertEqual(stderr.getvalue().count('Technisches App-Protokoll'), 1)
            self.assertNotIn('sk-secret', stderr.getvalue())
            self.assertNotIn('interview text', stderr.getvalue())

    def test_main_default_source_uses_chosen_data_dir_and_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'source-default'
            app = MagicMock(); app.runtime_status.return_value = {'state': 'closed'}
            server = MagicMock(); server.server_port = 12345; server.token = 'private-session-token'
            with patch.object(sys, 'argv', ['local_app.py', '--no-browser']), \
                    patch.object(local_app, 'default_data_dir', return_value=directory), \
                    patch.object(local_app, 'App', return_value=app) as construct, \
                    patch.object(local_app, 'make_server', return_value=server), \
                    contextlib.redirect_stdout(io.StringIO()):
                local_app.main()
            construct.assert_called_once_with(directory.resolve(), None, project_root=Path.home()/"Documents"/"Qualitative Analyse"/"Projekte")
            self.assertEqual([row['event'] for row in self.read_logs(directory)], ['start', 'closed'])
            self.assertNotIn(server.token, (directory / 'logs' / 'app.log').read_text())
            server.server_close.assert_called_once()

    def test_main_unhandled_failure_is_logged_without_changing_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            problem = ValueError('synthetic API key and interview text must stay out')
            with patch.object(sys, 'argv', ['local_app.py', '--data-dir', tmp]), \
                    patch.object(local_app, 'App', side_effect=problem):
                with self.assertRaises(ValueError) as caught:
                    local_app.main()
            self.assertIs(caught.exception, problem)
            rows = self.read_logs(tmp)
            self.assertEqual([row['event'] for row in rows], ['start', 'unhandled_error'])
            self.assertEqual(rows[-1]['exception_type'], 'ValueError')
            self.assertNotIn(str(problem), (Path(tmp) / 'logs' / 'app.log').read_text())
            # The failure path releases the selected instance lock as before.
            with local_app.exclusive_file_lock(Path(tmp) / '.app-instance.lock'):
                pass

    def test_busy_instance_does_not_create_or_append_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with local_app.exclusive_file_lock(Path(tmp) / '.app-instance.lock'), \
                    patch.object(sys, 'argv', ['local_app.py', '--data-dir', tmp]), \
                    patch.object(local_app, 'App') as app, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    local_app.main()
            self.assertEqual(caught.exception.code, 2)
            self.assertFalse((Path(tmp) / 'logs').exists())
            app.assert_not_called()


if __name__ == '__main__':
    unittest.main()
