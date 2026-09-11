"""Exercise the actual Mac launcher without browser, model or permanent data."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='Mac setup test ') as tmp:
        # Exercise installation paths containing spaces (common on user Macs).
        link = Path(tmp) / 'Program with spaces'
        link.symlink_to(ROOT, target_is_directory=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        with (Path(tmp) / 'server.log').open('w+') as log:
            process = subprocess.Popen(
                ['bash', str(link / 'start/macos/Start_Oberflaeche.command'),
                 '--no-browser', '--port', str(port), '--data-dir', str(Path(tmp) / 'Private data')],
                cwd=tmp, stdout=log, stderr=subprocess.STDOUT,
                env={**os.environ, 'CI': 'true'}, start_new_session=True)
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError('Launcher exited before serving the UI')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
                            assert response.status == 200
                            assert b'<html' in response.read().lower()
                        print('Mac launcher: HTTP 200, HTML UI, paths with spaces, isolated data directory')
                        return
                    except OSError:
                        time.sleep(0.3)
                raise AssertionError('Local UI did not become ready')
            except Exception:
                log.flush(); log.seek(0)
                print(log.read())
                raise
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
