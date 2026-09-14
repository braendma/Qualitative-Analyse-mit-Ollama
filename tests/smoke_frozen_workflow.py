"""Opt-in real Windows EXE workflow smoke. Synthetic material only.

This script does not build/install anything.
The harness needs PyYAML/openpyxl; the EXE children receive no Python in PATH.
Evidence stays in a new workspace-local directory; no directory is deleted.
"""
import argparse
import csv
import ctypes
from ctypes import wintypes
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import openpyxl
import yaml


BASE = Path(__file__).resolve().parents[1]
ROWS = [
    ['ID', 'Person', 'Code', 'Text'],
    ['s1', 'P1', 'A > B > C > positiv', 'Das Üben hilft; das Beispiel ist verständlich.'],
    ['s2', 'P2', 'A > B > C > negativ', 'Die Anleitung bleibt unklar.\nEin Beispiel würde helfen.'],
    ['s3', 'P1', 'A > B > C > positiv', 'Mit Rückfragen verstehe ich den Ablauf besser.'],
]
BOOK = 'Code;Definition;Ankerbeispiel\nA > B > C > positiv;Hilfreiches Lernen;Das Üben hilft.\nA > B > C > negativ;Unklare Anleitung;Die Anleitung bleibt unklar.\n'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


class OwnedJob:
    """Contain only this harness's child, never attach to an unrelated process."""
    def __init__(self):
        self.kernel = k = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ):
            getattr(k, name).argtypes = args
            getattr(k, name).restype = result
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('min_working', ctypes.c_size_t),
                        ('max_working', ctypes.c_size_t), ('active_limit', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended(); limits.basic.flags = 0x2000
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def attach(self, process):
        # Popen's retained process handle binds ownership; no PID-name matching.
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.terminate(); process.wait(timeout=10)
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def environment(root):
    allowed = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    for name in ('empty-path', 'home', 'temp', 'cache'):
        (root / name).mkdir()
    env.update(PATH=str(root / 'empty-path'), USERPROFILE=str(root / 'home'),
               HOME=str(root / 'home'), TEMP=str(root / 'temp'), TMP=str(root / 'temp'),
               LOCALAPPDATA=str(root / 'appdata-not-used-by-cli'), APPDATA=str(root / 'roaming'),
               MPLCONFIGDIR=str(root / 'cache'), MPLBACKEND='Agg', PYTHONUTF8='1')
    require('PYTHONPATH' not in env and 'PYTHONHOME' not in env, 'Inherited Python environment')
    return env


def launch(exe, args, cwd, env, stdout, stderr):
    job = OwnedJob()
    try:
        process = subprocess.Popen([str(exe), *map(str, args)], cwd=cwd, env=env,
                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        job.attach(process)
        return process, job
    except BaseException:
        job.close()
        raise


def cli(exe, config, args, cwd, env, logs, label, timeout):
    with (logs / (label + '.stdout.txt')).open('wb') as out, (logs / (label + '.stderr.txt')).open('wb') as err:
        process, job = launch(exe, ['--internal-script', '00_WORKFLOW_RUNNER.py', '--config', config, *args], cwd, env, out, err)
        try:
            code = process.wait(timeout=timeout)
            require(code == 0, f'{label}: EXE exit code {code}; inspect saved stderr')
        finally:
            job.close()
            process.wait(timeout=10)
    # Embedded UTF-8 mode must work even though no external Python is on PATH.
    (logs / (label + '.stdout.txt')).read_text(encoding='utf-8')
    (logs / (label + '.stderr.txt')).read_text(encoding='utf-8')


def config_for(template, study, input_path):
    config = json.loads(json.dumps(template))
    config['paths'].update(input_csv=str(input_path), category_system_csv=str(study / 'book.csv'))
    config['columns'] = {'segment_id': 'ID', 'person': 'Person', 'code': 'Code', 'segment': 'Text'}
    config['coding_agreement']['label_mode'] = 'unspecified'
    config['context'] = {}
    config['llm']['model'] = 'synthetic-never-called'
    for module in config['pipeline']['modules']:
        module['enabled'] = module['id'] == 'coverage'
    require(any(m['id'] == 'coverage' and m.get('requires_model') is False for m in config['pipeline']['modules']), 'Model-free coverage contract missing')
    path = study / 'base.yaml'
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
    return path


def check_run(run, config, input_path, book, exe, build):
    manifest = json.loads((run / 'workflow_manifest.json').read_text(encoding='utf-8'))
    require(manifest['status'] == 'success', 'Workflow did not succeed')
    require(manifest['completed_steps'] == ['coverage'], 'Unexpected executed module')
    coverage = json.loads((run / 'coverage.json').read_text(encoding='utf-8'))
    require(coverage['model_calls'] == 0, 'Coverage reports model calls')
    require(coverage['material']['material_units'] == 3, 'Synthetic material count differs')
    require('<html' in (run / 'gesamtbericht.html').read_text(encoding='utf-8').lower(), 'HTML report missing document')
    require(len((run / 'gesamtbericht.md').read_text(encoding='utf-8').strip()) > 50, 'Markdown report empty')
    provenance = manifest['provenance']
    for key, path in [('input_sha256', input_path), ('config_sha256', config), ('codebook_sha256', book)]:
        require(provenance[key] == digest(path), 'Wrong provenance: ' + key)
    package = provenance['package']
    require(package['kind'] == 'frozen-package', 'Not frozen package provenance')
    require(package['executable_sha256'] == digest(exe), 'Wrong executable identity')
    require(package['build_input_id'] == build['build_input_id'], 'Wrong build identity')
    require(provenance['commit'] == build['source_commit'] == package['source_commit'], 'Wrong package commit')
    for relative, expected in manifest['output_hashes'].items():
        artifact = (run / relative).resolve()
        require(artifact.is_relative_to(run.resolve()), 'Output escaped run')
        require(digest(artifact) == expected, 'Output hash mismatch: ' + relative)
    for name in ('00_WORKFLOW_RUNNER.py', 'coverage_analysis.py', 'runtime_support.py'):
        require(provenance['code'][name] == build['resources']['src/' + name]['sha256'], 'Source provenance mismatch: ' + name)
    return manifest


def import_xlsx(exe, study, cwd, env, root, timeout):
    """Exercise actual bundled openpyxl through authenticated local-import API."""
    appdata = root / 'xlsx-appdata'
    stdout = root / 'logs' / 'xlsx-app.stdout.txt'
    stderr = root / 'logs' / 'xlsx-app.stderr.txt'
    with stdout.open('wb') as out, stderr.open('wb') as err:
        process, job = launch(exe, ['--no-browser', '--data-dir', appdata], cwd, env, out, err)
        try:
            deadline = time.monotonic() + timeout
            match = None
            while time.monotonic() < deadline and process.poll() is None:
                match = re.search(r'http://127\.0\.0\.1:(\d+)/#([A-Za-z0-9_-]+)', stdout.read_text(encoding='utf-8', errors='replace'))
                if match:
                    break
                time.sleep(.1)
            require(match is not None, 'EXE UI did not provide startup URL')
            port, token = int(match[1]), match[2]
            def api(path, data=None):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
                try:
                    connection.request('POST' if data is not None else 'GET', '/api/' + path,
                                       json.dumps(data) if data is not None else None,
                                       {'X-App-Token': token, 'Content-Type': 'application/json'})
                    response = connection.getresponse(); raw = response.read()
                    require(response.status == 200, f'API {path}: {response.status} {raw[:800]!r}')
                    return json.loads(raw)
                finally:
                    connection.close()
            project = api('create', {'name': 'Synthetic frozen XLSX smoke'})
            result = api('local-import', {'project': project['id'], 'kind': 'segments', 'path': str(study / 'Echte Segmente ä.xlsx')})
            upload = result['uploads']['segments']
            require(upload['format'] == 'xlsx', 'XLSX parser was not used')
            require(upload['headers'] == ROWS[0], 'XLSX headers changed')
            require(upload['source_sha256'] == digest(study / 'Echte Segmente ä.xlsx'), 'Original XLSX identity lost')
            require(Path(result['suggested_output_dir']).resolve() == study.resolve(), 'XLSX input-folder default lost')
            require(re.fullmatch('[0-9a-f]{20}', upload['id']) is not None, 'Unexpected upload id')
            normalized = appdata / 'projects' / project['id'] / 'inputs' / (upload['id'] + '.csv')
            with normalized.open(encoding='utf-8-sig', newline='') as stream:
                require(list(csv.reader(stream, delimiter=';')) == ROWS, 'XLSX values changed during real import')
            api('shutdown', {'mode': 'idle'})
            closed = False
            while time.monotonic() < deadline:
                state = api('runtime')
                if state['state'] == 'closed':
                    closed = True
                    break
                time.sleep(.1)
            require(closed, 'No confirmed cleanup before UI shutdown')
            require(process.wait(timeout=20) == 0, 'XLSX import UI exited unsuccessfully')
            stdout.read_text(encoding='utf-8')
            stderr.read_text(encoding='utf-8')
            return normalized
        finally:
            job.close()
            process.wait(timeout=10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args(argv)
    require(os.name == 'nt', 'Native Windows is required')
    exe = (args.package/'QualitativeAnalyse.exe').resolve(strict=True)
    root = BASE / 'build' / 'smoke-frozen-workflow' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    logs = root / 'logs'; logs.mkdir()
    foreign = root / 'Fremder Arbeitsordner ü'; foreign.mkdir()
    env = environment(root)
    bundle = exe.parent / '_internal'
    build = json.loads((bundle / 'packaging' / 'build-manifest.json').read_text(encoding='utf-8'))
    template = yaml.safe_load((bundle / 'config' / 'config_v2.yaml').read_text(encoding='utf-8'))
    bundle_before = {relative: digest(bundle / relative) for relative in build['resources']}
    results = {'status': 'running', 'build_input_id': build['build_input_id'], 'cases': [],
               'child_path_contains_python': False, 'material': 'synthetic-only', 'directory': root.name}
    try:
        for kind in ('csv', 'xlsx'):
            study = root / ('Studie mit Umlaut ä ' + kind); study.mkdir()
            (study / 'book.csv').write_text(BOOK, encoding='utf-8')
            if kind == 'csv':
                original = study / 'Segmente frei benannt ä.csv'
                with original.open('w', encoding='utf-8', newline='') as stream:
                    csv.writer(stream, delimiter=';', lineterminator='\n').writerows(ROWS)
                input_path = original
                extra = []
            else:
                original = study / 'Echte Segmente ä.xlsx'
                workbook = openpyxl.Workbook(); workbook.active.title = 'Codierte Segmente'
                for row in ROWS:
                    workbook.active.append(row)
                workbook.save(original); workbook.close()
                original_hash = digest(original)
                input_path = import_xlsx(exe, study, foreign, env, root, args.timeout)
                require(digest(original) == original_hash, 'Original XLSX changed')
                extra = ['--output-dir', str(study / 'QualitativeAnalyse_XLSX')]
            config = config_for(template, study, input_path)
            before = {path.name: digest(path) for path in study.iterdir() if path.is_file()}
            cli(exe, config, ['--validate-only', *extra], foreign, env, logs, kind + '-validate', args.timeout)
            require({path.name for path in study.iterdir()} == set(before), 'Validation created output')
            cli(exe, config, extra, foreign, env, logs, kind + '-first', args.timeout)
            manifests = list(study.rglob('workflow_manifest.json'))
            require(len(manifests) == 1, 'Expected one result beside original input')
            run = manifests[0].parent
            first = check_run(run, config, input_path, study / 'book.csv', exe, build)
            cli(exe, config, ['--resume', str(run)], foreign, env, logs, kind + '-resume', args.timeout)
            resumed = check_run(run, config, input_path, study / 'book.csv', exe, build)
            require(first['fingerprint'] == resumed['fingerprint'], 'Resume identity changed')
            for name, expected in first['output_hashes'].items():
                if name not in {'gesamtbericht.html', 'gesamtbericht.md'}:
                    require(resumed['output_hashes'][name] == expected, 'Completed analysis changed on resume')
            require(len(list(study.rglob('workflow_manifest.json'))) == 1, 'Resume created a second run')
            require({name: digest(study / name) for name in before} == before, 'Input/config modified')
            results['cases'].append({'format': kind, 'status': 'passed', 'completed': ['coverage'],
                                     'model_calls': 0, 'input_unchanged': True, 'resume_hashes_stable': True,
                                     'report_html': True, 'report_markdown': True, 'package_provenance': True})
        require(list(foreign.iterdir()) == [], 'Unrelated cwd received artifacts')
        require(not (root / 'appdata-not-used-by-cli').exists(), 'CLI used default App data')
        require({relative: digest(bundle / relative) for relative in bundle_before} == bundle_before, 'Bundled source/resources changed')
        results['status'] = 'passed'
    except BaseException as exc:
        results.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        (root / 'result.json').write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print('Frozen workflow evidence: ' + str(root), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
