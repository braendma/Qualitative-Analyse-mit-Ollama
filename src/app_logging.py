"""Small technical lifecycle log with an allowlisted, message-free error schema."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import sys
import traceback


class _QuietRotatingHandler(RotatingFileHandler):
    def __init__(self, path, warning, max_bytes, backup_count):
        self.warning = warning
        super().__init__(path, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')

    def handleError(self, record):
        # logging's default error handler prints the entire record/exception.
        # Neither belongs in this technical log or its fallback console notice.
        self.warning()


def _label(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.<>-]{1,100}', value) else '<unknown>'


class AppLog:
    """Not a global/root logger; never collects scientific or HTTP log records."""
    def __init__(self, data_dir, version_path=None, *, max_bytes=1024 * 1024, backup_count=3):
        self.handler = None
        self.warned = False
        self.version = 'unknown'
        if version_path is not None:
            try:
                version = Path(version_path).read_text(encoding='utf-8').strip()
                if re.fullmatch(r'[0-9][0-9A-Za-z.+-]{0,63}', version):
                    self.version = version
            except (OSError, UnicodeError):
                pass
        try:
            folder = Path(data_dir) / 'logs'
            folder.mkdir(parents=True, exist_ok=True)
            self.handler = _QuietRotatingHandler(folder / 'app.log', self._warn, max_bytes, backup_count)
            self.handler.setFormatter(logging.Formatter('%(message)s'))
        except Exception:
            self._warn()

    def _warn(self):
        if self.warned:
            return
        self.warned = True
        try:
            print('Technisches App-Protokoll ist nicht verfügbar. Die Anwendung läuft weiter.', file=sys.stderr)
        except Exception:
            pass

    def event(self, name, error=None):
        if self.handler is None or name not in {'start', 'closed', 'unhandled_error'}:
            return
        try:
            record = {'timestamp': datetime.now(timezone.utc).isoformat(),
                      'event': name, 'version': self.version}
            if name == 'unhandled_error' and isinstance(error, BaseException):
                record['exception_type'] = _label(type(error).__name__)
                record['frames'] = [
                    {'file': _label(frame.f_code.co_filename.replace('\\', '/').rsplit('/', 1)[-1]),
                     'function': _label(frame.f_code.co_name), 'line': lineno}
                    for frame, lineno in traceback.walk_tb(error.__traceback__)
                ][-20:]
            # No args, exc_info, stack_info, arbitrary context or exception text.
            entry = logging.LogRecord('app_lifecycle', logging.INFO, '', 0,
                                      json.dumps(record, ensure_ascii=True), (), None)
            self.handler.handle(entry)
        except Exception:
            self._warn()

    def close(self):
        if self.handler is not None:
            try:
                self.handler.close()
            except Exception:
                self._warn()
            finally:
                self.handler = None
