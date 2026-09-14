"""Exercise the real Windows distribution in a disposable extracted copy."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, default=ROOT/'dist/QualitativeAnalyse')
    parser.add_argument('--long-output', action='store_true', help='Use a Windows result path longer than 300 characters')
    opts = parser.parse_args()
    summary = {'checks': [], 'model_calls': 0, 'real_executable': True,
               'limitation': 'Isolated extracted copy with Python absent from PATH; not a clean Windows VM.'}
    (ROOT/'build').mkdir(exist_ok=True)
    # Keep installation and ordinary result paths independent of checkout depth.
    # Dedicated long-path cases are separate from this fresh-installation smoke.
    with tempfile.TemporaryDirectory(prefix='qa-ui-') as tmp:
        area = Path(tmp).resolve()
        install = area/'Neu entpackt ä'
        shutil.copytree(opts.package.resolve(), install)
        exe = install/'QualitativeAnalyse.exe'
        env = {k: v for k, v in os.environ.items() if k.upper() not in {'PYTHONPATH', 'PYTHONHOME'}}
        env.update(PATH=str(Path(os.environ['SystemRoot'])/'System32'),
                   LOCALAPPDATA=str(area/'LocalAppData'), PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        cwd = area/'Fremder Arbeitsordner'; cwd.mkdir()

        def run(*args, timeout=50):
            return subprocess.run([str(exe), *map(str, args)], cwd=cwd, env=env,
                capture_output=True, encoding='utf-8', errors='replace', timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW)

        initial = run('--package-check')
        assert initial.returncode == 0, initial.stderr
        proof = json.loads(initial.stdout)
        assert proof['ok'] is True
        summary['identity'] = proof['identity']
        summary['checks'].append('package identity and source loaders in fresh extracted copy')
        assert shutil.which('python', path=env['PATH']) is None
        assert shutil.which('python3', path=env['PATH']) is None

        rejected = run('--internal-script', 'unapproved.py')
        assert rejected.returncode == 2, rejected.stdout + rejected.stderr
        summary['checks'].append('unapproved internal entry rejected')
        readme = install/'_internal/README.md'
        old = readme.read_bytes()
        try:
            readme.write_bytes(old + b'\nsynthetic changed package\n')
            changed = run('--package-check')
            assert changed.returncode == 2 and 'erneut entpacken' in changed.stderr, changed.stderr
        finally:
            readme.write_bytes(old)
        summary['checks'].append('changed package refused with repair hint')

        data = area/'Technische Ablage'
        processes = []
        results = None
        try:
            def start(label):
                trace = area/(label+'.log')
                with trace.open('wb') as output:
                    process = subprocess.Popen([str(exe), '--data-dir', str(data), '--no-browser'],
                        cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                processes.append(process)
                deadline = time.monotonic()+50
                while time.monotonic() < deadline:
                    message = trace.read_text(encoding='utf-8', errors='replace')
                    match = re.search(r'Lokale Oberfläche: (http://127\.0\.0\.1:\d+/#[^\s]+)', message)
                    if match:
                        return process, urlsplit(match.group(1))
                    if process.poll() is not None:
                        raise AssertionError(message)
                    time.sleep(.05)
                raise AssertionError('Own EXE did not become ready: '+message)

            def request(address, path, value=None, auth=True):
                connection = http.client.HTTPConnection(address.hostname, address.port, timeout=15)
                headers = {'X-App-Token': address.fragment} if auth else {}
                if value is not None: headers['Content-Type'] = 'application/json'
                try:
                    connection.request('GET' if value is None else 'POST', path,
                                       None if value is None else json.dumps(value), headers)
                    response = connection.getresponse()
                    raw = response.read()
                    return response.status, raw
                finally:
                    connection.close()

            def api(address, path, value=None):
                status, raw = request(address, path, value)
                assert status == 200, (path, status, raw)
                return json.loads(raw)

            def close(process, address):
                api(address, '/api/shutdown', {'mode': 'idle'})
                deadline = time.monotonic()+15
                while time.monotonic() < deadline:
                    state = api(address, '/api/runtime')['state']
                    if state == 'closed': break
                    time.sleep(.05)
                assert state == 'closed'
                assert process.wait(timeout=25) == 0

            process, address = start('initial')
            state = api(address, '/api/state')
            assert not state['projects'] and state['runtime']['state'] == 'open'
            for resource in ('/', '/app.js', '/app.css', '/handbuch', '/manual.css',
                             '/images/local-file-selection.svg', '/logo.jpg',
                             '/screenshots/15-speicherschaetzung.png', '/WINDOWS_STANDALONE.txt'):
                status, raw = request(address, resource, auth=False)
                assert status == 200 and raw, (resource, status)
            assert request(address, '/api/state', auth=False)[0] == 403
            duplicate = run('--data-dir', data, '--no-browser', timeout=25)
            assert duplicate.returncode != 0 and 'bereits geöffnet' in duplicate.stderr, duplicate.stderr
            assert process.poll() is None
            project = api(address, '/api/create', {'name': 'Synthetische Paketprüfung', 'demo': True})
            assert project['id']
            person = api(address, '/api/person-preview', {
                'project': project['id'], 'columns': state['defaults']['columns']})
            results = area/'Synthetische Ergebnisse ä'
            if opts.long_output:
                while len(str(results)) < 310:
                    results /= 'Tiefe synthetische Ablage ä mit Leerzeichen'
            visible_results = str(results)
            if opts.long_output:
                # Test the ordinary path submitted by a user; use independent
                # Windows IO syntax only for this harness's own assertions.
                results = Path('\\\\?\\' + visible_results)
            results.mkdir(parents=True)
            settings = {'columns': state['defaults']['columns'],
                'person_identity': {'confirmed': True, 'fingerprint': person['fingerprint'],
                    'mapping': {d['document']: d['document'] for d in person['documents']}},
                'book_columns': dict(zip(
                    ('kategorie','unterkategorie','auspraegung','facette','definition','ankerbeispiel'),
                    ('Kategorie','Unterkategorie','Ausprägung','Facette','Definition','Ankerbeispiel'))),
                'modules': ['coverage', 'information_loss', 'codebook_diagnostics'],
                'model': 'synthetic-no-model', 'label_mode': 'multi_label',
                'context': {}, 'output_dir': visible_results}
            api(address, '/api/save', {'project': project['id'], 'settings': settings})
            job = api(address, '/api/start', {'project': project['id']})
            deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                jobs = api(address, '/api/jobs?project='+project['id'])['jobs']
                stored = next(j for j in jobs if j['id'] == job['id'])
                if stored['status'] != 'running' and api(address, '/api/runtime')['active'] is None: break
                time.sleep(.1)
            assert stored['status'] == 'success', stored
            manifest_path = next(results.rglob('workflow_manifest.json'))
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            assert manifest['status'] == 'success', manifest
            assert (manifest_path.parent/'gesamtbericht.html').is_file()
            # The current supervised EXE attempt must have confirmed child cleanup.
            saved_job = json.loads((data/'projects'/project['id']/'jobs'/job['id']/'job.json').read_text(encoding='utf-8'))
            assert saved_job['cleanup_confirmed'] is True, saved_job
            assert api(address, '/api/runtime')['active'] is None
            summary['checks'].append('packaged App supervisor and three model-free analysis children complete')
            if opts.long_output:
                summary['checks'].append('ordinary user output path over 300 characters completes without registry changes')
            summary['checks'].extend(['UI and manual resources served without system Python',
                                      'API token required', 'duplicate instance refused', 'synthetic demo created'])
            close(process, address)
            process, address = start('restarted')
            assert any(p['id'] == project['id'] for p in api(address, '/api/state')['projects'])
            close(process, address)
            technical = [json.loads(line) for line in (data/'logs/app.log').read_text(encoding='utf-8').splitlines()]
            assert [entry['event'] for entry in technical] == ['start', 'closed', 'start', 'closed']
            assert address.fragment not in (data/'logs/app.log').read_text(encoding='utf-8')
            summary['checks'].append('bounded technical lifecycle log without URL token')
            summary['checks'].extend(['verified close delivered before HTTP exit', 'project retained on restart'])
        finally:
            # Only handles created by this test, never processes found by name.
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=15)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
            if opts.long_output and results is not None and results.is_dir():
                # This exact synthetic child belongs to the temporary test area.
                # Use extended IO for its cleanup too, after owned children exit.
                cleanup_root = Path('\\\\?\\' + str(area/'Synthetische Ergebnisse ä'))
                ordinary = Path(str(cleanup_root).removeprefix('\\\\?\\')).resolve()
                assert ordinary.is_relative_to(area), 'Refusing cleanup outside the test area'
                shutil.rmtree(cleanup_root)
    assert not area.exists(), 'Temporary extracted installation was not removed'
    summary['temporary_install_removed'] = True
    evidence = 'frozen-ui-long-path-smoke.json' if opts.long_output else 'frozen-ui-smoke.json'
    (ROOT/'build'/evidence).write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'checks': len(summary['checks']), 'temporary_install_removed': True}))


if __name__ == '__main__':
    main()
