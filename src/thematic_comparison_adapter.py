"""Pure common-theme adapter; person references are not complete membership."""
from copy import deepcopy

from runtime_support import fingerprint
from thematic_adapters import _require, _nonempty
from thematic_counts import _topics as validate_topics
from thematic_person_adapters import _unweighted, build_person_topics


def _strings(values):
    _require(isinstance(values, list) and all(_nonempty(v) for v in values))
    _require(len(values) == len(set(values)), 'Doppelte Referenz im Personenvergleich.')
    return sorted(values)


def _people(values, allowed):
    result = _strings(values)
    _require(set(result) <= allowed, 'Personenvergleich enthält eine unbekannte Personenreferenz.')
    return result


def _rows(payload, section, fields):
    values = payload.get(section)
    _require(isinstance(values, list), 'Personenvergleich benötigt alle Befundabschnitte als Listen.')
    for row in values:
        _require(isinstance(row, dict) and set(row) == set(fields), 'Befundschema im Personenvergleich ist unvollständig oder unbekannt.')
    return values


def _reduction(receipt, persons):
    _require(isinstance(receipt, dict) and type(receipt.get('used')) is bool,
             'Personenvergleich benötigt den ursprünglichen Verdichtungsnachweis.')
    _require(receipt.get('source_sha256') == fingerprint(persons),
             'Verdichtungsnachweis verweist nicht auf die vollständige Original-Personenanalyse.')
    if not receipt['used']:
        _require(set(receipt) == {'used', 'source_sha256'}, 'Ungekürzte Vergleichsbasis enthält widersprüchliche Verdichtungsangaben.')
        return
    _require(receipt.get('method') == 'per_person_hierarchical_reduction')
    _require(receipt.get('budget_method') == 'shared_final_prompt_with_soft_person_targets')
    _require(all(type(receipt.get(key)) is int and receipt[key] > 0 for key in ('target_bytes_per_person', 'context')))
    _require(isinstance(receipt.get('note'), str))
    sources = receipt.get('sources'); sizes = receipt.get('actual_bytes_per_person')
    _require(isinstance(sources, dict) and set(sources) == set(persons), 'Verdichtungsnachweis muss jede Originalperson genau einmal enthalten.')
    _require(isinstance(sizes, dict) and set(sizes) == set(persons))
    for person, source in sources.items():
        _require(isinstance(source, dict) and set(source) == {'source_sha256', 'source_person', 'summary'})
        _require(source['source_person'] == person and source['source_sha256'] == fingerprint(persons[person]),
                 'Einzelpersonen-Verdichtung passt nicht zur Originalquelle.')
        _require(_nonempty(source['summary']))
        _require(type(sizes[person]) is int and sizes[person] == len(source['summary'].encode('utf-8')),
                 'Gespeicherter Umfang der Personenverdichtung stimmt nicht.')


def build_person_comparison_topics(material, payload, source_person_payload):
    """Count fixed common findings over all confirmed people, never type lists.

    File/run hashes remain the caller's responsibility. This validates the full
    person source and saved reduction receipts independently of selected refs.
    """
    original = _unweighted(payload)
    source = _unweighted(source_person_payload)
    build_person_topics(material, source)
    persons = source['persons']; allowed = set(persons)
    _require(_people(original.get('source_persons'), allowed) == sorted(persons),
             'Vergleich muss genau alle bestätigten Personen enthalten.')
    _require('source_person_analysis_created_at' in original and
             original['source_person_analysis_created_at'] == source.get('created_at'))
    _reduction(original.get('input_reduction'), persons)
    _require(isinstance(original.get('gesamtvergleich'), str))

    common = _rows(original, 'gemeinsame_muster', ('thema', 'verdichtung', 'personen'))
    differences = _rows(original, 'zentrale_unterschiede', ('thema', 'beschreibung', 'personenpositionen'))
    types = _rows(original, 'typen', ('typ_name', 'beschreibung', 'personen', 'merkmale'))
    unassigned = _rows(original, 'nicht_zugeordnete_personen', ('person', 'begruendung'))
    for row in differences:
        _require(all(isinstance(row[key], str) for key in ('thema', 'beschreibung')))
        positions = _rows(row, 'personenpositionen', ('person', 'position'))
        _people([entry['person'] for entry in positions], allowed)
        _require(all(isinstance(entry['position'], str) for entry in positions))
    for row in types:
        _require(all(isinstance(row[key], str) for key in ('typ_name', 'beschreibung')))
        _people(row['personen'], allowed)
        _require(isinstance(row['merkmale'], list) and all(_nonempty(v) for v in row['merkmale']))
    _people([row['person'] for row in unassigned], allowed)
    _require(all(isinstance(row['begruendung'], str) for row in unassigned))

    scope = sorted(material['units']); topics = []; links = {}
    for row in common:
        _require(_nonempty(row['thema']) and _nonempty(row['verdichtung']), 'Gemeinsames Muster benötigt Thema und vollständige Definition.')
        references = _people(row['personen'], allowed)
        text = row['thema'] + '\nVerdichtung: ' + row['verdichtung']
        tid = 'person_comparison_' + fingerprint({'section': 'gemeinsame_muster',
            'definition': text, 'scope_persons': sorted(persons)})[:24]
        _require(tid not in links, 'Doppeltes identisches gemeinsames Muster: vor der Themenzuordnung eindeutig machen.')
        topics.append({'topic_id': tid, 'label': row['thema'], 'definition': text,
            'inclusion': 'Prüfe jede Originaleinheit aller bestätigten Vergleichspersonen auf Stützung oder ausdrückliche Gegenposition zu dieser festen analytischen Aussage.',
            'exclusion': 'Bloße Themennennung oder eine Personenreferenz im ursprünglichen Vergleich genügt nicht. Die Formulierung als gemeinsames Muster beweist keine Mehrheit. Fehlende Belege sind keine Ablehnung.',
            'kind': 'derived', 'scope_unit_ids': scope})
        links[tid] = {'module_id': 'person_comparison', 'section': 'gemeinsame_muster',
            'qualitative_text': text, 'source_persons': references, 'selected_evidence_segment_ids': [],
            'counting_basis': 'full_assignment_required',
            'counting_note': 'Personenreferenzen sind Kandidatenherkunft, keine vollständige Zuordnung; alle bestätigten Vergleichspersonen gehören zum Nenner.'}
    context = {section: deepcopy(original[section]) for section in
               ('zentrale_unterschiede', 'typen', 'nicht_zugeordnete_personen', 'gesamtvergleich', 'input_reduction')}
    context['counting_note'] = ('Nur gemeinsame Muster werden vollständig thematisch zugeordnet. Unterschiede, Typen, nicht zugeordnete Personen und Gesamtvergleich bleiben ungezählter analytischer Kontext. '
        'Typenlisten können sich überschneiden oder unvollständig sein; sie bilden keine bestätigte Partition und keine Themenhäufigkeiten.')
    return {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
        'source_fingerprint': fingerprint({'person_analysis': source, 'person_comparison': original}),
        'source_person_fingerprint': fingerprint(source),
        'assignment_origin': 'requires_full_thematic_assignment',
        'topics': validate_topics(material, topics), 'assignments': None,
        'source_links': dict(sorted(links.items())), 'qualitative_source': deepcopy(original),
        'unassigned_context': context, 'model_calls': 0,
        'methodological_note': 'Gemeinsame Muster sind feste analytisch abgeleitete Aussagen und werden über alle Originaleinheiten aller bestätigten Personen geprüft. '
            'Ausgewählte Personenreferenzen sind keine vollständige Zuordnung; wiederholte Aussagen einer Person werden nicht zu mehreren Personen. '
            'Getrennte Verdichtungen können Kandidaten übersehen; die vollständige Matrix prüft vorhandene Muster, entdeckt aber keine fehlenden Muster nachträglich. '
            'Unterschiede und Typen bleiben ausdrücklich ohne eigene Häufigkeitszählung.'}
