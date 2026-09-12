"""Start the Windows package in an isolated folder, without browser or model calls."""
from pathlib import Path
import os,socket,subprocess,sys,tempfile,time,urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='Windows UI with spaces ') as tmp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        with (Path(tmp)/'server.log').open('w+') as log:
            process=subprocess.Popen([sys.executable,'-X','utf8',str(ROOT/'src/local_app.py'),
                '--no-browser','--port',str(port),'--data-dir',str(Path(tmp)/'Private data')],
                cwd=tmp,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                deadline=time.monotonic()+35
                while time.monotonic()<deadline:
                    if process.poll() is not None:raise AssertionError('UI exited before serving')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=2) as r:
                            assert r.status==200 and b'prompt-dialog' in r.read()
                        print('Windows UI: HTTP 200, prompt dialog, isolated data path with spaces')
                        return
                    except OSError:time.sleep(.2)
                raise AssertionError('UI startup timed out')
            finally:
                if process.poll() is None:process.terminate()
                process.wait(timeout=10)

if __name__=='__main__':main()
