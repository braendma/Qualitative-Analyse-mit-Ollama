"""Reference transitions and explicit review questions; never a semantic loss score."""
from collections import defaultdict
import re

from coverage_core import distribution, markdown_escape, material_units
from runtime_support import fingerprint


UNCERTAINTY = re.compile(r'\b(?:vielleicht|möglicherweise|teilweise|vermutlich|könnte|könnten|unsicher|unklar)\b', re.I)
ASSERTION = re.compile(r'\b(?:immer|alle|ausnahmslos|eindeutig|zweifelsfrei|ausschließlich)\b', re.I)
PREVIEW_CHARS = 1200
MAX_CANDIDATES = 50
NOTE = ('Die Diagnose vergleicht gespeicherte Referenzen entlang konfigurierter Abhängigkeiten. '
        'Eine nicht weitergeführte Referenz beweist keinen Bedeutungsverlust; eine erhaltene Referenz '
        'beweist keinen Bedeutungserhalt. Eingabezuordnungen, direkte Belege, Personenreferenzen '
        'und Synthese-Quellengruppen besitzen unterschiedliche Aussagekraft. '
        'Sprachliche Hinweise sind deutsche Wortlisten, keine semantische Prüfung. '
        'Alle Hinweise benötigen eine Prüfung der Aussage und ihres Originalkontexts. Keine zusätzlichen Modellaufrufe.')


def _view(stage, inputs):
    if stage is None or stage['status'] != 'available':
        return {'measurable': False, 'reason': (stage or {}).get('reason', 'not_configured')}
    rows = stage['records']
    if any(not row['valid'] for row in rows):
        return {'measurable': False, 'reason': 'invalid_references'}
    no_links = [row['key'] for row in rows if row['scope'] != 'person_reference' and not row['segment_ids']]
    ids = {sid for row in rows for sid in row['segment_ids']}
    people = {p for row in rows for p in row['persons']} | {inputs[sid]['person'] for sid in ids}
    scopes = sorted({row['scope'] for row in rows})
    return {'measurable': True, 'scopes': scopes, 'people': people, 'ids': ids,
            'segment_measurable': not no_links and 'person_reference' not in scopes,
            'unlinked_records': no_links, 'records': rows}


def _excerpt(row):
    text = row['text']
    return {'record_key': row['key'], 'kind': row['kind'], 'scope': row['scope'],
            'segment_ids': row['segment_ids'], 'persons': row['persons'],
            'text_preview': text[:PREVIEW_CHARS], 'text_characters': len(text),
            'preview_truncated': len(text) > PREVIEW_CHARS, 'text_fingerprint': fingerprint(text)}


def _terms(pattern, text):
    return sorted({match.group(0).casefold() for match in pattern.finditer(text)})


def _review_rows(before, after, inputs, unit_for_id):
    """Inverted reference index avoids comparing every long text with every other text."""
    by_unit, by_person = defaultdict(set), defaultdict(set)
    target_terms = []
    for index, row in enumerate(after['records']):
        for sid in row['segment_ids']:
            by_unit[unit_for_id[sid]].add(index)
        for person in row['persons']:
            by_person[person].add(index)
        target_terms.append((_terms(UNCERTAINTY, row['text']), _terms(ASSERTION, row['text'])))
    matches = []
    for row in before['records']:
        candidates = set()
        for sid in row['segment_ids']:
            candidates.update(by_unit[unit_for_id[sid]])
        basis = 'shared_material_reference'
        # Person references remain weaker; never expand them to all that person's text.
        if not candidates and row['persons']:
            for person in row['persons']:
                candidates.update(by_person[person])
            basis = 'shared_person_reference'
        matches.append((candidates, basis))
    origin_counts = defaultdict(int)
    for candidates, _ in matches:
        for i in candidates:
            origin_counts[i] += 1
    reviews = []
    for row, (candidates, basis) in zip(before['records'], matches):
        flags = []
        uncertainty, assertion = _terms(UNCERTAINTY, row['text']), _terms(ASSERTION, row['text'])
        candidate_uncertainty = sorted({term for i in candidates for term in target_terms[i][0]})
        candidate_assertion = sorted({term for i in candidates for term in target_terms[i][1]})
        if not candidates:
            flags.append('no_linked_successor_record')
        else:
            if uncertainty and not candidate_uncertainty:
                flags.append('uncertainty_words_not_found_in_candidates')
            if candidate_assertion and not assertion:
                flags.append('assertive_words_added_in_candidates')
        if row['kind'] in ('counter_evidence', 'exception', 'negativfaelle', 'relativierungen',
                           'ambiguity_a', 'ambiguity_b', 'spannungsfelder', 'kontrastierende_aspekte'):
            flags.append('check_counterposition_or_ambivalence_in_context')
        if len(candidates) > 1:
            flags.append('multiple_successors_require_manual_assignment')
        if any(origin_counts[i] > 1 for i in candidates):
            flags.append('multiple_origins_check_distinct_positions')
        if not flags:
            continue
        ordered = sorted(candidates, key=lambda i: after['records'][i]['key'])
        reviews.append({'source': _excerpt(row), 'flags': flags, 'matching_basis': basis,
                        'candidate_count': len(ordered), 'candidate_previews_omitted': max(0, len(ordered) - MAX_CANDIDATES),
                        'candidates': [_excerpt(after['records'][i]) for i in ordered[:MAX_CANDIDATES]],
                        'largest_shared_origin_count': max((origin_counts[i] for i in candidates), default=0),
                        'source_uncertainty_words': uncertainty, 'candidate_uncertainty_words': candidate_uncertainty,
                        'source_assertive_words': assertion, 'candidate_assertive_words': candidate_assertion})
    return reviews


def analyze_information_loss(snapshot, edges):
    """Edges are configured dependencies, not an invented linear order of modules."""
    inputs, stages = snapshot['inputs'], snapshot['stages']
    units = material_units(inputs)
    unit_for_id = {sid: key for key, ids in units.items() for sid in ids}
    initial = _view(stages.get('clusterer'), inputs)
    initial_comparison = {'status': 'not_measurable', 'reason': initial.get('reason', 'unlinked_records')}
    if initial['measurable'] and initial['segment_measurable']:
        initial_comparison = {'status': 'available',
                              'unreferenced_coding_rows': sorted(inputs.keys() - initial['ids']),
                              'unreferenced_material_units': [ids for ids in units.values() if not set(ids) & initial['ids']]}
    transitions = []
    for source, target in sorted(set(tuple(edge) for edge in edges)):
        if source == target:
            raise ValueError('Eine Diagnosestufe kann nicht ihre eigene Nachfolgestufe sein.')
        before, after = _view(stages.get(source), inputs), _view(stages.get(target), inputs)
        transition = {'source': source, 'target': target, 'edge_basis': 'configured_dependency',
                      'status': 'available' if before['measurable'] and after['measurable'] else 'not_measurable'}
        transitions.append(transition)
        if transition['status'] != 'available':
            transition['reasons'] = {name: view['reason'] for name, view in ((source, before), (target, after)) if not view['measurable']}
            continue
        transition.update(source_scopes=before['scopes'], target_scopes=after['scopes'],
                          persons_no_longer_referenced=sorted(before['people'] - after['people']),
                          persons_newly_referenced=sorted(after['people'] - before['people']))
        transition['reference_comparison'] = None
        if before['segment_measurable'] and after['segment_measurable']:
            left, right = before['ids'], after['ids']
            left_units, right_units = {unit_for_id[sid] for sid in left}, {unit_for_id[sid] for sid in right}
            before_dist, after_dist = distribution(inputs, left), distribution(inputs, right)
            before_people = {r['person']: r for r in before_dist['by_person']}
            transition['reference_comparison'] = {
                'coding_rows_no_longer_referenced': sorted(left - right),
                'coding_rows_newly_referenced': sorted(right - left),
                'coding_rows_referenced_in_both': sorted(left & right),
                'material_units_no_longer_referenced': [units[key] for key in sorted(left_units - right_units)],
                'material_units_referenced_in_both': len(left_units & right_units),
                'person_shares': [{'person': row['person'], 'material_share': row['material_share'],
                                   'before': before_people[row['person']]['evidence_share'],
                                   'after': row['evidence_share']} for row in after_dist['by_person']],
                'categories_no_longer_referenced': sorted({inputs[sid]['code'] for sid in left} -
                                                         {inputs[sid]['code'] for sid in right})}
        else:
            transition['reference_comparison_note'] = 'Segmentvergleich nicht bestimmbar: reine Personenreferenzen oder Einträge ohne Segmentverknüpfung.'
        transition['review_items'] = _review_rows(before, after, inputs, unit_for_id)
    incomplete = any(stage['status'] == 'invalid' or
                     (stage['status'] == 'unavailable' and stage.get('reason') != 'disabled') or
                     any(not row['valid'] for row in stage['records']) for stage in stages.values())
    return {'schema_version': 1, 'processing_status': 'incomplete' if incomplete else 'completed',
            'model_calls': 0, 'input_fingerprint': snapshot['input_fingerprint'],
            'material': {'coding_rows': len(inputs), 'material_units': len(units)},
            'input_to_clusters': initial_comparison,
            'methodological_note': NOTE, 'transitions': transitions,
            'limits': ['Kein semantisches Verlustmaß; keine Bewertung der Codierungsqualität.',
                       'Der Prüftext umfasst die dokumentierten Textfelder des Diagnoseadapters, keine vollständigen Zwischenprodukte.',
                       'Der Text des Originals wird hier nicht sprachlich geprüft. Die CSV ist am Originalkontext nachzulesen.',
                       'Geringe Häufigkeit bezeichnet keine inhaltliche Minderheitenposition.',
                       'Der finale HTML-Export wird erst nach den Analysen erstellt und ist kein Diagnoseeingang.',
                       f'Vorschauen: höchstens {PREVIEW_CHARS} Zeichen und {MAX_CANDIDATES} Kandidaten je Prüfpunkt; Wortlisten prüfen alle vollständigen Kandidatentexte.'],
            'source_artifacts': {mid: {key: stage[key] for key in ('status', 'artifact', 'sha256', 'reason', 'warnings') if key in stage}
                                 for mid, stage in stages.items()}}


FLAGS = {
    'no_linked_successor_record': 'Kein referenzierter Nachfolgeeintrag: Aussage und Kontext am Original prüfen.',
    'uncertainty_words_not_found_in_candidates': 'Unsicherheitswörter im Nachfolgetext nicht gefunden; andere Formulierungen können dieselbe Unsicherheit ausdrücken.',
    'assertive_words_added_in_candidates': 'Neue verallgemeinernde Wörter: auch Negation, Zitat und Gegenposition prüfen.',
    'check_counterposition_or_ambivalence_in_context': 'Gegenposition oder Ambivalenz: beide Seiten und Einschränkungen am Original prüfen.',
    'multiple_successors_require_manual_assignment': 'Mehrere Nachfolgeeinträge: gemeinsame Referenzen erlauben keine eindeutige Aussagezuordnung.',
    'multiple_origins_check_distinct_positions': 'Nachfolgeeintrag mit Referenzen mehrerer Ursprungseinträge: prüfen, ob unterschiedliche Positionen und Kontexte erkennbar bleiben.'}


def render_information_loss(result):
    lines = ['# Information-Loss-Audit', '', result['methodological_note'], '']
    if result['processing_status'] != 'completed':
        lines += ['Vorläufige Diagnose: Quelle unvollständig oder ungültig. Fehler beheben und Lauf fortsetzen.', '']
    lines += ['## Grenzen', ''] + ['- ' + markdown_escape(limit) for limit in result['limits']] + ['']
    lines += ['## Ausgangsmaterial und Clusterzuordnung', '',
              f"{result['material']['coding_rows']} Codierzeilen, {result['material']['material_units']} Materialeinheiten.", '']
    initial = result['input_to_clusters']
    if initial['status'] == 'available':
        lines += [f"{len(initial['unreferenced_material_units'])} Materialeinheiten ohne Clusterzuordnung.", '',
                  'Codierzeilen ohne Clusterzuordnung: ' + (', '.join(map(markdown_escape, initial['unreferenced_coding_rows'])) or 'keine'), '']
    else:
        lines += ['Clusterzuordnung nicht bestimmbar: ' + markdown_escape(initial['reason']), '']
    if not result['transitions']:
        lines += ['Keine analytischen Quellübergänge ausgewählt. Die gewünschten Analysen zusätzlich aktivieren. Ergebnisse aus früheren Läufen werden nicht automatisch übernommen.', '']
    scope_labels = {'direct': 'direkte Segmentbelege', 'input_association': 'Eingabezuordnung',
                    'source_group': 'Material einer Quellengruppe', 'person_reference': 'Personenreferenzen'}
    for edge in result['transitions']:
        lines += ['## ' + markdown_escape(edge['source']) + ' → ' + markdown_escape(edge['target']), '']
        source_paths = [result['source_artifacts'].get(mid, {}).get('artifact') for mid in (edge['source'], edge['target'])]
        if any(source_paths):
            lines += ['Zwischenprodukte: ' + ' → '.join(markdown_escape(path or 'nicht verfügbar') for path in source_paths), '']
        if edge['status'] != 'available':
            lines += ['Nicht bestimmbar: ' + markdown_escape(str(edge['reasons'])), '']
            continue
        lines += ['Referenzarten: ' + ', '.join(scope_labels[s] for s in edge['source_scopes']) + ' → ' +
                  ', '.join(scope_labels[s] for s in edge['target_scopes']), '',
                  'Nicht mehr referenzierte Personen: ' + (', '.join(map(markdown_escape, edge['persons_no_longer_referenced'])) or 'keine'), '']
        data = edge['reference_comparison']
        if data is None:
            lines += [edge['reference_comparison_note'], '']
        else:
            lines += [f"Materialeinheiten ohne Nachfolgereferenz: {len(data['material_units_no_longer_referenced'])}; in beiden Stufen referenziert: {data['material_units_referenced_in_both']}.", '',
                      'Codierzeilen ohne Nachfolgereferenz: ' + (', '.join(map(markdown_escape, data['coding_rows_no_longer_referenced'])) or 'keine'), '',
                      'Kategorien ohne Nachfolgereferenz: ' + (', '.join(map(markdown_escape, data['categories_no_longer_referenced'])) or 'keine'), '']
            lines += ['| Person | Materialanteil | Referenzanteil vorher | Referenzanteil nachher |', '|---|---:|---:|---:|']
            def percent(value):
                return 'nicht bestimmbar' if value is None else f'{100 * value:.1f} %'
            for person in data['person_shares']:
                lines.append('| ' + markdown_escape(person['person']) + ' | ' + ' | '.join(
                    percent(person[key]) for key in ('material_share', 'before', 'after')) + ' |')
            lines += ['', 'Personenanteile verwenden eindeutige explizite Passagen, sonst Codierzeilen. Sie beschreiben Referenzen, keine inhaltliche Bedeutung.', '']
        lines += [f"Prüfpunkte: {len(edge['review_items'])}. Dies ist keine Fehlerquote.", '']
        for review in edge['review_items']:
            source = review['source']
            lines += ['### Prüfpunkt ' + markdown_escape(source['record_key']), '']
            lines += ['- ' + FLAGS[flag] for flag in review['flags']] + ['']
            for label, row in [('Vorher', source)] + [('Möglicher Nachfolgeeintrag', r) for r in review['candidates']]:
                lines += [label + ': ' + markdown_escape(row['record_key']), '',
                          'Referenzen: ' + markdown_escape(', '.join(row['segment_ids'] + row['persons']) or 'keine'), '',
                          markdown_escape(row['text_preview']) or '(kein projizierter Prüftext)', '']
                if row['preview_truncated']:
                    lines += [f"Vorschau gekürzt; vollständiger Prüftext umfasst {row['text_characters']} Zeichen. Originalartefakt am angegebenen Eintrag öffnen.", '']
            if review['candidate_previews_omitted']:
                lines += [f"Weitere {review['candidate_previews_omitted']} Kandidaten im Originalartefakt prüfen; Vorschau begrenzt.", '']
    return '\n'.join(lines)
