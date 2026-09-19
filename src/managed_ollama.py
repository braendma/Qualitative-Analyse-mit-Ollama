"""A workflow-owned, loopback-only Ollama server with explicit request slots.

The supervisor holds a stdin lease: even an abruptly terminated workflow closes
the pipe and causes its server tree to be stopped. Existing servers are untouched.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
from process_commands import python_command
import sys
import threading
import time
import urllib.request

HOST_ENV = 'QUALITATIVE_MANAGED_OLLAMA_HOST'


def workers(settings):
    value = settings.get('parallel_workers', 1)
    if type(value) is not int or not 1 <= value <= 8:
        raise ValueError('Parallelität muss eine ganze Zahl zwischen 1 und 8 sein.')
    from llm_providers import transport_selection
    if value > 1 and transport_selection(settings, settings['model'])['provider'] != 'ollama_local':
        raise ValueError('Parallele Verarbeitung ist derzeit nur für lokales Ollama verfügbar.')
    return value


def executable():
    found = shutil.which('ollama')
    if not found and os.name == 'nt':
        candidate = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/ollama.exe'
        if candidate.is_file(): found = str(candidate)
    if not found:
        raise ValueError('Ollama-Programm nicht gefunden. Ollama installieren oder eine Anfrage auswählen.')
    return found


def preflight(settings):
    count = workers(settings)
    if count > 1:
        executable()
        from ollama_capacity import check
        result = check(settings)
        maximum = result.get('estimated_parallel')
        if maximum is None or count > maximum:
            prefix = f"Parallelstart mit {count} Anfragen für {settings.get('model', '')} nicht freigegeben: "
            detail = result['reason']
            if maximum is not None:
                detail += (f" Gewählt: {settings.get('num_ctx', '?')} Tokens je Anfrage; "
                           f'aktuell geschätzt: {maximum} gleichzeitige Anfragen. '
                           'Parallelität reduzieren oder Kontext und Speicherbelegung prüfen. '
                           'Die Eingabeprüfung muss auch mit einem kleineren Kontext bestehen.')
            raise ValueError(prefix + detail)
    return count


class ManagedOllama:
    def __init__(self, settings, directory):
        self.settings, self.directory = settings, Path(directory)
        self.process = self.log = None
        self.host = None

    def start(self):
        # Never trust a host override inherited from an earlier workflow.
        os.environ.pop(HOST_ENV, None)
        count = preflight(self.settings)
        if count == 1: return {'parallel_workers': 1, 'managed': False}
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.host = f'http://127.0.0.1:{port}'
        env = dict(os.environ)
        # Match the cache layout used by the user's existing Ollama installation.
        env.update(OLLAMA_HOST=self.host, OLLAMA_NUM_PARALLEL=str(count),
                   OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_NO_CLOUD='1',
                   OLLAMA_CONTEXT_LENGTH=str(self.settings['num_ctx']),
                   OLLAMA_KV_CACHE_TYPE='f16', OLLAMA_DEBUG='false')
        for key in ('OLLAMA_API_KEY', 'OLLAMA_ORIGINS', HOST_ENV): env.pop(key, None)
        self.log = (self.directory / 'ollama_runtime.log').open('ab')
        try:
            self.process = subprocess.Popen(python_command(Path(__file__).resolve(),
                ['--serve', executable()]), env=env, stdin=subprocess.PIPE, stdout=self.log,
                stderr=subprocess.STDOUT, start_new_session=os.name != 'nt',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('Eigene Ollama-Instanz konnte nicht starten. ollama_runtime.log prüfen.')
                try:
                    with opener.open(self.host + '/api/tags', timeout=1) as response:
                        tags = json.load(response).get('models', [])
                    name = self.settings['model']
                    canonical = name if ':' in name.rsplit('/', 1)[-1] else name + ':latest'
                    if not any(t.get('name') in (name, canonical) and not t.get('remote_host') for t in tags):
                        raise ValueError('Modell fehlt im lokalen Cache der eigenen Ollama-Instanz. OLLAMA_MODELS prüfen.')
                    os.environ[HOST_ENV] = self.host
                    return {'parallel_workers': count, 'managed': True, 'host': self.host,
                            'context_per_request': self.settings['num_ctx']}
                except OSError:
                    time.sleep(.2)
            raise RuntimeError('Eigene Ollama-Instanz antwortet nicht innerhalb von 30 Sekunden.')
        except BaseException:
            self.close()
            raise

    def close(self):
        os.environ.pop(HOST_ENV, None)
        if self.process:
            if self.process.stdin: self.process.stdin.close()
            try: self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                stop_tree(self.process)
                self.process.wait(timeout=10)
            self.process = None
        if self.log: self.log.close(); self.log = None


def stop_tree(process):
    if process.poll() is not None: return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
    else:
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass


def supervise(program):
    return supervise_command([program, 'serve'])


def supervise_command(command, receipt_path=None, ticket=None):
    """Reuse the stdin lease for model servers and diagnostic runner trees."""
    from runtime_support import atomic_json, fingerprint
    import errno
    job = child = None
    spawn_attempted = no_child_started = False
    primary_error = None
    record = {'schema_version': 1, 'ticket': ticket, 'command_sha256': fingerprint(command),
              'supervisor_pid': os.getpid(), 'status': 'starting', 'cleanup_confirmed': False}
    def save():
        if receipt_path:
            atomic_json(receipt_path, record)
    released = threading.Event()
    def lease():
        try:
            while os.read(sys.stdin.fileno(), 1024):
                pass
        finally:
            released.set()
    code = 130
    try:
        save()
        if os.name == 'nt':
            from windows_process_job import SupervisorJob
            job = SupervisorJob()  # Containment must succeed before spawning children.
        threading.Thread(target=lease, daemon=True).start()
        spawn_attempted = True
        try:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                start_new_session=os.name != 'nt', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except OSError as exc:
            # These OS launch failures cannot leave an executed command behind.
            # An arbitrary constructor exception is not such a proof; Windows
            # can still authoritatively inspect its already established job.
            no_child_started = isinstance(exc, (FileNotFoundError, PermissionError, NotADirectoryError)) or exc.errno == errno.ENOEXEC
            raise
        record.update(child_pid=child.pid, status='running'); save()
        while not released.wait(.2):
            if child.poll() is not None:
                code = child.returncode
                break
    except BaseException as exc:
        primary_error, code = exc, 1
    finally:
        cleanup_error = None
        confirmed = False
        try:
            if job:
                job.stop_descendants()
            elif child:
                # The leader may have exited while a module in its group remains.
                try: os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
            if child:
                child.wait(timeout=10)
                if not job:
                    deadline = time.monotonic() + 5
                    while True:
                        try: os.killpg(child.pid, 0)
                        except ProcessLookupError: break
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Prozessgruppe noch nicht vollständig beendet; Abschluss nicht bestätigt.')
                        try: os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError: break
                        time.sleep(.05)
            confirmed = bool(job or child or not spawn_attempted or no_child_started)
        except BaseException as exc:
            cleanup_error = exc
        record.update(status='finished' if confirmed else 'cleanup_unconfirmed', exit_code=code,
                      cleanup_confirmed=confirmed, cleanup_scope='windows_job' if os.name == 'nt' else 'process_group',
                      parent_released=released.is_set())
        if child is None:
            record['child_start'] = 'not_started' if not spawn_attempted or no_child_started else 'unknown'
        try:
            save()
        except BaseException as exc:
            cleanup_error = cleanup_error or exc
        if primary_error is not None and cleanup_error is not None:
            # Python 3.10 remains supported; notes were introduced in 3.11.
            add_note = getattr(primary_error, 'add_note', None)
            if add_note:
                add_note('Zusätzlich konnte der Abschlussnachweis nicht sicher geschrieben oder bestätigt werden.')
        elif cleanup_error is not None:
            primary_error = cleanup_error
    if primary_error is not None:
        raise primary_error
    return code


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--serve':
        raise SystemExit(supervise(sys.argv[2]))
    if len(sys.argv) >= 5 and sys.argv[1] == '--command':
        raise SystemExit(supervise_command(sys.argv[4:], sys.argv[2], sys.argv[3]))
    raise SystemExit(2)
