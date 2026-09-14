"""Inspect an existing controlled series without dispatching or resuming any run."""
from collections import Counter
import math
from pathlib import Path
import re

from coding_validation_common import load_codebook, load_segments
from diagnostic_series import (_check_plan, _confirmed_supervision, _identity, _inside,
                               _read_json, _runner, _sample_run, _sensitivity_records)
from diagnostic_sources import STAGES, load_declared_artifact
from runtime_evidence import _canonical, _name
from runtime_support import exclusive_file_lock, file_hash, fingerprint
from failure_help import child_failure_guidance
from stability_core import analyze_coding_repetitions, analyze_stage_repetitions


def _thematic_upstreams(run, module_id, payload, by_id, manifest):
    """Bind required originals to the same completed child-run manifest."""
    if 'analysis_perspective' not in payload:
        return {}
    required = {'meta_swot': ('swot',), 'ambiguity_analysis': ('person_analysis',),
                'person_comparison': ('person_analysis',),
                'contrast_analysis': ('person_analysis', 'person_comparison'),
                'relation_analysis': ('clusterer', 'summarizer')}.get(module_id, ())
    result = {}
    for mid in required:
        if mid not in by_id:
            raise ValueError('Thematische Wiederholung benötigt eine deklarierte Originalvorstufe: ' + mid)
        source = load_declared_artifact(run, by_id[mid], manifest)
        if source['status'] != 'available':
            raise ValueError('Thematische Wiederholung enthält keine verifizierte Originalvorstufe: ' + mid)
        result[mid] = source['payload']
    return result


def _parameters(value, provider):
    """Validate and retain only the content-free fields emitted by RequestReceipt."""
    if not isinstance(value, dict):
        raise ValueError('Ungültiger Laufzeit-Parameternachweis.')
    if provider in ('ollama_local', 'ollama_cloud'):
        if set(value) - {'options', 'think', 'format_sha256'} or not isinstance(value.get('options'), dict):
            raise ValueError('Unerwartete Felder im Ollama-Parameternachweis.')
        numeric = value['options']
        if set(numeric) - {'temperature', 'num_predict', 'num_ctx', 'seed', 'top_k', 'top_p', 'min_p', 'repeat_penalty'}:
            raise ValueError('Unbekannte Laufzeitoption.')
        if provider == 'ollama_cloud' and 'num_ctx' in numeric:
            raise ValueError('Cloud-Nachweis enthält nicht übertragbare Kontextoption.')
        if 'think' in value and type(value['think']) is not bool and value['think'] not in ('low', 'medium', 'high', 'max'):
            raise ValueError('Ungültiger Thinking-Nachweis.')
        if 'format_sha256' in value and not re.fullmatch('[a-f0-9]{64}', str(value['format_sha256'])):
            raise ValueError('Ungültiger Schema-Nachweis.')
    else:
        expected = 'max_output_tokens' if provider == 'openai' else 'max_tokens'
        if set(value) != {expected}:
            raise ValueError('Unerwartete Felder im Anbieter-Parameternachweis.')
        numeric = value
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in numeric.values()):
        raise ValueError('Ungültige numerische Laufzeitparameter.')
    return value


def _request_profiles(run, manifest, plan, modules):
    """Hashes/run binding were checked by the shared series reader before this call."""
    profiles, counts, digests = {}, Counter(), set()
    inventory = manifest.get('runtime_evidence') or {'files': {}}
    for name in inventory['files']:
        receipt = _read_json(run / '_runtime_evidence' / name)
        module = receipt.get('module')
        if module not in modules:
            raise ValueError('Laufzeitnachweis nennt ein nicht geplantes Modul.')
        counts[(module, receipt['status'])] += 1
        if receipt['status'] != 'accepted':
            continue
        provider, model = receipt.get('provider'), receipt.get('model')
        if provider != plan['provider'] or not _name(model) or _canonical(model) != _canonical(plan['config']['llm']['model']):
            raise ValueError('Anbieter oder Modell des Laufzeitnachweises weicht vom Plan ab.')
        if receipt.get('parameter_status') != 'request_accepted':
            raise ValueError('Akzeptierte Anfrage ohne bestätigten Übertragungsstatus.')
        if provider == 'ollama_local':
            before, after = receipt.get('model_before'), receipt.get('model_after')
            if (not isinstance(before, dict) or not isinstance(after, dict)
                    or not re.fullmatch('[a-f0-9]{64}', str(before.get('digest', '')))
                    or before['digest'] != after.get('digest')):
                raise ValueError('Lokale Modellidentität vor/nach Anfrage nicht bestätigt.')
            digests.add(before['digest'])
        parameters = _parameters(receipt.get('parameters_sent'), provider)
        identity = fingerprint({'module': module, 'provider': provider, 'model': _canonical(model), 'parameters': parameters})
        profile = profiles.setdefault(identity, {'fingerprint': identity, 'module': module,
            'provider': provider, 'model': model, 'parameters_sent': parameters,
            'accepted_requests': 0, 'observed_context_lengths': []})
        profile['accepted_requests'] += 1
        context = receipt.get('observed_context_length')
        if context is not None:
            if type(context) is not int or context < 1:
                raise ValueError('Ungültige beobachtete Kontextgröße.')
            if context not in profile['observed_context_lengths']:
                profile['observed_context_lengths'].append(context)
                profile['observed_context_lengths'].sort()
    return {'profiles': [profiles[k] for k in sorted(profiles)], 'local_digests': sorted(digests),
            'modules': {mid: {'accepted': counts[mid, 'accepted'], 'failed': counts[mid, 'failed'],
                             'pending': counts[mid, 'pending'] + counts[mid, 'preparing']} for mid in modules},
            'server_parameter_enforcement': 'not_verifiable'}


def load_stability_series(directory):
    return _load_series(directory, kind='stability')


def load_sensitivity_series(directory):
    return _load_series(directory, kind='sensitivity')


def _load_series(directory, *, kind):
    """Reconstruct only planned samples; repetition_index.json is never authority.

    Busy/unconfirmed processes and corrupted provenance raise instead of reading
    a moving target. Failed or never-started samples remain explicit exclusions.
    """
    root = Path(directory).resolve()
    if not root.is_dir():
        raise ValueError('Wiederholungsordner nicht gefunden.')
    lock = root / '.series.lock'
    _inside(lock, root)
    if not lock.is_file():
        raise ValueError('Kein vorbereiteter Serienordner.')
    with exclusive_file_lock(lock):
        receipt_path, config_path = root / 'repetition_plan.json', root / 'repetition_config.yaml'
        for path in (receipt_path, config_path):
            _inside(path, root)
        receipt = _read_json(receipt_path)
        plan = receipt.get('plan')
        sensitivity = kind == 'sensitivity'
        if (not isinstance(plan, dict) or receipt.get('schema_version') != (2 if sensitivity else 1)
                or (plan.get('kind') == 'sensitivity') != sensitivity):
            raise ValueError('Ungültiger Seriennachweis.')
        _check_plan(plan)
        if sensitivity:
            records, identity = _sensitivity_records(root, plan)
        else:
            if file_hash(config_path) != receipt.get('config_sha256'):
                raise ValueError('Gespeicherte Serienkonfiguration verändert oder fehlt.')
            identity = _identity(config_path, plan['config'])
            if identity != receipt.get('execution_fingerprint'):
                raise ValueError('Code, Abhängigkeiten oder Laufgrundlage passen nicht zur Serie.')
            records = {'baseline': {'path': config_path, 'config': plan['config'], 'identity': identity}}
        config = records['baseline']['config']
        receipt_hash = file_hash(receipt_path)
        modules = _runner().topological_order(_runner().normalize_modules(config))
        by_id = {m['id']: m for m in modules}
        comparable = [mid for mid in by_id if mid in STAGES or mid in {'blind_coding', 'code_verification'}]
        samples = {mid: [] for mid in comparable}
        conditions, checked, all_digests, model_digests = [], [], set(), {}
        for sample in plan['samples']:
            sid = sample['sample_id']
            cid = sample.get('configuration_id', 'baseline')
            record = records[cid]
            parent, log = root / sid, root / (sid + '.log')
            dispatch = log.with_suffix('.supervision.request.json')
            supervision = None
            if dispatch.exists():
                supervision = _confirmed_supervision(log, identity, str(parent))
            run, manifest = _sample_run(parent, record['identity'], modules)
            if manifest and supervision is None:
                raise ValueError('Lauf ohne zugehörigen Prozessabschlussnachweis.')
            status = manifest['status'] if manifest else 'failed' if supervision else 'pending'
            if status == 'running':
                status = 'interrupted'  # Cleanup is confirmed; do not mutate the manifest.
            if status == 'success' and (type(supervision.get('exit_code')) is not int or supervision['exit_code'] != 0):
                status = 'failed'
            condition = {'sample_id': sid, 'status': status, 'run_dir': str(run.relative_to(root)) if run else None}
            if sensitivity:
                condition['configuration_id'] = cid
            if manifest:
                checked.append((parent, manifest, record['identity']))
                if status in ('failed', 'interrupted'):
                    condition['failure_guidance'] = child_failure_guidance(manifest, by_id)
                runtime = _request_profiles(run, manifest, {'provider': plan['provider'], 'config': record['config']}, by_id)
                all_digests.update(runtime['local_digests'])
                model = _canonical(record['config']['llm']['model'])
                model_digests.setdefault(model, set()).update(runtime['local_digests'])
                condition['runtime'] = runtime
            conditions.append(condition)
            for mid in comparable:
                item = {'sample_id': sid, 'status': status}
                if sensitivity:
                    item['configuration_id'] = cid
                if status == 'success':
                    artifact = load_declared_artifact(run, by_id[mid], manifest)
                    if artifact['status'] != 'available':
                        raise ValueError('Abgeschlossene Wiederholung enthält kein verifiziertes Modulergebnis: ' + mid)
                    item['payload'] = artifact['payload']
                    upstreams = _thematic_upstreams(run, mid, item['payload'], by_id, manifest)
                    if upstreams:
                        item['upstream_payloads'] = upstreams
                samples[mid].append(item)
        if any(len(digests) > 1 for digests in model_digests.values()):
            raise ValueError('Verschiedene lokale Modellgewichte: keine gemeinsame Stabilitätsbewertung.')
        segments = load_segments(config['paths']['input_csv'], config['columns'])
        codebook, _ = load_codebook(config['paths']['category_system_csv'])
        label_mode = config.get('coding_agreement', {}).get('label_mode', 'single_label')
        label_mode = 'single_label' if label_mode == 'unspecified' else label_mode
        comparisons = {}
        for mid, items in samples.items():
            if sensitivity:
                from sensitivity_core import analyze_sensitivity
                result = analyze_sensitivity(segments, codebook, mid, plan['configurations'], items, label_mode=label_mode)
                for within in result['within_configurations'].values():
                    _runtime_comparison(within, mid, conditions)
                result['provenance_status'] = 'series_and_artifact_hashes_verified'
                comparisons[mid] = result
                continue
            if mid in STAGES:
                result = analyze_stage_repetitions(segments, mid, items)
            else:
                result = analyze_coding_repetitions(segments, codebook, mid, items, label_mode=label_mode)
            _runtime_comparison(result, mid, conditions)
            comparisons[mid] = result
        # Detect changes while reading, even from processes outside our series lock.
        for parent, original, sample_identity in checked:
            _, current = _sample_run(parent, sample_identity, modules)
            if current != original:
                raise ValueError('Lauf während der Diagnose geändert; erneut prüfen.')
        _check_plan(plan)
        current_identity = _sensitivity_records(root, plan)[1] if sensitivity else _identity(config_path, config)
        if (current_identity != identity or file_hash(receipt_path) != receipt_hash):
            raise ValueError('Seriengrundlage während der Diagnose geändert.')
        output = {'schema_version': 1, 'kind': kind, 'model_calls': 0,
            'processing_status': 'completed' if all(r['processing_status'] == 'completed' for r in comparisons.values()) else 'incomplete',
            'execution_fingerprint': identity, 'plan_fingerprint': plan['plan_fingerprint'],
            'source_provenance': plan['source_provenance'], 'conditions': conditions, 'comparisons': comparisons,
            'derived_modules': [mid for mid in by_id if mid not in comparable],
            'local_digests': sorted(all_digests),
            'model_identity_status': 'local_digest_observed' if all_digests else 'not_observed_or_cloud_weights_unverifiable',
            'notes': ['Gleiche Parameterprofile bestätigen Übertragung, nicht serverinterne Durchsetzung.',
                      'Anfragezahlen können sich durch Reparaturen und variable Analyseschritte unterscheiden.',
                      'Fehlende Laufzeitnachweise erlauben nur einen Vergleich unter gleichen konfigurierten Bedingungen.',
                      'Agreement und Prüfliste sind abgeleitete Ergebnisse, keine zusätzlichen unabhängigen Wiederholungen.']}
        if sensitivity:
            output['configurations'] = [{key: row[key] for key in
                ('configuration_id', 'changes', 'joint_changes', 'configuration_fingerprint')}
                for row in plan['configurations']]
            output['model_digests'] = {name: sorted(values) for name, values in model_digests.items()}
            output['model_identity_status'] = 'local_digest_observed_per_model' if all_digests else 'not_observed_or_cloud_weights_unverifiable'
            output['notes'] += ['Vorlagenänderungen sind gespeichert; die tatsächliche Verwendung jedes Promptpfads ist nicht gesondert nachgewiesen.',
                'Mehrere gleichzeitig geänderte Parameter erlauben keine Zuordnung zu einer einzelnen Ursache.',
                'Unterschiede sind Prüfhinweise, keine automatisch erkannten Fehler oder Verbesserung.']
        return output


def _runtime_comparison(result, mid, conditions):
    result['provenance_status'] = 'series_and_artifact_hashes_verified'
    runtime_ids = []
    for sid in result['included_samples']:
        condition = next(c for c in conditions if c['sample_id'] == sid)
        runtime_ids.append({p['fingerprint'] for p in condition['runtime']['profiles'] if p['module'] == mid})
    result['runtime_comparison'] = {
        'parameter_profiles_same': all(p == runtime_ids[0] for p in runtime_ids[1:])
            if len(runtime_ids) >= 2 and all(runtime_ids) else None,
        'samples_with_accepted_requests': sum(bool(p) for p in runtime_ids),
        'server_parameter_enforcement': 'not_verifiable'}
