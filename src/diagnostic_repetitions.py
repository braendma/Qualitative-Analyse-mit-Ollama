"""Prepare isolated repetitions for the existing runner; no execution or file writes."""
import copy
import importlib
from pathlib import Path, PureWindowsPath
import yaml

from diagnostic_sources import STAGES
from llm_providers import transport_selection
from provider_keys import reject_config_secrets
from runtime_support import file_hash, fingerprint

ANALYSES = set(STAGES) | {'code_verification', 'blind_coding', 'coding_agreement', 'review_queue'}
MAX_REPETITIONS = 20
WRITE_FLAGS = {'--checkpoint', '--plots-dir', '--log-file', '--idmap-json', '-x', '-o'}


def _local_output(value):
    if not isinstance(value, str) or not value or value.startswith('-') or '{' in value or '}' in value:
        raise ValueError('Wiederholung benötigt feste relative Ausgabepfade innerhalb des einzelnen Laufs.')
    path = PureWindowsPath(value)
    if (path.drive or path.root or '..' in path.parts or str(path) == '.'
            or any(':' in p or p.endswith((' ', '.')) or any(ord(c) < 32 for c in p) for p in path.parts)
            or path.is_reserved()):
        raise ValueError('Wiederholung darf keinen Ausgabe- oder Checkpointpfad außerhalb ihres Laufs verwenden.')
    if path.parts[0].casefold() in {'workflow_manifest.json', 'config_snapshot.yaml', 'progress.json', '_runtime_evidence'}:
        raise ValueError('Wiederholung darf keine Steuerdateien als Modulausgabe verwenden.')


def _check_outputs(module):
    if not isinstance(module.get('outputs', []), list) or not isinstance(module.get('args', []), list):
        raise ValueError('Modulargumente und Ausgaben müssen Listen sein.')
    for name in module.get('outputs', []):
        _local_output(name)
    args = module.get('args', [])
    for index, arg in enumerate(args):
        if not isinstance(arg, str):
            raise ValueError('Wiederholungen benötigen eindeutige textuelle Modulargumente.')
        flag, separator, attached = arg.partition('=')
        if flag == '--mock-responses-json':
            raise ValueError('Gespeicherte Mockantworten sind keine unabhängigen Modellwiederholungen.')
        if flag in WRITE_FLAGS or flag.startswith('--out-') or flag.startswith('--queue-'):
            value = attached if separator else args[index + 1] if index + 1 < len(args) else None
            _local_output(value)


def prepare_repetitions(config_path, module_ids, *, repetitions=3):
    """Return a deterministic plan. A future executor must assign fresh runner directories."""
    if type(repetitions) is not int or not 2 <= repetitions <= MAX_REPETITIONS:
        raise ValueError(f'Wiederholungszahl muss eine ganze Zahl zwischen 2 und {MAX_REPETITIONS} sein.')
    if not isinstance(module_ids, list) or not module_ids or any(not isinstance(x, str) for x in module_ids):
        raise ValueError('Mindestens ein Analysenmodul ausdrücklich für die Wiederholung auswählen.')
    if len(set(module_ids)) != len(module_ids) or set(module_ids) - ANALYSES:
        raise ValueError('Doppelte, unbekannte oder rekursive Diagnosemodule sind keine Wiederholungsziele.')
    path = Path(config_path).resolve()
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict) or config.get('_diagnostic_child'):
        raise ValueError('Verschachtelte Wiederholungen sind nicht zulässig; eine ursprüngliche Konfiguration verwenden.')
    if any(not isinstance(config.get(key), dict) for key in ('llm', 'paths', 'pipeline')):
        raise ValueError('Wiederholung benötigt gültige llm-, paths- und pipeline-Zuordnungen.')
    child = copy.deepcopy(config)
    llm = child.get('llm', {})
    reject_config_secrets(child)
    selected = transport_selection(llm, llm.get('model', ''))
    if llm.get('partial_checkpoint_dir'):
        raise ValueError('Gemeinsame partial_checkpoint_dir entfernen; Wiederholungen benötigen eigene Lauf-Checkpoints.')
    runner = importlib.import_module('00_WORKFLOW_RUNNER')
    modules = runner.normalize_modules(child)
    enabled_order = runner.topological_order(modules)
    available = {m['id']: m for m in enabled_order}
    required = set(module_ids)
    if required - available.keys():
        raise ValueError('Wiederholungsziele müssen bereits in der ursprünglichen Analyse aktiviert sein.')
    pending = list(required)
    while pending:
        module = available[pending.pop()]
        for dep in module['depends_on']:
            if dep not in ANALYSES:
                raise ValueError('Analysenvorstufen dürfen keine Diagnosewiederholung auslösen.')
            if dep not in required:
                required.add(dep); pending.append(dep)
    for module in modules:
        module['enabled'] = module['id'] in required
        if module['enabled']:
            if module.get('starts_child_runs'):
                raise ValueError('Analysen mit eigenen Unterläufen sind keine zulässigen Wiederholungsziele.')
            if module['script'] != module['id'] + '.py':
                raise ValueError('Wiederholungen unterstützen nur die unveränderten Modulskripte der Analysepipeline.')
            _check_outputs(module)
    child['pipeline']['modules'] = modules
    child['_diagnostic_child'] = True
    sources = {'config_sha256': file_hash(path)}
    for key, digest in (('input_csv', 'input_sha256'), ('category_system_csv', 'codebook_sha256')):
        value = child.get('paths', {}).get(key)
        if not value:
            raise ValueError('Wiederholung benötigt paths.' + key + '.')
        source = runner.resolve_path(path.parent, value)
        if not source.is_file():
            raise ValueError('Wiederholung: Eingabe oder Kategoriensystem nicht gefunden.')
        child['paths'][key] = str(source)
        sources[digest] = file_hash(source)
    order = runner.topological_order(modules)
    configuration_fingerprint = fingerprint(child)
    plan = {'schema_version': 1, 'kind': 'stability', 'repetitions': repetitions,
            'requested_modules': list(module_ids), 'effective_modules': [m['id'] for m in order],
            'added_prerequisites': [m['id'] for m in order if m['id'] not in module_ids],
            'source_config': str(path), 'source_provenance': sources, 'config': child,
            'configuration_fingerprint': configuration_fingerprint,
            'samples': [{'sample_id': f'repeat-{i:03d}', 'configuration_fingerprint': configuration_fingerprint}
                        for i in range(1, repetitions + 1)],
            'parameter_status': 'configured_not_runtime_verified', 'provider': selected['provider'],
            'module_executions': repetitions * len(order), 'model_calls': None,
            'notes': ['Jede Stichprobe muss als neuer Lauf ohne --resume beginnen; Fortsetzen nur innerhalb derselben Stichprobe.',
                      'Gleiche konfigurierte Parameter garantieren weder identische Ergebnisse noch unveränderte Modellgewichte.',
                      'Thinking-Fallbacks und tatsächliche Laufzeitparameter müssen bei der Auswertung berücksichtigt werden.',
                      'Dies ist ein Plan; kein Modellaufruf und kein Unterlauf wurde gestartet.']}
    plan['plan_fingerprint'] = fingerprint(plan)
    return plan
