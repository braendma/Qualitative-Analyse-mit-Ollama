"""Pure mixed-scope contrast topics, with explicit unresolved candidate context."""
from copy import deepcopy

from runtime_support import fingerprint
from thematic_adapters import _require, _nonempty
from thematic_comparison_adapter import build_person_comparison_topics, _rows, _people, _strings
from thematic_counts import _topics as validate_topics
from thematic_person_adapters import _unweighted


def _compact_receipt(receipt, value):
    _require(isinstance(receipt, dict) and type(receipt.get('used')) is bool)
    _require(receipt.get('source_sha256') == fingerprint(value), 'Kontrastverdichtung passt nicht zur vollständigen Originalvorstufe.')
    if receipt['used']:
        _require(_nonempty(receipt.get('summary')), 'Verdichtungsnachweis benötigt den gespeicherten Summarytext.')
    else:
        _require(set(receipt) == {'used', 'source_sha256'})
    if 'note' in receipt:
        _require(isinstance(receipt['note'], str))


def _reduction(receipt, source, comparison):
    _require(isinstance(receipt, dict) and type(receipt.get('used')) is bool)
    if not receipt['used']:
        _require(set(receipt) == {'used'}, 'Ungekürzte Kontrastbasis enthält widersprüchliche Verdichtungsangaben.')
        return
    _require(set(receipt) == {'used', 'parts', 'persons', 'comparison', 'note'})
    _require(type(receipt['parts']) is int and receipt['parts'] > 0)
    _require(isinstance(receipt['note'], str))
    persons = source['persons']
    _require(isinstance(receipt['persons'], dict) and set(receipt['persons']) == set(persons),
             'Kontrastverdichtung muss alle bestätigten Personen enthalten.')
    projected = {key: value for key, value in comparison.items() if key not in
                 ('input_reduction', 'created_at', 'source_person_analysis_created_at')}
    _compact_receipt(receipt['comparison'], projected)
    _require(set(receipt['comparison']) <= {'used', 'source_sha256', 'summary', 'note'})
    prior = comparison['input_reduction'].get('sources', {})
    for person, row in receipt['persons'].items():
        _compact_receipt(row, persons[person])
        _require(set(row) <= {'used', 'source_sha256', 'summary', 'note', 'reused_comparison_summary'})
        if 'reused_comparison_summary' in row:
            _require(row['reused_comparison_summary'] is True and row['used'] is True)
            saved = prior.get(person)
            _require(isinstance(saved, dict) and saved.get('source_person') == person and
                     saved.get('source_sha256') == fingerprint(persons[person]) and
                     saved.get('summary') == row['summary'], 'Wiederverwendete Personenverdichtung stimmt nicht mit der geprüften Vergleichsvorstufe überein.')


def build_contrast_topics(material, payload, source_person_payload, source_comparison_payload):
    """Prepare full global patterns and independent, fully scoped countercases.

    File/run provenance is caller-owned. Free-text reference resolution is exact;
    unresolved text stays context, whereas structural/source errors fail closed.
    """
    original = _unweighted(payload)
    source = _unweighted(source_person_payload)
    comparison = _unweighted(source_comparison_payload)
    build_person_comparison_topics(material, comparison, source)
    for field, upstream in (('source_person_analysis_created_at', source),
                            ('source_person_comparison_created_at', comparison)):
        _require(field in original and original[field] == upstream.get('created_at'), 'Kontrastanalyse verweist nicht auf die übergebenen Originalvorstufen.')
    _reduction(original.get('input_reduction'), source, comparison)
    people = set(source['persons'])
    patterns = _rows(original, 'dominante_muster', ('muster', 'beschreibung', 'getragen_von'))
    cases = _rows(original, 'negativfaelle', ('person', 'bezugs_muster', 'abweichung', 'begruendung'))
    tensions = _rows(original, 'spannungen_zwischen_typen', ('typen', 'beschreibung'))
    qualifiers = _rows(original, 'relativierungen', ('aussage', 'bedeutung'))
    _require(isinstance(original.get('gesamteinordnung'), str))
    registry = {}
    for row in comparison['typen']:
        registry.setdefault(row['typ_name'], set()).add(fingerprint({k: v for k, v in row.items() if k != 'personen'}))
    context = {'records': [], 'spannungen_zwischen_typen': deepcopy(tensions),
        'relativierungen': deepcopy(qualifiers), 'gesamteinordnung': original['gesamteinordnung'],
        'input_reduction': deepcopy(original['input_reduction'])}

    def leave(section, index, row, reason):
        context['records'].append({'section': section, 'source_record_index': index, 'record': deepcopy(row), 'reason': reason})

    for index, row in enumerate(tensions):
        names = _strings(row['typen'])
        _require(set(names) <= set(registry), 'Typenspannung enthält eine unbekannte Typreferenz.')
        _require(isinstance(row['beschreibung'], str))
        reason = 'ambiguous_type_reference' if any(len(registry[name]) > 1 for name in names) else 'uncounted_type_context'
        leave('spannungen_zwischen_typen', index, row, reason)
    for index, row in enumerate(qualifiers):
        _require(all(isinstance(row[key], str) for key in ('aussage', 'bedeutung')))
        leave('relativierungen', index, row, 'uncounted_qualifier_context')

    topics = []; links = {}; titles = {}; grouped = {}
    scope = sorted(material['units'])
    for index, row in enumerate(patterns):
        _people(row['getragen_von'], people)
        _require(all(isinstance(row[key], str) for key in ('muster', 'beschreibung')))
        if not (_nonempty(row['muster']) and _nonempty(row['beschreibung'])):
            leave('dominante_muster', index, row, 'incomplete_candidate')
            continue
        key = (row['muster'], row['beschreibung'])
        grouped.setdefault(key, []).append((index, row))
    for (label, description), rows in sorted(grouped.items()):
        definition = label + '\nMusterbeschreibung: ' + description
        tid = 'contrast_pattern_' + fingerprint({'definition': definition, 'scope_persons': sorted(people)})[:24]
        topics.append({'topic_id': tid, 'label': label, 'definition': definition,
            'inclusion': 'Prüfe jede Originaleinheit aller bestätigten Personen unabhängig auf Stützung oder ausdrückliche Gegenposition zu dieser festen Musterbeschreibung.',
            'exclusion': 'Die Bezeichnung dominant ist eine Kandidateninterpretation, keine feststehende Mehrheit. Bloße Themennennung oder getragen_von-Referenzen sind keine vollständige Zuordnung. Fehlende Belege sind keine Ablehnung.',
            'kind': 'derived', 'scope_unit_ids': scope})
        links[tid] = {'module_id': 'contrast_analysis', 'section': 'dominante_muster', 'scope_kind': 'global_pattern',
            'qualitative_text': definition, 'source_record_indices': [index for index, _ in rows],
            'source_records': [deepcopy(row) for _, row in rows], 'selected_evidence_segment_ids': [],
            'countercase_topic_ids': [], 'counting_basis': 'full_assignment_required'}
        titles.setdefault(label, []).append(tid)

    case_groups = {}
    for index, row in enumerate(cases):
        _people([row['person']], people)
        _require(all(isinstance(row[key], str) for key in ('bezugs_muster', 'abweichung', 'begruendung')))
        if not (_nonempty(row['bezugs_muster']) and _nonempty(row['abweichung'])):
            leave('negativfaelle', index, row, 'incomplete_candidate')
            continue
        matches = titles.get(row['bezugs_muster'], [])
        if len(matches) != 1:
            leave('negativfaelle', index, row, 'ambiguous_pattern_reference' if matches else 'unresolved_pattern_reference')
            continue
        key = (row['person'], matches[0], row['abweichung'], row['begruendung'])
        case_groups.setdefault(key, []).append((index, row))
    for (person, pattern_id, deviation, reason), rows in sorted(case_groups.items()):
        definition = ('Einzelperson: ' + person + '\nVollständiges Bezugsmuster: ' + links[pattern_id]['qualitative_text'] +
                      '\nAbweichung: ' + deviation + '\nBegründung: ' + reason)
        tid = 'contrast_case_' + fingerprint({'person': person, 'pattern_topic_id': pattern_id,
                                             'deviation': deviation, 'reason': reason})[:24]
        topics.append({'topic_id': tid, 'label': person + ' · Gegenfall: ' + rows[0][1]['bezugs_muster'], 'definition': definition,
            'inclusion': 'Prüfe alle Originaleinheiten genau dieser Person auf Stützung oder ausdrückliche Gegenposition zu der beschriebenen Abweichung vom vollständigen Bezugsmuster.',
            'exclusion': 'Dieser Einzelfall hat höchstens eine Person als Nenner. Stützung der Abweichung setzt nicht automatisch opposed im globalen Muster. both bedeutet Stützung und Ablehnung dieser Abweichung, nicht beide Themen gemeinsam.',
            'kind': 'derived', 'scope_unit_ids': sorted(uid for uid, unit in material['units'].items() if unit['person'] == person)})
        links[tid] = {'module_id': 'contrast_analysis', 'section': 'negativfaelle', 'scope_kind': 'individual_countercase',
            'person': person, 'pattern_topic_id': pattern_id, 'qualitative_text': definition,
            'source_record_indices': [index for index, _ in rows], 'source_records': [deepcopy(row) for _, row in rows],
            'selected_evidence_segment_ids': [], 'counting_basis': 'full_assignment_required'}
        links[pattern_id]['countercase_topic_ids'].append(tid)
    for row in links.values():
        if 'countercase_topic_ids' in row:
            row['countercase_topic_ids'].sort()
    context['counting_note'] = ('Nur vollständig definierte globale Muster und eindeutig gebundene Gegenfälle werden thematisch gezählt. '
        'Unvollständige oder unaufgelöste Kandidaten, Typenspannungen, Relativierungen und Gesamteinordnung bleiben sichtbar als ungezählter Kontext; fehlende Zuordnung ist keine Nullhäufigkeit.')
    return {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
        'source_fingerprint': fingerprint({'person_analysis': source, 'person_comparison': comparison, 'contrast_analysis': original}),
        'source_person_fingerprint': fingerprint(source), 'source_comparison_fingerprint': fingerprint(comparison),
        'assignment_origin': 'requires_full_thematic_assignment', 'topics': validate_topics(material, topics), 'assignments': None,
        'source_links': dict(sorted(links.items())), 'qualitative_source': deepcopy(original), 'unassigned_context': context, 'model_calls': 0,
        'methodological_note': 'Globale Muster werden im gesamten bestätigten Korpus geprüft; Gegenfälle unabhängig im vollständigen Material genau ihrer Person. '
            'Die Nenner sind verschieden und werden nicht zusammengerechnet. Seltene Gegenfälle bleiben sichtbar. '
            'Exakte doppelte Definitionen werden einmal geprüft, ihre ursprünglichen Referenzen bleiben Herkunft und sind keine Zählergebnisse. '
            'Getrennte Kandidatenblöcke können globale Vergleiche übersehen; die neue Matrix entdeckt keine fehlenden Kandidaten nachträglich.'}
