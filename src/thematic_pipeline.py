"""Application boundary for verified, opt-in thematic module execution."""
from copy import deepcopy
import json
import os
from pathlib import Path

import yaml
from runtime_support import run_artifact_path
from filesystem_paths import canonical_path, io_path

from analysis_perspectives import normalize_analysis_perspectives, perspective_capabilities, perspective_effort


IMPLEMENTED = ('clusterer', 'summarizer', 'swot', 'meta_swot',
               'person_analysis', 'ambiguity_analysis', 'person_comparison', 'contrast_analysis', 'relation_analysis', 'overall_synthesis')
FULL_ASSIGNMENT_MODULES = ('swot', 'meta_swot', 'person_analysis', 'ambiguity_analysis', 'person_comparison', 'contrast_analysis', 'relation_analysis', 'overall_synthesis')


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


def _relation_receipt_needed(config, selected):
    """A qualitative relation may supply provenance to a counted synthesis."""
    if selected.get('overall_synthesis', 'qualitative') == 'qualitative':
        return False
    from synthesis_inputs import sources_from_module, bind_source_modules
    modules = config.get('pipeline', {}).get('modules', [])
    synthesis = next((m for m in modules if m['id'] == 'overall_synthesis' and m.get('enabled', True)), None)
    if synthesis is None:
        return False
    bindings = bind_source_modules(sources_from_module(synthesis), modules, run_artifact_path("."))
    return any(binding['module_id'] == 'relation_analysis' for binding in bindings.values())


def prepare(module, config_path, *, input_path=None, cluster_path=None, idmap_path=None,
            summary_path=None, swot_path=None, person_path=None, comparison_path=None, source_paths=None):
    """Verify inputs and source files before the existing core makes any call."""
    from coding_validation_common import resolve_config_path
    from runtime_support import file_hash
    from thematic_material import load_counting_material
    from thematic_adapters import build_cluster_topics, build_summary_topics, build_swot_topics
    config_path = Path(config_path).resolve()
    config = yaml.safe_load(config_path.read_text(encoding='utf-8-sig'))
    selected = modes(config)
    mode = selected[module]
    provenance_only = module == 'relation_analysis' and mode == 'qualitative' and _relation_receipt_needed(config, selected)
    if mode == 'qualitative' and not provenance_only:
        return None
    run_path = os.environ.get('WORKFLOW_RUN_DIR')
    runner_input = os.environ.get('WORKFLOW_INPUT_CSV')
    in_runner = any(os.environ.get(key) for key in
                    ('WORKFLOW_FINGERPRINT', 'WORKFLOW_MODULE', 'WORKFLOW_RUN_DIR', 'WORKFLOW_INPUT_CSV'))
    if in_runner and (not run_path or not runner_input or not os.environ.get('WORKFLOW_FINGERPRINT')):
        raise ValueError('Perspektivprüfung benötigt den vollständigen Eingabe- und Laufnachweis des Runners.')
    if os.environ.get('WORKFLOW_MODULE') and os.environ['WORKFLOW_MODULE'] != module:
        raise ValueError('Perspektivprüfung passt nicht zum aktuellen Runner-Modul.')
    actual_input = resolve_config_path(config_path, input_path or runner_input, config.get('paths', {}).get('input_csv'))
    material = load_counting_material(config_path, actual_input, run_dir=run_path if in_runner else None)
    book = resolve_config_path(config_path, None, config['paths']['category_system_csv'])
    files = {str(p): file_hash(p) for p in (config_path, actual_input, book)}
    manifest = None
    if in_runner:
        manifest = json.loads(io_path(Path(run_path) / 'workflow_manifest.json').read_text(encoding='utf-8'))
        if manifest.get('fingerprint') != os.environ['WORKFLOW_FINGERPRINT']:
            raise ValueError('Perspektivprüfung gehört nicht zum aktuellen Runner-Lauf.')

    def source(path, source_module=None):
        # Declared upstream filenames are relative to the scientific run, while
        # the managed process can have an unrelated short working directory.
        path = canonical_path(run_artifact_path(path))
        if manifest is not None:
            from diagnostic_sources import load_declared_artifact
            try:
                relative = path.relative_to(canonical_path(run_path)).as_posix()
            except ValueError:
                raise ValueError('Analysevorstufe liegt außerhalb des geprüften Laufs.') from None
            matching = [digest for name, digest in manifest.get('output_hashes', {}).items()
                        if canonical_path(Path(run_path, name)) == path]
            if len(matching) != 1 or file_hash(path) != matching[0]:
                raise ValueError('Analysevorstufe hat keinen passenden Output-Prüfnachweis.')
            if source_module:
                declared = next((m for m in config['pipeline']['modules'] if m['id'] == source_module), None)
                if declared is None:
                    raise ValueError('Benötigte Analysevorstufe fehlt im Modulvertrag.')
                verified = load_declared_artifact(run_path, declared, manifest)
                if verified['status'] != 'available' or canonical_path(Path(run_path, verified['artifact'])) != path:
                    raise ValueError('Analysevorstufe ist nicht vollständig und unverändert nachgewiesen.')
        digest = file_hash(path)
        payload = json.loads(io_path(path).read_text(encoding='utf-8'))
        if file_hash(path) != digest:
            raise ValueError('Analysevorstufe wurde während des Einlesens verändert.')
        files[str(path)] = digest
        return payload

    clusters = swot = persons = comparison = summaries = None
    if module in ('summarizer', 'swot', 'person_analysis', 'relation_analysis'):
        if cluster_path is None:
            raise ValueError('Cluster und Originaltext-Zuordnung werden für die Perspektivprüfung benötigt.')
        clusters = source(cluster_path, 'clusterer')
        build_cluster_topics(material, clusters)
    if module in ('summarizer', 'swot', 'person_analysis', 'ambiguity_analysis', 'relation_analysis'):
        if idmap_path is None:
            raise ValueError('Vollständige Originaltext-Zuordnung fehlt für die Perspektivprüfung.')
        mapping = source(idmap_path)
        expected = {sid: material['units'][row['unit_id']]['text'] for sid, row in material['segment_index'].items()}
        if mapping != expected:
            raise ValueError('Originaltext-Zuordnung stimmt nicht vollständig mit der bestätigten CSV überein. Clusterung neu ausführen.')
        if module in ('swot', 'person_analysis', 'relation_analysis'):
            if summary_path is None:
                raise ValueError('Geprüfte Clusterzusammenfassungen fehlen für die Analyseperspektive.')
            summaries = source(summary_path, 'summarizer')
            build_summary_topics(material, clusters, summaries)
    if module == 'meta_swot':
        if swot_path is None:
            raise ValueError('Geprüfte originale SWOT-Analyse fehlt für die Meta-SWOT-Perspektive.')
        swot = source(swot_path, 'swot')
        build_swot_topics(material, swot)
    if module in ('ambiguity_analysis', 'person_comparison', 'contrast_analysis'):
        from thematic_person_adapters import build_person_topics
        if person_path is None:
            raise ValueError('Geprüfte originale Personenanalyse fehlt für die zusätzliche Analyseperspektive.')
        persons = source(person_path, 'person_analysis')
        build_person_topics(material, persons)
    if module == 'contrast_analysis':
        from thematic_comparison_adapter import build_person_comparison_topics
        if comparison_path is None:
            raise ValueError('Geprüfter originaler Personenvergleich fehlt für die Kontrastperspektive.')
        comparison = source(comparison_path, 'person_comparison')
        build_person_comparison_topics(material, comparison, persons)
    sources = bindings = upstreams = None
    if module == 'overall_synthesis':
        from synthesis_inputs import sources_from_module, bind_source_modules
        from synthesis_material import UPSTREAMS, validate_source_material
        from diagnostic_sources import declared_json
        modules = config.get('pipeline', {}).get('modules', [])
        declared = next((m for m in modules if m['id'] == module), None)
        if declared is None or not isinstance(source_paths, dict) or not source_paths:
            raise ValueError('Syntheseperspektive benötigt die tatsächliche Quellenauswahl und ihren gespeicherten Modulvertrag.')
        actual_sources = {label: str(path) for label, path in source_paths.items()}
        bindings = bind_source_modules(actual_sources, modules, run_artifact_path("."))
        expected_bindings = bind_source_modules(sources_from_module(declared), modules, run_artifact_path("."))
        if bindings != expected_bindings:
            raise ValueError('Synthesequellenauswahl weicht vom gespeicherten Modulvertrag ab. Quellenargumente in der Konfiguration anpassen.')
        by_id = {m['id']: m for m in modules}
        upstreams = {}
        def load_upstream(mid):
            if mid in upstreams:
                return
            declaration = by_id.get(mid)
            if declaration is None or not declaration.get('enabled', True) or declaration.get('script') != mid + '.py':
                raise ValueError('Geprüfte Standardvorstufe fehlt für die Syntheseperspektive: ' + mid)
            for required in UPSTREAMS.get(mid, ()):
                load_upstream(required)
            upstreams[mid] = source(declared_json(declaration), mid)
        for binding in bindings.values():
            load_upstream(binding['module_id'])
        sources = {label: upstreams[binding['module_id']] for label, binding in bindings.items()}
        validate_source_material(material, sources, bindings, upstreams)
    return {'module_id': module, 'mode': mode, 'material': material, 'clusters': clusters,
            'swot': swot, 'persons': persons, 'comparison': comparison, 'summaries': summaries, 'files': files,
            'source_payloads': sources, 'source_bindings': bindings, 'source_upstreams': upstreams}


def finish(prepared, payload, markdown, params, *, llm=None):
    if prepared is None:
        return markdown, payload
    from runtime_support import file_hash
    from thematic_execution import execute_perspective, perspective_markdown
    def unchanged():
        if any(file_hash(path) != expected for path, expected in prepared['files'].items()):
            raise ValueError('Eingaben oder Vorstufen wurden während der Analyse verändert; neuen Lauf mit geprüften Daten starten.')
    unchanged()
    if prepared['mode'] == 'qualitative':
        # Provenance-only preparation must not activate a frequency perspective.
        return markdown, payload
    result = execute_perspective(prepared['module_id'], prepared['mode'], prepared['material'], payload, params,
                                 cluster_payload=prepared['clusters'], swot_payload=prepared.get('swot'),
                                 person_payload=prepared.get('persons'), comparison_payload=prepared.get('comparison'),
                                 summary_payload=prepared.get('summaries'), source_payloads=prepared.get('source_payloads'),
                                 source_bindings=prepared.get('source_bindings'), source_upstreams=prepared.get('source_upstreams'), llm=llm)
    unchanged()
    output = deepcopy(payload)
    output['analysis_perspective'] = result
    return ('# Gemeinsame qualitative Ausgangsbasis\n\n'
            'Die folgende Ausgangsanalyse bleibt als Grundlage nachvollziehbar. Die gewählte '
            'Analyseperspektive mit berechneten Zahlen folgt im Abschnitt „Häufigkeitsinformierte Analyseperspektive“.\n\n'
            + markdown + perspective_markdown(result)), output
