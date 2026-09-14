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
               'aussage', 'beschreibung', 'abweichung', 'position_a', 'position_b')


def strings(value):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError('Diagnosequelle: Liste von Zeichenketten erwartet.')
    return sorted(set(value))


def records(value, key):
    result = value.get(key)
    if not isinstance(result, list) or any(not isinstance(x, dict) for x in result):
        raise ValueError(f'Diagnosequelle: Ergebnisliste {key} fehlt oder ist ungültig.')
    return result


def mapping(value, key):
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f'Diagnosequelle: Ergebnisobjekt {key} fehlt oder ist ungültig.')
    return result


def project_stage(module_id, payload):
    """Project one validated artifact. No source registers are traversed wholesale."""
    if not isinstance(payload, dict):
        raise ValueError('Diagnosequelle muss ein JSON-Objekt sein.')
    if payload.get('processing_status', 'completed') != 'completed':
        raise ValueError('Unvollständige Diagnosequelle wird nicht als Ergebnis gewertet.')
    out = []
    warnings = []

    def add(path, row, *, ids=None, people=None, scope='direct', kind='finding', unresolved=None):
        out.append({'key': path, 'kind': kind, 'scope': scope,
                    'segment_ids': strings(row.get('segment_ids', []) if ids is None else ids),
                    'persons': strings([] if people is None else people),
                    'text': '\n'.join(row[k] for k in TEXT_FIELDS if isinstance(row.get(k), str)),
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
                    add(f'swot/{unit}/{dimension}/{i}', row)
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
                            ids.extend(strings(registry[fid].get('segment_ids', [])))
                    add(f'meta_swot/{dimension}/{section}/{i}', row, ids=ids,
                        kind='exception' if section == 'einzelbefunde' else 'pattern', unresolved=missing)
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
                add(f'{section}/{i}', row, people=people, scope='person_reference')
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
                add(f'{section}/{i}', row, ids=ids, scope='source_group', unresolved=missing)
                out[-1]['source_refs'] = refs
        warnings.append('Synthese: Quellengruppen beschreiben Eingabematerial, keine bestätigte Evidenz pro Aussage.')
    else:
        raise ValueError(f'Kein Diagnoseadapter für Modul {module_id}.')
    return {'records': out, 'warnings': warnings}


def declared_json(module):
    """Prefer explicit CLI output over auxiliary JSON (e.g. text mappings)."""
    args = module.get('args', [])
    for flag in ('--out-json', '-x'):
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


def load_sources(directory, config):
    """Load only completed, hash-verified declared artifacts. Never scan random files."""
    directory = Path(directory).resolve()
    manifest_path = directory / 'workflow_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    result = {}
    modules = config.get('pipeline', {}).get('modules', [])
    for module in modules:
        mid = module['id']
        if mid not in STAGES:
            continue
        if mid in result:
            raise ValueError('Doppelte Modul-ID in Diagnosekonfiguration.')
        item = result[mid] = {'status': 'unavailable', 'records': [], 'warnings': []}
        if not module.get('enabled', True):
            item['reason'] = 'disabled'
            continue
        if mid not in manifest.get('completed_steps', []):
            item['reason'] = manifest.get('module_status', {}).get(mid, 'not_verified')
            continue
        try:
            name = declared_json(module)
            path = local_file(directory, name)
            digest = file_hash(path)
            if digest != manifest.get('output_hashes', {}).get(name):
                raise ValueError('Output-Prüfsumme fehlt oder stimmt nicht überein.')
            payload = json.loads(path.read_text(encoding='utf-8'))
            projected = project_stage(mid, payload)
            item.update(projected, status='available', artifact=name, sha256=digest)
        except (OSError, ValueError, TypeError, KeyError) as exc:
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


def load_snapshot(directory, config_path, input_path):
    """Bind the diagnostic to the original input and exact saved configuration."""
    import yaml
    from coding_validation_common import load_segments
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'workflow_manifest.json').read_text(encoding='utf-8'))
    provenance = manifest.get('provenance', {})
    for key, path in (('config_sha256', config_path), ('input_sha256', input_path)):
        if not provenance.get(key) or file_hash(path) != provenance[key]:
            raise ValueError('Diagnose abgelehnt: Eingabe oder Konfiguration fehlt im Herkunftsnachweis oder wurde verändert.')
    config = yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
    return make_snapshot(load_segments(input_path, config['columns']), load_sources(directory, config))
