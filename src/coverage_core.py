"""Deterministic distributions of input material and recorded evidence selection."""
from collections import Counter

from coding_validation_common import markdown_escape

SCOPES = ('direct', 'input_association', 'source_group', 'person_reference')
DEFAULT_SCOPE = {'clusterer': 'input_association', 'summarizer': 'input_association',
                 'overall_synthesis': 'source_group', 'person_comparison': 'person_reference',
                 'contrast_analysis': 'person_reference'}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def material_units(inputs):
    """Deduplicate only explicit, consistent passage IDs; never match by text."""
    units = {}
    for sid, row in inputs.items():
        key = ('passage', row['unit_id']) if row.get('unit_id') else ('row', sid)
        if key in units:
            old = inputs[units[key][0]]
            if old['person'] != row['person'] or old['text_sha256'] != row['text_sha256']:
                raise ValueError('Passage-ID bezeichnet verschiedene Personen oder Texte.')
        units.setdefault(key, []).append(sid)
    return units


def distribution(inputs, selected_ids):
    chosen = set(selected_ids)
    if chosen - inputs.keys():
        raise ValueError('Unbekannte Segment-ID in Coverage.')
    units = material_units(inputs)
    selected_units = {k: v for k, v in units.items() if chosen.intersection(v)}
    words_total = sum(inputs[v[0]]['words'] for v in units.values())
    words_selected = sum(inputs[v[0]]['words'] for v in selected_units.values())
    by_person = []
    for person in sorted({r['person'] for r in inputs.values()}):
        source = [v for v in units.values() if inputs[v[0]]['person'] == person]
        used = [v for v in selected_units.values() if inputs[v[0]]['person'] == person]
        words = sum(inputs[v[0]]['words'] for v in source)
        selected_words = sum(inputs[v[0]]['words'] for v in used)
        by_person.append({'person': person, 'material_units': len(source),
            'material_share': ratio(len(source), len(units)), 'material_words': words,
            'material_word_share': ratio(words, words_total), 'selected_units': len(used),
            'evidence_share': ratio(len(used), len(selected_units)),
            'within_person_coverage': ratio(len(used), len(source)),
            'selected_words': selected_words, 'evidence_word_share': ratio(selected_words, words_selected)})
    categories = []
    for level in range(1, 5):
        def path(row):
            parts = row['code'].split(' > ')
            return ' > '.join(parts[:level]) if len(parts) >= level else None
        source = Counter(path(row) for row in inputs.values() if path(row) is not None)
        selected = Counter(path(inputs[sid]) for sid in chosen if path(inputs[sid]) is not None)
        for code, count in sorted(source.items()):
            categories.append({'level': level, 'code': code, 'material_coding_rows': count,
                'material_share_at_level': ratio(count, sum(source.values())),
                'selected_coding_rows': selected[code],
                'evidence_share_at_level': ratio(selected[code], sum(selected.values())),
                'within_code_coverage': ratio(selected[code], count)})
    return {'selected_segment_ids': sorted(chosen), 'selected_coding_rows': len(chosen),
            'input_coding_rows': len(inputs), 'material_units': len(units),
            'selected_units': len(selected_units), 'unit_coverage': ratio(len(selected_units), len(units)),
            'by_person': by_person, 'by_category': categories,
            'unreferenced_segment_ids': sorted(inputs.keys() - chosen)}


def analyze_coverage(snapshot):
    inputs = snapshot['inputs']
    # Fail on inconsistent explicit passage IDs even if no stage is available.
    material_units(inputs)
    stages = {}
    for mid, stage in snapshot['stages'].items():
        result = stages[mid] = {'status': stage['status'], 'warnings': stage.get('warnings', []), 'scopes': {}}
        if stage['status'] != 'available':
            result['reason'] = stage.get('reason', 'unavailable')
            continue
        valid = [r for r in stage['records'] if r['valid']]
        result['invalid_records'] = [r['key'] for r in stage['records'] if not r['valid']]
        for scope in SCOPES:
            rows = [r for r in valid if r['scope'] == scope]
            selected = {sid for row in rows for sid in row['segment_ids']}
            persons = {person for row in rows for person in row['persons']}
            # A named source without a saved segment link cannot yield zero coverage.
            no_links = [r['key'] for r in rows if scope == 'source_group' and not r['segment_ids']]
            applicable = bool(rows) or scope == DEFAULT_SCOPE.get(mid, 'direct')
            measured = scope != 'person_reference' and applicable and not no_links and not result['invalid_records']
            result['scopes'][scope] = {'record_count': len(rows), 'persons_named': sorted(persons),
                'unlinked_records': no_links, 'measurable': measured,
                'distribution': distribution(inputs, selected) if measured else None}
    return {'schema_version': 1, 'processing_status': 'completed', 'model_calls': 0,
        'input_fingerprint': snapshot['input_fingerprint'], 'stages': stages,
        'material': distribution(inputs, inputs.keys()),
        'unit_basis': 'explicit_passages' if inputs and all(r.get('unit_id') for r in inputs.values()) else 'rows_with_explicit_passages_grouped',
        'methodological_note': 'Coverage beschreibt gespeicherte Referenzen, keine qualitative Güte. '
            'Personenanteile verwenden eindeutige explizite Passagen, sonst einzelne Codierzeilen. '
            'Kategorieanteile beziehen sich auf Codierzeilen je Hierarchieebene. '
            'Wortanteile sind Anteile der exportierten Stellen, nicht vollständiger Interviews. '
            'Quellengruppen sind keine bestätigten Belege jeder Syntheseaussage. '
            'Fehlende oder ungültige Referenzdaten ergeben keine Nullabdeckung.'}


def render_coverage(result):
    lines = ['# Coverage und Blind Spots', '', result['methodological_note'], '']
    labels = {'direct': 'Ausgewählte Segmentbelege', 'input_association': 'Zugeordnetes Eingabematerial',
              'source_group': 'Material zitierter Quellengruppen', 'person_reference': 'Personenreferenzen'}
    percent = lambda value: 'nicht bestimmbar' if value is None else f'{100 * value:.1f} %'
    for mid, stage in result['stages'].items():
        lines += ['## ' + markdown_escape(mid), '']
        if stage['status'] != 'available':
            lines += ['Nicht auswertbar: ' + markdown_escape(stage.get('reason', stage['status'])), '']
            continue
        if stage['invalid_records']:
            lines += [f"Ungültige Referenzeinträge: {len(stage['invalid_records'])}. Keine vollständige Abdeckung berechnet.", '']
        for scope, item in stage['scopes'].items():
            if not item['record_count'] and not item['measurable']:
                continue
            lines += ['### ' + labels[scope], '']
            data = item['distribution']
            if data is None:
                lines += ['Segmentabdeckung nicht bestimmbar; gespeicherte Personenreferenzen: ' +
                          (', '.join(markdown_escape(x) for x in item['persons_named']) or 'keine'), '']
                continue
            lines += [f"{data['selected_units']} von {data['material_units']} Materialeinheiten referenziert.", '',
                      '| Person | Anteil am Material | Anteil an der Evidenzauswahl | Innerhalb der Person referenziert |',
                      '|---|---:|---:|---:|']
            for row in data['by_person']:
                lines.append('| ' + markdown_escape(row['person']) + ' | ' + ' | '.join(percent(row[k]) for k in (
                    'material_share', 'evidence_share', 'within_person_coverage')) + ' |')
            lines += ['', '| Ebene / Code | Codierzeilen | Referenzierte Codierzeilen |', '|---|---:|---:|']
            for row in data['by_category']:
                lines.append(f"| {row['level']} / {markdown_escape(row['code'])} | {row['material_coding_rows']} | {row['selected_coding_rows']} |")
            lines += ['', 'Nicht referenzierte Codierzeilen: ' + (', '.join(markdown_escape(x) for x in data['unreferenced_segment_ids']) or 'keine'), '']
        lines += [markdown_escape(w) for w in stage['warnings']] + ['']
    return '\n'.join(lines)
