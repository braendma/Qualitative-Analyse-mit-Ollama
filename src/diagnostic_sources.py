"""Read-only, schema-aware evidence projection for scientific diagnostics.

Registers and model input inventories are not selected evidence. Direct evidence,
cluster input associations and synthesis source groups remain distinguishable.
"""
import json
from pathlib import Path

from html_report import local_file
from runtime_support import file_hash, fingerprint
from synthesis_sources import source_details

DIMENSIONS = ('Stärken', 'Schwächen', 'Chancen', 'Risiken')
STAGES = ('clusterer', 'summarizer', 'swot', 'meta_swot', 'person_analysis',
          'person_comparison', 'contrast_analysis', 'relation_analysis',
          'ambiguity_analysis', 'evidence_audit', 'overall_synthesis')
TEXT_FIELDS = ('thema', 'definition', 'summary', 'verdichtung', 'analyse',
               'aussage', 'beschreibung', 'abweichung', 'position_a', 'position_b',
               'cluster_name', 'typ_name', 'muster', 'bezugs_muster', 'begruendung',
               'bedeutung', 'einordnung')


def strings(value):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError('Diagnosequelle: Liste von Zeichenketten erwartet.')
    return sorted(set(value))


def records(value, key):
    if not isinstance(value, dict):
        raise ValueError('Diagnosequelle: Ergebnisobjekt erwartet.')
    result = value.get(key)
    if not isinstance(result, list) or any(not isinstance(x, dict) for x in result):
        raise ValueError(f'Diagnosequelle: Ergebnisliste {key} fehlt oder ist ungültig.')
    return result


def mapping(value, key):
    if not isinstance(value, dict):
        raise ValueError('Diagnosequelle: Ergebnisobjekt erwartet.')
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f'Diagnosequelle: Ergebnisobjekt {key} fehlt oder ist ungültig.')
    return result


def _thematic_projection(module_id, payload, segments, upstream_payloads=None):
    """Reproduce metrics from original units; project no matrix/scope as evidence."""
    from thematic_material import build_material
    from thematic_counts import count_topics
    from thematic_adapters import build_cluster_topics, build_summary_topics, build_swot_topics

    def require(condition):
        if not condition:
            raise ValueError('Analyseperspektive passt nicht zu Modul, Originalmaterial oder Themenquelle.')

    extension = payload['analysis_perspective']
    require(module_id in ('clusterer', 'summarizer', 'swot', 'meta_swot', 'person_analysis', 'ambiguity_analysis')
            and isinstance(extension, dict))
    upstream_payloads = {} if upstream_payloads is None else upstream_payloads
    require(isinstance(upstream_payloads, dict))
    require(type(extension.get('schema_version')) is int and extension['schema_version'] == 1)
    require(extension.get('module_id') == module_id and extension.get('selected_mode') in ('frequency', 'both'))
    from thematic_interpretation import comparison_basis
    legacy_basis = 'all_fixed_topics' if module_id in ('clusterer', 'summarizer', 'swot') else None
    require(extension.get('interpretation_comparison_basis', legacy_basis) == comparison_basis(module_id))
    require(extension.get('candidate_basis') == 'original_unweighted_findings' and segments is not None)
    counted = extension.get('counting')
    require(isinstance(counted, dict))
    material = build_material(segments, person_basis=counted.get('person_basis'))
    # The material-content hash and recomputed metrics verify the actual supplied
    # original units; the surrounding artifact loader verifies run/config hashes.
    material['basis_fingerprint'] = counted.get('basis_fingerprint')
    require(count_topics(material, counted.get('definitions'), counted.get('assignments')) == counted)
    original = {key: value for key, value in payload.items() if key != 'analysis_perspective'}
    if module_id == 'clusterer':
        prepared = build_cluster_topics(material, original)
    elif module_id == 'swot':
        prepared = build_swot_topics(material, original)
    elif module_id == 'meta_swot':
        from thematic_meta_adapter import build_meta_swot_topics
        require(isinstance(upstream_payloads.get('swot'), dict))
        prepared = build_meta_swot_topics(material, original, upstream_payloads['swot'])
    elif module_id == 'person_analysis':
        from thematic_person_adapters import build_person_topics
        prepared = build_person_topics(material, original)
    elif module_id == 'ambiguity_analysis':
        from thematic_person_adapters import build_ambiguity_topics
        require(isinstance(upstream_payloads.get('person_analysis'), dict))
        prepared = build_ambiguity_topics(material, original, upstream_payloads['person_analysis'])
    else:
        # Summary records contain exact cluster identity and membership. Rebuild
        # that structural source without pretending to recover plots/timestamps
        # from the separate original cluster artifact.
        metadata = {s.segment_id: {'person': s.person, 'unit_id': s.unit_id} for s in segments}
        clusters = {'processing_status': 'completed', 'segment_metadata': metadata,
                    'clusters': original.get('cluster_summaries')}
        prepared = build_summary_topics(material, clusters, original)
    require(extension.get('source_links') == prepared['source_links'])
    require(counted['definitions'] == prepared['topics'])
    if prepared['assignments'] is not None:
        require(counted['assignments'] == prepared['assignments'])
    origin = ('complete_cluster_membership' if module_id in ('clusterer', 'summarizer')
              else 'full_scoped_model_assignment')
    require(extension.get('assignment_origin') == origin)
    require(extension.get('unassigned_context') == prepared.get('unassigned_context', {}))
    digest = extension.get('candidate_source_fingerprint')
    require(isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest))
    if module_id != 'summarizer':
        require(digest == prepared['source_fingerprint'])
    # For summaries the source hash also binds the separate cluster artifact;
    # here its identity/membership is verified, its file hash is loader-owned.
    modes = ('qualitative', 'frequency') if extension['selected_mode'] == 'both' else ('frequency',)
    outputs = extension.get('interpretations')
    require(isinstance(outputs, dict) and set(outputs) == set(modes))
    topics = {topic['topic_id']: topic for topic in counted['definitions']}
    result = []
    def add(tid, perspective, kind, text):
        result.append({'key': 'analysis_perspective/' + tid + '/' + perspective,
            'kind': kind, 'scope': 'thematic_result',
            'comparison_context': ['analysis_perspective', tid, perspective],
            'segment_ids': [], 'persons': [], 'text': text, 'unresolved': []})
    for mode in modes:
        rows = outputs[mode]
        require(isinstance(rows, list))
        seen = set()
        fields = {'topic_id', 'interpretation'} | ({'counterpositions', 'limitations'} if mode == 'frequency' else set())
        for row in rows:
            require(isinstance(row, dict) and set(row) == fields)
            require(all(isinstance(row[key], str) and bool(row[key].strip()) for key in fields))
            tid = row['topic_id']
            require(tid in topics and tid not in seen)
            seen.add(tid)
            if mode == 'qualitative':
                require(row['interpretation'] == prepared['source_links'][tid]['qualitative_text'])
            text = '\n'.join(key + ': ' + row[key] for key in sorted(fields - {'topic_id'}))
            add(tid, mode, 'thematic_interpretation', text)
        require(seen == set(topics))
    for row in counted['topics']:
        scope = {key: value for key, value in row['scope'].items() if key not in ('unit_ids', 'person_ids')}
        metrics = {stance: {key: value for key, value in values.items() if key not in ('unit_ids', 'person_ids')}
                   for stance, values in row['counts'].items()}
        value = {'kind': row['kind'], 'count_meaning': row['count_meaning'],
                 'scope': scope, 'coverage': row['coverage'], 'counts': metrics,
                 'assignment_review_status': counted['assignment_review_status'],
                 'person_basis': counted['person_basis']}
        add(row['topic_id'], 'counts', 'thematic_counts', json.dumps(value, ensure_ascii=False, sort_keys=True))
    return result


def project_stage(module_id, payload, *, segments=None, upstream_payloads=None):
    """Project one validated artifact. No source registers are traversed wholesale."""
    if not isinstance(payload, dict):
        raise ValueError('Diagnosequelle muss ein JSON-Objekt sein.')
    if payload.get('processing_status', 'completed') != 'completed':
        raise ValueError('Unvollständige Diagnosequelle wird nicht als Ergebnis gewertet.')
    out = []
    warnings = []

    def add(path, row, *, ids=None, people=None, scope='direct', kind='finding', unresolved=None, context=()):
        text = [row[k] for k in TEXT_FIELDS if isinstance(row.get(k), str)]
        # Explicit schema fields only: do not traverse evidence registries or whole input inventories.
        for position in row.get('personenpositionen', []):
            if isinstance(position, dict) and isinstance(position.get('position'), str):
                text.append(str(position.get('person', '')) + ': ' + position['position'])
        if isinstance(row.get('merkmale'), list):
            text.extend(value for value in row['merkmale'] if isinstance(value, str))
        out.append({'key': path, 'kind': kind, 'scope': scope, 'comparison_context': list(context),
                    'segment_ids': strings(row.get('segment_ids', []) if ids is None else ids),
                    'persons': strings([] if people is None else people),
                    'text': '\n'.join(text),
                    'unresolved': sorted(set(unresolved or []))})

    if module_id == 'clusterer':
        for i, row in enumerate(records(payload, 'clusters')):
            add(f'clusters/{i}', row, ids=row.get('segments', []), scope='input_association', kind='cluster')
    elif module_id == 'summarizer':
        for i, row in enumerate(records(payload, 'cluster_summaries')):
            add(f'cluster_summaries/{i}', row, ids=row.get('segments', []), scope='input_association', kind='summary')
        warnings.append('Die freie Gesamtzusammenfassung besitzt keine aussagenspezifischen Segmentreferenzen.')
    elif module_id == 'swot':
        for unit, value in mapping(payload, 'swot').items():
            for dimension in DIMENSIONS:
                for i, row in enumerate(records(value, dimension)):
                    add(f'swot/{unit}/{dimension}/{i}', row, context=(unit, dimension))
    elif module_id == 'meta_swot':
        registry = mapping(payload, 'finding_registry')
        for dimension, value in mapping(payload, 'meta_swot').items():
            for section in ('uebergreifende_muster', 'einzelbefunde'):
                for i, row in enumerate(records(value, section)):
                    ids = list(row.get('segment_ids', []))
                    missing = []
                    refs = row.get('finding_ids', [row['finding_id']] if 'finding_id' in row else [])
                    for fid in strings(refs):
                        if fid not in registry:
                            missing.append(fid)
                        else:
                            if not isinstance(registry[fid], dict):
                                raise ValueError('Ungültiger Befund im Quellenregister.')
                            ids.extend(strings(registry[fid].get('segment_ids', [])))
                    add(f'meta_swot/{dimension}/{section}/{i}', row, ids=ids,
                        kind='exception' if section == 'einzelbefunde' else 'pattern', unresolved=missing,
                        context=(dimension, section))
    elif module_id in ('person_analysis', 'ambiguity_analysis'):
        sections = ('ambivalenzen',) if module_id == 'ambiguity_analysis' else (
            'zentrale_themen', 'perspektiven', 'spannungsfelder', 'kontrastierende_aspekte')
        for person, value in mapping(payload, 'persons').items():
            for section in sections:
                for i, row in enumerate(records(value, section)):
                    if section == 'ambivalenzen':
                        for side in ('a', 'b'):
                            add(f'persons/{person}/{section}/{i}/{side}', row,
                                ids=row.get('segment_ids_' + side, []), people=[person], kind='ambiguity_' + side)
                    else:
                        add(f'persons/{person}/{section}/{i}', row, people=[person], kind=section)
    elif module_id == 'person_comparison':
        for section in ('gemeinsame_muster', 'zentrale_unterschiede', 'typen', 'nicht_zugeordnete_personen'):
            for i, row in enumerate(records(payload, section)):
                people = list(row.get('personen', []))
                if 'person' in row:
                    people.append(row['person'])
                people.extend(x['person'] for x in row.get('personenpositionen', []) if isinstance(x, dict) and 'person' in x)
                add(f'{section}/{i}', row, people=people, scope='person_reference', context=(section,))
        warnings.append('Personenvergleich: Personenreferenzen sind keine direkte Segmentauswahl.')
    elif module_id == 'contrast_analysis':
        for section in ('dominante_muster', 'negativfaelle', 'spannungen_zwischen_typen', 'relativierungen'):
            for i, row in enumerate(records(payload, section)):
                people = [row['person']] if 'person' in row else row.get('getragen_von', [])
                add(f'{section}/{i}', row, people=people, scope='person_reference', kind=section)
        warnings.append('Negativfälle nennen Personen; genaue Segmentbelege sind hier nicht gespeichert.')
    elif module_id == 'relation_analysis':
        for i, row in enumerate(records(payload, 'beziehungen')):
            for side in ('a', 'b'):
                add(f'beziehungen/{i}/{side}', row, ids=row.get('segment_ids_' + side, []), kind='relation_' + side)
        if payload.get('omitted_pair_count', 0):
            warnings.append(f"Nicht untersuchte Relationskandidaten: {payload['omitted_pair_count']}")
    elif module_id == 'evidence_audit':
        for i, row in enumerate(records(payload, 'befunde')):
            add(f'befunde/{i}', row)
            for j, counter in enumerate(records(row, 'gegenbelege')):
                ids = strings(counter.get('segment_ids', []))
                for side in ('a', 'b'):
                    ids += strings(counter.get('segment_ids_' + side, []))
                people = [counter['person']] if 'person' in counter else counter.get('personen', [])
                add(f'befunde/{i}/gegenbelege/{j}', counter, ids=ids, people=people,
                    scope='direct' if ids else 'person_reference', kind='counter_evidence')
    elif module_id == 'overall_synthesis':
        details = source_details(payload)
        for section in ('kernergebnisse', 'uebergreifende_muster', 'spannungen_und_relativierungen'):
            for i, row in enumerate(records(payload, section)):
                refs = strings(row.get('quellen', []))
                ids = []
                missing = []
                for ref in refs:
                    detail = details.get(ref, {})
                    ids += detail.get('segment_ids', [])
                    if not detail or detail.get('unresolved'):
                        missing.append(ref)
                add(f'{section}/{i}', row, ids=ids, scope='source_group', unresolved=missing, context=(section,))
                out[-1]['source_refs'] = refs
        warnings.append('Synthese: Quellengruppen beschreiben Eingabematerial, keine bestätigte Evidenz pro Aussage.')
    else:
        raise ValueError(f'Kein Diagnoseadapter für Modul {module_id}.')
    if 'analysis_perspective' in payload:
        thematic = _thematic_projection(module_id, payload, segments, upstream_payloads)
        for row in out:
            row['comparison_context'] = ['candidate_basis', *row['comparison_context']]
        out.extend(thematic)
        warnings.append('Ursprüngliche Befunde sind die ungewichtete Kandidatenbasis. Ausgewählte Interpretationen und berechnete Zähler werden getrennt verglichen; keine semantische Gleichheit oder menschliche Bestätigung. Themenumfang und Zuordnungsmatrix sind keine ausgewählten Belege.')
    return {'records': out, 'warnings': warnings}


def declared_json(module):
    """Prefer explicit CLI output over auxiliary JSON (e.g. text mappings)."""
    args = module.get('args', [])
    for flag in ('--out-json', '-x', '--queue-json'):
        if flag in args:
            index = args.index(flag)
            if index + 1 >= len(args):
                raise ValueError('JSON-Ausgabepfad fehlt.')
            name = args[index + 1]
            if name not in module.get('outputs', []):
                raise ValueError('JSON-Ausgabe fehlt im Outputvertrag.')
            return name
    candidates = [name for name in module.get('outputs', []) if str(name).endswith('.json')]
    if len(candidates) != 1:
        raise ValueError('JSON-Ausgabe ist nicht eindeutig deklariert.')
    return candidates[0]


def load_declared_artifact(directory, module, manifest):
    """One provenance guard for all diagnostics; decoding is not schema validation."""
    item = {'status': 'unavailable'}
    mid = module['id']
    if not module.get('enabled', True):
        item['reason'] = 'disabled'
        return item
    if mid not in manifest.get('completed_steps', []):
        item['reason'] = manifest.get('module_status', {}).get(mid, 'not_verified')
        return item
    try:
        name = declared_json(module)
        path = local_file(Path(directory).resolve(), name)
        digest = file_hash(path)
        if digest != manifest.get('output_hashes', {}).get(name):
            raise ValueError('Output-Prüfsumme fehlt oder stimmt nicht überein.')
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('Diagnosequelle muss ein JSON-Objekt sein.')
        if payload.get('processing_status', 'completed') != 'completed':
            raise ValueError('Unvollständige Diagnosequelle wird nicht als Ergebnis gewertet.')
        item.update(status='available', artifact=name, sha256=digest, payload=payload)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        item.update(status='invalid', reason=str(exc))
    return item


def load_sources(directory, config, *, segments=None):
    """Two passes: verify declared files, then project using those exact sources.

    Upstream mappings contain only available artifacts from this same manifest.
    Module array order is irrelevant; selected meta registries cannot substitute
    for a missing, incomplete or hash-mismatched original upstream artifact.
    """
    directory = Path(directory).resolve()
    manifest_path = directory / 'workflow_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    result, payloads = {}, {}
    modules = config.get('pipeline', {}).get('modules', [])
    for module in modules:
        mid = module['id']
        if mid not in STAGES:
            continue
        if mid in result:
            raise ValueError('Doppelte Modul-ID in Diagnosekonfiguration.')
        artifact = load_declared_artifact(directory, module, manifest)
        result[mid] = {**{key: value for key, value in artifact.items() if key != 'payload'},
                       'records': [], 'warnings': []}
        if artifact['status'] == 'available':
            payloads[mid] = artifact['payload']
    for mid, item in result.items():
        if item['status'] != 'available':
            continue
        try:
            item.update(project_stage(mid, payloads[mid], segments=segments, upstream_payloads=payloads))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
            item.update(status='invalid', reason=str(exc))
    return result


def make_snapshot(segments, sources):
    """Validate links against actual input IDs; exclude invalid records from metrics."""
    inputs = {}
    for segment in segments:
        if segment.segment_id in inputs:
            raise ValueError('Doppelte Segment-ID in Diagnoseeingaben.')
        inputs[segment.segment_id] = {
            'person': segment.person, 'code': segment.human_code, 'unit_id': segment.unit_id,
            'words': len(segment.text.split()), 'text_sha256': fingerprint(segment.text)}
    people = {value['person'] for value in inputs.values()}
    # Copy to guarantee callers' saved analysis structures remain untouched.
    sources = json.loads(json.dumps(sources, ensure_ascii=False))
    for stage in sources.values():
        for row in stage['records']:
            row['unknown_segment_ids'] = sorted(set(row['segment_ids']) - inputs.keys())
            row['unknown_persons'] = sorted(set(row['persons']) - people)
            row['valid'] = not (row['unknown_segment_ids'] or row['unknown_persons'] or row['unresolved'])
    return {'schema_version': 1, 'inputs': inputs, 'input_fingerprint': fingerprint(inputs), 'stages': sources,
            'note': 'Referenzen und Herkunft werden geprüft, nicht die semantische Richtigkeit. Keine Modellaufrufe.'}


def load_input_context(directory, config_path, input_path, *, require_codebook=False):
    """Bind diagnostics to saved inputs before any source is interpreted."""
    import yaml
    from coding_validation_common import resolve_config_path
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'workflow_manifest.json').read_text(encoding='utf-8'))
    provenance = manifest.get('provenance', {})
    for key, path in (('config_sha256', config_path), ('input_sha256', input_path)):
        if not provenance.get(key) or file_hash(path) != provenance[key]:
            raise ValueError('Diagnose abgelehnt: Eingabe oder Konfiguration fehlt im Herkunftsnachweis oder wurde verändert.')
    config = yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Diagnose abgelehnt: Konfiguration muss eine Zuordnung sein.')
    codebook_path = None
    if require_codebook:
        codebook_path = resolve_config_path(config_path, None, config.get('paths', {}).get('category_system_csv'))
        if not provenance.get('codebook_sha256') or file_hash(codebook_path) != provenance['codebook_sha256']:
            raise ValueError('Diagnose abgelehnt: Kategoriesystem fehlt im Herkunftsnachweis oder wurde verändert.')
    return config, manifest, codebook_path


def load_snapshot(directory, config_path, input_path):
    """Bind the diagnostic to the original input and exact saved configuration."""
    from coding_validation_common import load_segments
    config, _, _ = load_input_context(directory, config_path, input_path)
    segments = load_segments(input_path, config['columns'])
    snapshot = make_snapshot(segments, load_sources(directory, config, segments=segments))
    snapshot['dependency_edges'] = dependency_edges(config)
    return snapshot


def dependency_edges(config):
    """Only configured analytic dependencies whose declared JSON is actually an input."""
    modules = {m['id']: m for m in config.get('pipeline', {}).get('modules', [])
               if m['id'] in STAGES and m.get('enabled', True)}
    edges = []
    for target, module in modules.items():
        args = module.get('args', [])
        for source in module.get('depends_on', []):
            if source not in modules:
                continue
            try:
                path = declared_json(modules[source])
            except ValueError:
                # load_sources already marks enabled malformed sources invalid.
                continue
            if any(arg == path or (isinstance(arg, str) and arg.partition('=')[2] == path) for arg in args):
                edges.append((source, target))
    return sorted(set(edges))
