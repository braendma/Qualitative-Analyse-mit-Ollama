"""Internal sequential dispatch to the existing runner, with isolated run directories.

No additional module runner or checkpoint format: child manifests remain authoritative.
Runtime receipts and supervised managed-server handoff are implemented; UI follows.
"""
import importlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import uuid

import yaml

from diagnostic_repetitions import prepare_repetitions
from managed_ollama import stop_tree
from runtime_support import atomic_json, atomic_text, exclusive_file_lock, file_hash, fingerprint


def _runner():
    return importlib.import_module('00_WORKFLOW_RUNNER')


def _runner_command():
    return [sys.executable, str(Path(__file__).with_name('00_WORKFLOW_RUNNER.py'))]


def _check_plan(plan):
    try:
        actual = prepare_repetitions(plan['source_config'], plan['requested_modules'],
                                     repetitions=plan['repetitions'])
    except (KeyError, TypeError, OSError) as exc:
        raise ValueError('Wiederholungsplan oder seine Ausgangsdateien fehlen bzw. sind beschädigt.') from exc
    if actual != plan:
        raise ValueError('Wiederholungsplan passt nicht mehr zu den Eingaben oder Einstellungen. Neue Serie planen.')


def _identity(config_path, config):
    provenance = _runner().execution_provenance(config_path, config['paths']['input_csv'], config)
    return fingerprint({k: v for k, v in provenance.items() if k != 'commit'})


def _read_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('Keine Objektstruktur')
        return value
    except (OSError, ValueError) as exc:
        raise ValueError(f'Seriensteuerung: Datei fehlt oder ist beschädigt: {path.name}') from exc


def _inside(path, root):
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError('Serienpfad verweist außerhalb des zugehörigen Laufordners.')


def _sample_run(parent, identity, modules):
    """Only inspect the one child allocated to this sample; never adopt another run."""
    if not parent.exists():
        return None, None
    _inside(parent, parent.parent)
    entries = list(parent.iterdir())
    if not entries:
        return None, None
    if len(entries) != 1 or not entries[0].is_dir():
        raise ValueError(f'{parent.name}: Mehrdeutiger Laufordner; keine automatische Wiederaufnahme.')
    run = entries[0]
    _inside(run, parent)
    manifest_path = run / 'workflow_manifest.json'
    _inside(manifest_path, run)
    manifest = _read_json(manifest_path)
    if manifest.get('run_id') != run.name or manifest.get('fingerprint') != identity:
        raise ValueError(f'{parent.name}: Laufidentität stimmt nicht mit der geplanten Wiederholung überein.')
    if not isinstance(manifest.get('output_hashes'), dict) or not isinstance(manifest.get('provenance'), dict):
        raise ValueError(f'{parent.name}: Prüfsummen der Ausgaben fehlen oder sind beschädigt.')
    if fingerprint({k: v for k, v in manifest['provenance'].items() if k != 'commit'}) != identity:
        raise ValueError(f'{parent.name}: Gespeicherte Provenienz stimmt nicht mit der Laufidentität überein.')
    snapshot = run / 'config_snapshot.yaml'
    _inside(snapshot, run)
    if not snapshot.is_file() or file_hash(snapshot) != manifest['provenance'].get('config_sha256'):
        raise ValueError(f'{parent.name}: Konfigurationskopie des Laufs verändert oder fehlt.')
    completed = manifest.get('completed_steps')
    expected = {m['id'] for m in modules}
    if (not isinstance(completed, list) or any(not isinstance(x, str) for x in completed)
            or len(set(completed)) != len(completed) or set(completed) - expected):
        raise ValueError(f'{parent.name}: Ungültige Liste abgeschlossener Module.')
    for module in modules:
        if module['id'] in completed:
            for name in module.get('outputs', []):
                _inside(run / name, run)
    _runner().verify_completed_outputs(run, manifest, modules)
    from runtime_evidence import verify_inventory
    verify_inventory(run, manifest)
    status = manifest.get('status')
    if status not in {'success', 'failed', 'paused', 'interrupted', 'running'}:
        raise ValueError(f'{parent.name}: Unbekannter Laufstatus; Zwischenstand prüfen.')
    if status == 'success':
        if set(completed) != expected:
            raise ValueError(f'{parent.name}: Erfolg ohne sämtliche abgeschlossenen Module.')
        for name in ('gesamtbericht.md', 'gesamtbericht.html'):
            path = run / name
            _inside(path, run)
            if not path.is_file() or file_hash(path) != manifest.get('output_hashes', {}).get(name):
                raise ValueError(f'{parent.name}: Abschlussbericht verändert oder fehlt: {name}')
    return run, manifest


def _execute(command, directory, log, env):
    """Keep a pipe lease; the shared supervisor owns and reaps the child tree."""
    request_path = log.with_suffix('.supervision.request.json')
    receipt_path = log.with_suffix('.supervision.json')
    for path in (request_path, receipt_path):
        _inside(path, Path(directory))
    ticket = uuid.uuid4().hex
    plan_path = Path(directory) / 'repetition_plan.json'
    identity = _read_json(plan_path).get('execution_fingerprint') if plan_path.is_file() else None
    parent = command[command.index('--output-dir') + 1] if '--output-dir' in command else None
    atomic_json(request_path, {'ticket': ticket, 'command_sha256': fingerprint(command),
        'execution_fingerprint': identity, 'run_parent': parent})
    supervised = [sys.executable, str(Path(__file__).with_name('managed_ollama.py')),
                  '--command', str(receipt_path), ticket, *command]
    with open(log, 'ab') as output:
        process = subprocess.Popen(supervised, cwd=directory, env=env, stdin=subprocess.PIPE,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            return process.wait()
        finally:
            if process.stdin:
                process.stdin.close()
            if process.poll() is None:
                try:
                    process.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    stop_tree(process)
                    process.wait(timeout=10)
                    raise RuntimeError('Prozessaufsicht musste beendet werden; Aufräumen nicht bestätigt. Zwischenstand prüfen.')
            _confirmed_supervision(log, identity, parent)


def _confirmed_supervision(log, identity, parent):
    request_path = log.with_suffix('.supervision.request.json')
    receipt_path = log.with_suffix('.supervision.json')
    for path in (request_path, receipt_path):
        _inside(path, log.parent)
    request, receipt = _read_json(request_path), _read_json(receipt_path)
    if (receipt.get('schema_version') != 1 or request.get('execution_fingerprint') != identity or request.get('run_parent') != parent
            or not re.fullmatch('[a-f0-9]{64}', str(request.get('command_sha256', '')))
            or receipt.get('cleanup_scope') not in ('windows_job', 'process_group')
            or not request.get('ticket') or receipt.get('ticket') != request['ticket']
            or receipt.get('command_sha256') != request.get('command_sha256')
            or receipt.get('status') != 'finished' or receipt.get('cleanup_confirmed') is not True):
        raise ValueError('Prozessende ist noch nicht sicher bestätigt; keine parallele Wiederaufnahme. Aufräumen abwarten oder Prozessstatus prüfen.')
    return receipt


def execute_repetitions(plan, directory, *, resume=False, pause_file=None, progress=None):
    """Run samples sequentially; stop on first failure/pause, preserving all outputs.

    Abruptly abandoned children require the supervisor's cleanup receipt before
    a restart. A supervising app is not yet
    supported: release its managed Ollama server before dispatching this API.
    """
    _check_plan(plan)
    if os.environ.get('QUALITATIVE_MANAGED_OLLAMA_HOST'):
        raise ValueError('Verwaltete Ollama-Instanz des übergeordneten Laufs zuerst freigeben; keine zweite Instanz starten.')
    root = Path(directory).resolve()
    if resume:
        if not root.is_dir():
            raise ValueError('Serienordner für Wiederaufnahme nicht gefunden.')
    else:
        root.mkdir(parents=True, exist_ok=False)
    pause = Path(pause_file).resolve() if pause_file else None
    lock_path = root / '.series.lock'
    _inside(lock_path, root)
    with exclusive_file_lock(lock_path):
        config_path = root / 'repetition_config.yaml'
        receipt_path = root / 'repetition_plan.json'
        for path in (config_path, receipt_path):
            _inside(path, root)
        if resume:
            receipt = _read_json(receipt_path)
            if receipt.get('plan') != plan:
                raise ValueError('Gespeicherter Serienplan stimmt nicht überein; neue Serie verwenden.')
            if not config_path.is_file() or file_hash(config_path) != receipt.get('config_sha256'):
                raise ValueError('Gespeicherte Serienkonfiguration verändert oder fehlt.')
            identity = _identity(config_path, plan['config'])
            if receipt.get('execution_fingerprint') != identity:
                raise ValueError('Code, Abhängigkeiten oder Laufgrundlage geändert; neue Serie verwenden.')
        else:
            atomic_text(config_path, yaml.safe_dump(plan['config'], allow_unicode=True, sort_keys=True))
            identity = _identity(config_path, plan['config'])
            atomic_json(receipt_path, {'schema_version': 1, 'plan': plan,
                'execution_fingerprint': identity, 'config_sha256': file_hash(config_path)})
        modules = _runner().topological_order(_runner().normalize_modules(plan['config']))
        result = {'schema_version': 1, 'status': 'running', 'plan_fingerprint': plan['plan_fingerprint'],
                  'execution_fingerprint': identity, 'samples': [],
                  'parameter_status': 'configured_not_runtime_verified'}
        env = {k: v for k, v in os.environ.items() if not k.startswith('WORKFLOW_')}
        env['PYTHONUTF8'] = '1'
        observed_digests = set()
        for sample in plan['samples']:
            if progress:
                progress(sum(s['status'] == 'success' for s in result['samples']), len(plan['samples']))
            _check_plan(plan)
            if _identity(config_path, plan['config']) != identity:
                raise ValueError('Laufgrundlage während der Serie geändert; keine weiteren Wiederholungen gestartet.')
            parent = root / sample['sample_id']
            supervision_log = root / (sample['sample_id'] + '.log')
            has_dispatch = supervision_log.with_suffix('.supervision.request.json').exists()
            if has_dispatch:
                _confirmed_supervision(supervision_log, identity, str(parent))
            run, manifest = _sample_run(parent, identity, modules)
            if manifest and not has_dispatch:
                raise ValueError('Vorhandener Lauf hat keine zugehörige Prozessaufsicht; keine automatische Übernahme.')
            if manifest and manifest['status'] == 'running':
                manifest['status'] = 'interrupted'
                atomic_json(run / 'workflow_manifest.json', manifest)
            if not manifest or manifest['status'] != 'success':
                if pause and pause.is_file():
                    result['status'] = 'paused'
                    break
                command = _runner_command() + ['--config', str(config_path), '--output-dir', str(parent)]
                if run:
                    command += ['--resume', str(run)]
                if pause:
                    command += ['--pause-file', str(pause)]
                log_path = root / (sample['sample_id'] + '.log')
                _inside(log_path, root)
                try:
                    if observed_digests:
                        env['WORKFLOW_EXPECTED_MODEL_DIGEST'] = next(iter(observed_digests))
                    code = _execute(command, root, log_path, env)
                except KeyboardInterrupt:
                    # _execute only propagates this after its child has been reaped.
                    stopped_run, stopped = _sample_run(parent, identity, modules)
                    if stopped and stopped['status'] == 'running':
                        stopped['status'] = 'interrupted'
                        atomic_json(stopped_run / 'workflow_manifest.json', stopped)
                    raise
                _check_plan(plan)
                if _identity(config_path, plan['config']) != identity:
                    raise ValueError('Laufgrundlage während einer Wiederholung geändert; Ergebnisse nicht vergleichbar.')
                run, manifest = _sample_run(parent, identity, modules)
                if not manifest:
                    result['samples'].append({'sample_id': sample['sample_id'], 'status': 'failed',
                        'run_dir': None, 'exit_code': code, 'error': 'Runner ohne gültiges Manifest beendet; Serienlog prüfen.'})
                    result['status'] = 'failed'
                    break
                if code != 0 or manifest['status'] not in {'success', 'paused'}:
                    result['status'] = 'failed'
                elif manifest['status'] == 'paused':
                    result['status'] = 'paused'
            evidence = manifest.get('runtime_evidence', {})
            observed_digests.update(evidence.get('local_digests', []))
            if len(observed_digests) > 1:
                result.update(status='failed', error='Modellidentität zwischen kontrollierten Anfragen verändert; keine gemeinsame Stabilitätsbewertung.')
            result['samples'].append({'sample_id': sample['sample_id'],
                'status': 'failed' if result['status'] == 'failed' else manifest['status'],
                'run_dir': str(run.relative_to(root)),
                'runtime_evidence': {k: evidence.get(k) for k in ('records', 'accepted', 'failed', 'pending', 'local_digests', 'parameter_status')}})
            if result['status'] != 'running':
                break
        if result['status'] == 'running':
            result['status'] = 'success'
        result['completed_samples'] = sum(s['status'] == 'success' for s in result['samples'])
        result['planned_samples'] = len(plan['samples'])
        # This is an index of existing manifests, never a second module checkpoint.
        atomic_json(root / 'repetition_index.json', result)
        if progress:
            progress(result['completed_samples'], result['planned_samples'])
        return result
