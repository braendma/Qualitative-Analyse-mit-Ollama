"""Application boundary for verified, opt-in thematic module execution."""
from copy import deepcopy
import json
import os
from pathlib import Path

import yaml

from analysis_perspectives import normalize_analysis_perspectives, perspective_capabilities, perspective_effort


IMPLEMENTED = ('clusterer', 'summarizer', 'swot')


def modes(config):
    result = normalize_analysis_perspectives(config, implemented_modules=IMPLEMENTED)
    # A replacement script must not accidentally inherit a built-in capability.
    modules = config.get('pipeline', {}).get('modules', [])
    for module in modules:
        mid = module.get('id') if isinstance(module, dict) else None
        if mid in IMPLEMENTED and result[mid] != 'qualitative' and module.get('script') != mid + '.py':
            raise ValueError('Zusätzliche Analyseperspektiven benötigen das unveränderte Standardmodul: ' + mid)
    return result


def capability(module):
    implemented = IMPLEMENTED if module.get('script') == module['id'] + '.py' else ()
    return next((row for row in perspective_capabilities(implemented_modules=implemented)
                 if row['module_id'] == module['id']), None)


def default_modes(config):
    selected = modes(config)
    present = {m['id'] for m in config.get('pipeline', {}).get('modules', [])}
    return {mid: mode for mid, mode in selected.items() if mid in present}


def effort(config, modules):
    modes(config)
    return perspective_effort(config, [m['id'] for m in modules if m['id'] in
                              {r['module_id'] for r in perspective_capabilities()}], implemented_modules=IMPLEMENTED)


def validate_material(config_path, config, modules, input_path=None):
    selected = modes(config)
    if any(selected.get(m['id'], 'qualitative') != 'qualitative' for m in modules):
        from thematic_material import load_counting_material
        return load_counting_material(config_path, input_path)
    return None


def prepare(module, config_path, *, input_path=None, cluster_path=None, idmap_path=None, summary_path=None):
    """Verify inputs and source files before the existing core makes any call."""
    from coding_validation_common import resolve_config_path
    from runtime_support import file_hash
    from thematic_material import load_counting_material
    from thematic_adapters import build_cluster_topics, build_summary_topics
    config_path = Path(config_path).resolve()
    config = yaml.safe_load(config_path.read_text(encoding='utf-8-sig'))
    mode = modes(config)[module]
    if mode == 'qualitative':
        return None
    run_path = os.environ.get('WORKFLOW_RUN_DIR')
    runner_input = os.environ.get('WORKFLOW_INPUT_CSV')
    in_runner = bool(os.environ.get('WORKFLOW_FINGERPRINT') or os.environ.get('WORKFLOW_MODULE'))
    if in_runner and (not run_path or not runner_input or not os.environ.get('WORKFLOW_FINGERPRINT')):
        raise ValueError('Perspektivprüfung benötigt den vollständigen Eingabe- und Laufnachweis des Runners.')
    actual_input = resolve_config_path(config_path, input_path or runner_input, config.get('paths', {}).get('input_csv'))
    material = load_counting_material(config_path, actual_input, run_dir=run_path if in_runner else None)
    book = resolve_config_path(config_path, None, config['paths']['category_system_csv'])
    files = {str(p): file_hash(p) for p in (config_path, actual_input, book)}
    manifest = None
    if in_runner:
        manifest = json.loads((Path(run_path) / 'workflow_manifest.json').read_text(encoding='utf-8'))
        if manifest.get('fingerprint') != os.environ['WORKFLOW_FINGERPRINT']:
            raise ValueError('Perspektivprüfung gehört nicht zum aktuellen Runner-Lauf.')

    def source(path, source_module=None):
        path = Path(path).resolve()
        if manifest is not None:
            from diagnostic_sources import load_declared_artifact
            try:
                relative = path.relative_to(Path(run_path).resolve()).as_posix()
            except ValueError:
                raise ValueError('Analysevorstufe liegt außerhalb des geprüften Laufs.') from None
            matching = [digest for name, digest in manifest.get('output_hashes', {}).items()
                        if Path(run_path, name).resolve() == path]
            if len(matching) != 1 or file_hash(path) != matching[0]:
                raise ValueError('Analysevorstufe hat keinen passenden Output-Prüfnachweis.')
            if source_module:
                declared = next((m for m in config['pipeline']['modules'] if m['id'] == source_module), None)
                if declared is None:
                    raise ValueError('Benötigte Analysevorstufe fehlt im Modulvertrag.')
                verified = load_declared_artifact(run_path, declared, manifest)
                if verified['status'] != 'available' or Path(run_path, verified['artifact']).resolve() != path:
                    raise ValueError('Analysevorstufe ist nicht vollständig und unverändert nachgewiesen.')
        digest = file_hash(path)
        payload = json.loads(path.read_text(encoding='utf-8'))
        if file_hash(path) != digest:
            raise ValueError('Analysevorstufe wurde während des Einlesens verändert.')
        files[str(path)] = digest
        return payload

    clusters = None
    if module != 'clusterer':
        if cluster_path is None or idmap_path is None:
            raise ValueError('Cluster und Originaltext-Zuordnung werden für die Perspektivprüfung benötigt.')
        clusters = source(cluster_path, 'clusterer')
        build_cluster_topics(material, clusters)
        mapping = source(idmap_path)
        expected = {sid: material['units'][row['unit_id']]['text'] for sid, row in material['segment_index'].items()}
        if mapping != expected:
            raise ValueError('Originaltext-Zuordnung stimmt nicht vollständig mit der bestätigten CSV überein. Clusterung neu ausführen.')
        if module == 'swot':
            if summary_path is None:
                raise ValueError('Geprüfte Clusterzusammenfassungen fehlen für die SWOT-Perspektive.')
            build_summary_topics(material, clusters, source(summary_path, 'summarizer'))
    return {'module_id': module, 'mode': mode, 'material': material, 'clusters': clusters, 'files': files}


def finish(prepared, payload, markdown, params, *, llm=None):
    if prepared is None:
        return markdown, payload
    from runtime_support import file_hash
    from thematic_execution import execute_perspective, perspective_markdown
    def unchanged():
        if any(file_hash(path) != expected for path, expected in prepared['files'].items()):
            raise ValueError('Eingaben oder Vorstufen wurden während der Analyse verändert; neuen Lauf mit geprüften Daten starten.')
    unchanged()
    result = execute_perspective(prepared['module_id'], prepared['mode'], prepared['material'], payload, params,
                                 cluster_payload=prepared['clusters'], llm=llm)
    unchanged()
    output = deepcopy(payload)
    output['analysis_perspective'] = result
    return ('# Gemeinsame qualitative Ausgangsbasis\n\n'
            'Die folgende Ausgangsanalyse bleibt als Grundlage nachvollziehbar. Die gewählte '
            'Analyseperspektive mit berechneten Zahlen folgt im Abschnitt „Häufigkeitsinformierte Analyseperspektive“.\n\n'
            + markdown + perspective_markdown(result)), output
