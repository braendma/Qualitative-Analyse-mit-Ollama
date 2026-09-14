"""Internal sequential dispatch to the existing runner, with isolated run directories.

No additional module runner or checkpoint format: child manifests remain authoritative.
Runtime receipts and supervised managed-server handoff serve both diagnostic types.
"""
import importlib
from contextvars import ContextVar
from itertools import islice
import json
import os
import re
from pathlib import Path
from filesystem_paths import canonical_path, process_directory, io_path
import subprocess
import sys
import uuid

import yaml

from diagnostic_repetitions import prepare_repetitions
from managed_ollama import stop_tree
from process_commands import python_command
from runtime_support import atomic_json, atomic_text, exclusive_file_lock, file_hash, fingerprint


# Scope display callbacks to one synchronous dispatch without changing the
# established dispatch interface or passing callbacks into the child process.
_PROGRESS_POLL = ContextVar('diagnostic_series_progress_poll', default=None)


def _runner():
    return importlib.import_module('00_WORKFLOW_RUNNER')


def _runner_command():
    return python_command(Path(__file__).with_name('00_WORKFLOW_RUNNER.py'))


def _check_plan(plan):
    if not isinstance(plan,dict):
        raise ValueError('Serienplan muss eine gültige Zuordnung sein.')
    try:
        if plan.get('kind') == 'sensitivity':
            from diagnostic_sensitivity import prepare_sensitivity
            actual = prepare_sensitivity(plan['source_config'], plan['requested_modules'],
                                         plan['variants'], repetitions=plan['repetitions'])
        else:
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
    if (not canonical_path(path).is_relative_to(canonical_path(root))
            or io_path(path).is_symlink()):
        raise ValueError('Serienpfad verweist außerhalb des zugehörigen Laufordners.')


def _sensitivity_records(root, plan, *, prepare=False):
    """Bind each variant to its own configuration and the shared process supervisor.

    No execution or module checkpoint here: this is the immutable series receipt.
    The same receipt reader is used before dispatch, after dispatch and on resume.
    """
    receipt_path=root/'repetition_plan.json'
    _inside(receipt_path,root)
    records={}; bindings=[]
    for condition in plan['configurations']:
        cid=condition['configuration_id'];config=condition['config']
        path=root/('configuration-'+cid+'.yaml')
        _inside(path,root)
        if prepare:
            if path.exists():
                raise ValueError('Sensitivitätskonfiguration bereits vorhanden; keine Datei überschrieben.')
            atomic_text(path,yaml.safe_dump(config,allow_unicode=True,sort_keys=True))
        identity=_identity(path,config)
        binding={'configuration_id':cid,'filename':path.name,'config_sha256':file_hash(path),
                 'execution_fingerprint':identity}
        bindings.append(binding)
        records[cid]={'path':path,'config':config,'identity':identity}
    identity=fingerprint(bindings)
    expected={'schema_version':2,'plan':plan,'configurations':bindings,'execution_fingerprint':identity}
    if prepare:
        atomic_json(receipt_path,expected)
    elif _read_json(receipt_path) != expected:
        raise ValueError('Sensitivitätskonfiguration, Code oder Laufgrundlage verändert; neue Serie verwenden.')
    return records,identity


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


def _bounded_status(path, root, limit):
    _inside(path, root)
    with path.open('rb') as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Statusdatei überschreitet die Anzeigegrenze.')
    value = json.loads(raw.decode('utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Statusdatei ist keine Zuordnung.')
    return value


def _child_progress(parent, identity, modules):
    """Read only the allocated child's small status files, never result artifacts.

    This live projection does not replace the full verification at completion or
    resume. Missing, changing, unbound or malformed status is simply unavailable.
    """
    from progress_presentation import safe_numeric_progress
    unavailable = {'state': 'unavailable'}
    try:
        if not parent.exists():
            return {'state': 'starting'}
        _inside(parent, parent.parent)
        entries = list(islice(parent.iterdir(), 2))
        if not entries:
            return {'state': 'starting'}
        if len(entries) != 1 or not entries[0].is_dir():
            return unavailable
        run = entries[0]
        _inside(run, parent)
        path = run / 'workflow_manifest.json'
        manifest = _bounded_status(path, run, 2 * 1024 * 1024)
        if (manifest.get('run_id') != run.name or manifest.get('fingerprint') != identity or
                not isinstance(manifest.get('provenance'), dict) or
                fingerprint({k: v for k, v in manifest['provenance'].items() if k != 'commit'}) != identity):
            return unavailable
        expected = {m['id'] for m in modules}
        completed = manifest.get('completed_steps')
        if (not isinstance(completed, list) or any(not isinstance(mid, str) for mid in completed) or
                len(set(completed)) != len(completed) or set(completed) - expected):
            return unavailable
        status = manifest.get('status')
        if status not in {'running', 'success', 'failed', 'paused', 'interrupted'}:
            return unavailable
        result = {'state': {'success': 'finishing', 'interrupted': 'failed'}.get(status, status),
                  'modules_completed': len(completed), 'modules_total': len(expected)}
        mid = manifest.get('current_module')
        if mid in expected:
            result['module'] = mid
        if status == 'running' and mid in expected and manifest.get('module_status', {}).get(mid) == 'running':
            try:
                detail = _bounded_status(run / 'progress.json', run, 16384)
                if (detail.get('run_id') == run.name and detail.get('fingerprint') == identity and
                        detail.get('module') == mid):
                    result['detail'] = safe_numeric_progress(detail)
            except (OSError, ValueError, TypeError):
                pass
        # A module may finish between the two reads; do not combine counters
        # from different modules or lifecycle boundaries in one display frame.
        again = _bounded_status(path, run, 2 * 1024 * 1024)
        keys = ('run_id', 'fingerprint', 'provenance', 'current_module', 'module_status', 'completed_steps', 'status')
        if any(again.get(key) != manifest.get(key) for key in keys):
            return unavailable
        return result
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        return unavailable


def _poll_progress():
    callback = _PROGRESS_POLL.get()
    if callback is not None:
        try:
            callback()
        except Exception:
            pass  # Optional display failure must never abort or detach a run.


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
    supervised = python_command(Path(__file__).with_name('managed_ollama.py'),
                  ['--command', str(receipt_path), ticket, *command])
    with open(log, 'ab') as output:
        process = subprocess.Popen(supervised, cwd=process_directory(Path(__file__).parent), env=env, stdin=subprocess.PIPE,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            if _PROGRESS_POLL.get() is None:
                return process.wait()
            while True:
                _poll_progress()
                try:
                    code = process.wait(timeout=2)
                    _poll_progress()
                    return code
                except subprocess.TimeoutExpired:
                    continue
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
    from supervision_receipts import UNCONFIRMED, validate_receipt
    request_path = log.with_suffix('.supervision.request.json')
    receipt_path = log.with_suffix('.supervision.json')
    for path in (request_path, receipt_path):
        _inside(path, log.parent)
    request, receipt = _read_json(request_path), _read_json(receipt_path)
    stored_parent = request.get('run_parent')
    try:
        same_parent = stored_parent is None if parent is None else (
            isinstance(stored_parent, str) and bool(stored_parent)
            and isinstance(parent, str) and bool(parent)
            and Path(stored_parent).is_absolute() and Path(parent).is_absolute()
            and canonical_path(stored_parent) == canonical_path(parent))
    except (OSError, RuntimeError, TypeError, ValueError):
        same_parent = False
    # Compare only path identity across normal/extended IO spelling. The saved
    # request, command hash and ticket remain byte-for-byte authoritative.
    if request.get('execution_fingerprint') != identity or not same_parent:
        raise ValueError(UNCONFIRMED)
    return validate_receipt(receipt, ticket=request.get('ticket'), command_sha256=request.get('command_sha256'))


def _child_environment(config):
    from llm_providers import provider_environment, transport_selection
    selected = transport_selection(config['llm'], config['llm']['model'])
    env = provider_environment(selected, os.environ)
    env = {key: value for key, value in env.items() if not key.startswith('WORKFLOW_')}
    env['PYTHONUTF8'] = '1'
    return env


def execute_repetitions(plan, directory, *, resume=False, pause_file=None, progress=None, inner_progress=None):
    """Run samples sequentially; stop on first failure/pause, preserving all outputs.

    Abruptly abandoned children require the supervisor's cleanup receipt before
    a restart. The caller must release its managed Ollama server before dispatch;
    the existing runner does so for modules marked starts_child_runs.
    """
    _check_plan(plan)
    if os.environ.get('QUALITATIVE_MANAGED_OLLAMA_HOST'):
        raise ValueError('Verwaltete Ollama-Instanz des übergeordneten Laufs zuerst freigeben; keine zweite Instanz starten.')
    root = io_path(directory)
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
        varied=plan['kind']=='sensitivity'
        if varied:
            configurations,identity=_sensitivity_records(root,plan,prepare=not resume)
            first_config=next(iter(configurations.values()))['config']
        elif resume:
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
        if not varied:
            configurations={'baseline':{'path':config_path,'config':plan['config'],'identity':identity}}
            first_config=plan['config']
        modules = _runner().topological_order(_runner().normalize_modules(first_config))
        result = {'schema_version': 1, 'status': 'running', 'plan_fingerprint': plan['plan_fingerprint'],
                  'execution_fingerprint': identity, 'samples': [],
                  'parameter_status': 'configured_not_runtime_verified'}
        env = _child_environment(first_config)
        observed_by_model = {}
        for sample_index, sample in enumerate(plan['samples'], 1):
            if progress:
                progress(sum(s['status'] == 'success' for s in result['samples']), len(plan['samples']))
            _check_plan(plan)
            selected_config=configurations[sample.get('configuration_id','baseline')]
            sample_config=selected_config['config'];config_path=selected_config['path']
            sample_identity=selected_config['identity']
            if varied:
                _sensitivity_records(root,plan)
            if _identity(config_path, sample_config) != sample_identity:
                raise ValueError('Laufgrundlage während der Serie geändert; keine weiteren Wiederholungen gestartet.')
            from runtime_evidence import _canonical
            model_key=_canonical(sample_config['llm']['model'])
            observed_digests=observed_by_model.setdefault(model_key,set())
            parent = root / sample['sample_id']
            supervision_log = root / (sample['sample_id'] + '.log')
            has_dispatch = supervision_log.with_suffix('.supervision.request.json').exists()
            if has_dispatch:
                _confirmed_supervision(supervision_log, identity, str(parent))
            run, manifest = _sample_run(parent, sample_identity, modules)
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
                    env.pop('WORKFLOW_EXPECTED_MODEL_DIGEST',None)
                    if observed_digests:
                        env['WORKFLOW_EXPECTED_MODEL_DIGEST'] = next(iter(observed_digests))
                    def current_progress():
                        ids = list(configurations)
                        cid = sample.get('configuration_id', 'baseline')
                        metadata = {'sample_number': sample_index, 'sample_total': len(plan['samples']),
                            'configuration_number': ids.index(cid) + 1, 'configuration_total': len(ids),
                            'repetition_number': sum(s.get('configuration_id', 'baseline') == cid
                                                     for s in plan['samples'][:sample_index]),
                            'repetition_total': plan['repetitions']}
                        inner_progress({**metadata, **_child_progress(parent, sample_identity, modules)})
                    token = _PROGRESS_POLL.set(current_progress if inner_progress else None)
                    try:
                        code = _execute(command, root, log_path, env)
                    finally:
                        _PROGRESS_POLL.reset(token)
                except KeyboardInterrupt:
                    # _execute only propagates this after its child has been reaped.
                    stopped_run, stopped = _sample_run(parent, sample_identity, modules)
                    if stopped and stopped['status'] == 'running':
                        stopped['status'] = 'interrupted'
                        atomic_json(stopped_run / 'workflow_manifest.json', stopped)
                    raise
                _check_plan(plan)
                if varied:
                    _sensitivity_records(root,plan)
                if _identity(config_path, sample_config) != sample_identity:
                    raise ValueError('Laufgrundlage während einer Wiederholung geändert; Ergebnisse nicht vergleichbar.')
                run, manifest = _sample_run(parent, sample_identity, modules)
                if not manifest:
                    result['samples'].append({'sample_id': sample['sample_id'], 'status': 'failed',
                        'run_dir': None, 'exit_code': code, 'error': 'Runner ohne gültiges Manifest beendet; Serienlog prüfen.'})
                    if varied:
                        result['samples'][-1]['configuration_id']=sample['configuration_id']
                    result['status'] = 'failed'
                    break
                if code != 0 or manifest['status'] not in {'success', 'paused'}:
                    result['status'] = 'failed'
                elif manifest['status'] == 'paused':
                    result['status'] = 'paused'
            evidence = manifest.get('runtime_evidence', {})
            observed_digests.update(evidence.get('local_digests', []))
            if len(observed_digests) > 1:
                result.update(status='failed', error='Modellidentität desselben Modellnamens zwischen kontrollierten Anfragen verändert; keine gemeinsame Bewertung.')
            result['samples'].append({'sample_id': sample['sample_id'],
                'status': 'failed' if result['status'] == 'failed' else manifest['status'],
                'run_dir': str(run.relative_to(root)),
                'runtime_evidence': {k: evidence.get(k) for k in ('records', 'accepted', 'failed', 'pending', 'local_digests', 'parameter_status')}})
            if varied:
                result['samples'][-1]['configuration_id']=sample['configuration_id']
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
