"""Pure, person-scoped topic adapters; no inference from selected quote counts.

File/run provenance is the caller's responsibility. These adapters validate the
complete original person/segment scope, then define a full assignment matrix.
"""
from copy import deepcopy

from runtime_support import fingerprint
from thematic_adapters import _completed, _ids, _nonempty, _require
from thematic_counts import _material as validate_material, _topics as validate_topics

PERSON_SECTIONS = ('zentrale_themen', 'perspektiven', 'spannungsfelder', 'kontrastierende_aspekte')


def _unweighted(payload):
    _completed(payload)
    return {key: value for key, value in payload.items() if key != 'analysis_perspective'}


def _person_material(material):
    validate_material(material)
    _require(material['person_basis'] == 'confirmed', 'Personenzuordnung zuerst prüfen und bestätigen.')
    index = material.get('segment_index')
    expected = {}; scopes = {}; texts = {}
    for uid, unit in material['units'].items():
        scopes.setdefault(unit['person'], []).append(uid)
        for sid in unit['segment_ids']:
            expected.setdefault(unit['person'], set()).add(sid)
            texts[sid] = unit['text']
    _require(isinstance(index, dict) and set(index) == set(texts), 'Originalsegment-Verzeichnis ist unvollständig.')
    for sid, row in index.items():
        _require(isinstance(row, dict) and isinstance(row.get('unit_id'), str) and row['unit_id'] in material['units'])
        unit = material['units'][row['unit_id']]
        _require(sid in unit['segment_ids'] and row.get('code_path') in unit['code_paths'],
                 'Originalsegment-Verzeichnis passt nicht zur Materialeinheit.')
    return expected, {person: sorted(ids) for person, ids in scopes.items()}, texts


def _persons(payload, expected):
    _completed(payload)
    persons = payload.get('persons')
    _require(isinstance(persons, dict) and set(persons) == set(expected),
             'Analysequelle muss genau die bestätigten Personen enthalten.')
    for person, row in persons.items():
        _require(isinstance(row, dict) and row.get('person') == person,
                 'Personenschlüssel und gespeicherte Personenkennung stimmen nicht überein.')
    if 'person_count' in payload:
        _number(payload['person_count'], len(expected))
    return persons


def _number(value, expected):
    _require(type(value) is int and value == expected, 'Gespeicherte Anzahl stimmt nicht mit dem Originalumfang überein.')


def _evidence(ids, allowed):
    values = _ids(ids)
    _require(set(values) <= allowed, 'Befund enthält unbekannte oder einer anderen Person zugehörige Belege.')
    return values


def _quotes(values, expected, texts, field):
    _require(isinstance(values, list) and len(values) == len(expected), 'Originalzitate müssen genau den ausgewählten Beleg-IDs entsprechen.')
    seen = set()
    for row in values:
        _require(isinstance(row, dict) and isinstance(row.get('segment_id'), str))
        sid = row['segment_id']
        _require(sid in expected and sid not in seen, 'Unbekannte oder doppelte Zitatkennung.')
        _require(row.get(field) == texts[sid], 'Gespeichertes Zitat stimmt nicht mit dem vollständigen Originaltext überein.')
        seen.add(sid)


def _envelope(module, material, payload, topics, links, context, *, source=None):
    result = {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
        'source_fingerprint': fingerprint(payload) if source is None else fingerprint({'person_analysis': source, 'ambiguity_analysis': payload}),
        'assignment_origin': 'requires_full_thematic_assignment',
        'topics': validate_topics(material, topics), 'assignments': None,
        'source_links': dict(sorted(links.items())), 'qualitative_source': deepcopy(payload),
        'unassigned_context': context, 'model_calls': 0,
        'methodological_note': 'Alle Originaleinheiten der jeweiligen Einzelperson werden gegen die festen analytisch abgeleiteten Themen geprüft. '
            'Ausgewählte Belege sind keine vollständige Themenzuordnung. Der Personennenner ist höchstens eins; '
            'Passagen- und Codierzeilenbreite innerhalb dieses Falls ist keine Bevölkerungsprävalenz.'}
    if module == 'ambiguity_analysis':
        result['source_person_fingerprint'] = fingerprint(source)
        result['methodological_note'] += (' A und B sind unabhängige Seitenthemen: Unterstützung für B bedeutet nicht automatisch Gegenposition zu A. '
            'Getrennte Kandidatenblöcke können blockübergreifende Ambivalenzen übersehen; eine vollständige Zuordnung entdeckt keine fehlenden Kandidaten nachträglich.')
    return result


def build_person_topics(material, payload):
    """Derived findings scoped to one complete confirmed person, not quote IDs."""
    payload = _unweighted(payload)
    expected, scopes, texts = _person_material(material)
    persons = _persons(payload, expected)
    topics = []; links = {}; context = {}
    for person in sorted(persons):
        row = persons[person]
        _require(set(_ids(row.get('segment_ids'))) == expected[person], 'Gesamte Originalsegment-Liste der Personenanalyse stimmt nicht überein.')
        _require(isinstance(row.get('gesamtverdichtung'), str))
        context[person] = {'gesamtverdichtung': row['gesamtverdichtung']}
        used = set()
        for section in PERSON_SECTIONS:
            findings = row.get(section)
            _require(isinstance(findings, list), 'Personenanalyse benötigt alle vier Befundabschnitte als Listen.')
            for finding in findings:
                _require(isinstance(finding, dict))
                evidence = _evidence(finding.get('segment_ids'), expected[person]); used.update(evidence)
                if section == 'zentrale_themen':
                    _require(_nonempty(finding.get('thema')) and isinstance(finding.get('verdichtung'), str))
                    label = finding['thema']
                    text = label + '\nVerdichtung: ' + finding['verdichtung']
                else:
                    field = 'aussage' if section == 'perspektiven' else 'beschreibung'
                    _require(_nonempty(finding.get(field)))
                    label = text = finding[field]
                tid = 'person_' + fingerprint({'person': person, 'section': section, 'definition': text})[:24]
                _require(tid not in links, 'Doppelter identischer Personenbefund: vor der Themenzuordnung eindeutig machen.')
                topics.append({'topic_id': tid, 'label': person + ' · ' + label,
                    'definition': 'Einzelperson: ' + person + '\nBefundabschnitt: ' + section + '\n' + text,
                    'inclusion': 'Originalmaterial dieser Person, das den konkreten analytischen Befund stützt. Ausdrücklich entgegenstehende Positionen getrennt erfassen.',
                    'exclusion': 'Bloße Zugehörigkeit zur Person oder Erwähnung des Oberthemas genügt nicht. Fehlende Belege sind keine Ablehnung. Andere Personen gehören nicht zum Bezugsraum.',
                    'kind': 'derived', 'scope_unit_ids': scopes[person]})
                links[tid] = {'module_id': 'person_analysis', 'person': person, 'section': section,
                    'qualitative_text': text, 'selected_evidence_segment_ids': evidence,
                    'counting_basis': 'full_assignment_required',
                    'counting_note': 'Materialbreite innerhalb einer Einzelperson; kein Vergleich zusammengezählter gleichnamiger Themen verschiedener Personen.'}
        _quotes(row.get('belege'), used, texts, 'zitat')
    return _envelope('person_analysis', material, payload, topics, links,
                     {'persons': context, 'counting_note': 'Freie Gesamtverdichtungen erhalten keine eigenen Themenhäufigkeiten.'})


def build_ambiguity_topics(material, payload, source_person_payload):
    """Two independent themes per pair; B never seeds opposition to A."""
    payload = _unweighted(payload)
    source_person_payload = _unweighted(source_person_payload)
    # Validate the complete unweighted upstream source, not only referenced people.
    build_person_topics(material, source_person_payload)
    expected, scopes, texts = _person_material(material)
    persons = _persons(payload, expected)
    _require('source_person_analysis_created_at' in payload and
             payload['source_person_analysis_created_at'] == source_person_payload.get('created_at'),
             'Ambivalenzanalyse verweist nicht auf die übergebene Personenanalyse.')
    topics = []; links = {}; context = {}; pairs = set(); source_ids = set(); finding_count = 0
    for person in sorted(persons):
        row = persons[person]
        _number(row.get('segment_count'), len(expected[person]))
        reduction = row.get('input_reduction')
        _require(isinstance(reduction, dict) and set(_ids(reduction.get('segment_ids'))) == expected[person],
                 'Ambivalenz-Eingabe muss alle Originalsegmente derselben Person enthalten.')
        if 'parts' in reduction:
            _require(type(reduction['parts']) is int and reduction['parts'] >= 1)
        _require(isinstance(row.get('gesamteinordnung'), str))
        context[person] = {'gesamteinordnung': row['gesamteinordnung'], 'input_reduction': deepcopy(reduction)}
        findings = row.get('ambivalenzen')
        _require(isinstance(findings, list))
        for finding in findings:
            _require(isinstance(finding, dict) and all(_nonempty(finding.get(key)) for key in ('ambiguity_id', 'thema', 'position_a', 'position_b')))
            _require(isinstance(finding.get('beschreibung'), str))
            original_id = finding['ambiguity_id']
            _require(original_id not in source_ids, 'Doppelte Ambivalenzkennung im Quellresultat.')
            source_ids.add(original_id); finding_count += 1
            evidence = {}
            for side in ('a', 'b'):
                evidence[side] = _evidence(finding.get('segment_ids_' + side), expected[person])
                _quotes(finding.get('belege_' + side), evidence[side], texts, 'text')
            _require(evidence['a'] != evidence['b'], 'Identische A-/B-Belegmengen sind keine gültigen Kandidaten des bestehenden Ambivalenzmoduls.')
            identity = {'person': person, **{key: finding[key] for key in ('thema', 'beschreibung', 'position_a', 'position_b')}}
            pair_id = 'ambiguity_' + fingerprint(identity)[:24]
            _require(pair_id not in pairs, 'Doppeltes identisches Ambivalenzpaar: vor der Themenzuordnung eindeutig machen.')
            pairs.add(pair_id)
            pair_context = ('Einzelperson: ' + person + '\nThema: ' + finding['thema'] + '\nPaarkontext: ' + finding['beschreibung'] +
                            '\nPosition A: ' + finding['position_a'] + '\nPosition B: ' + finding['position_b'])
            for side in ('A', 'B'):
                position = finding['position_' + side.lower()]
                tid = pair_id + '_' + side
                definition = pair_context + '\nZu prüfende Seite ' + side + ': ' + position
                topics.append({'topic_id': tid, 'label': person + ' · ' + finding['thema'] + ' · Seite ' + side + ': ' + position,
                    'definition': definition,
                    'inclusion': 'Prüfe Originalmaterial dieser Person unabhängig auf Stützung oder ausdrückliche Gegenposition zu genau dieser Seite. Dieselbe Passage darf beide Seitenthemen stützen.',
                    'exclusion': 'Die andere Seite ist nicht automatisch die logische Negation dieser Seite. Keine Umdeutung ihrer Belege als Gegenposition, keine Subtraktion von Seitenzahlen; bloße Themennennung genügt nicht.',
                    'kind': 'derived', 'scope_unit_ids': scopes[person]})
                links[tid] = {'module_id': 'ambiguity_analysis', 'person': person, 'section': 'ambivalenzen',
                    'pair_id': pair_id, 'side': side, 'source_ambiguity_id': original_id,
                    'qualitative_text': definition, 'selected_evidence_segment_ids': evidence[side.lower()],
                    'counting_basis': 'full_assignment_required',
                    'counting_note': 'Unabhängige Seite eines intrapersonellen Paars; Überschneidungen sind möglich, Personenanteile haben maximal den Nenner eins.'}
    if 'ambiguity_count' in payload:
        _number(payload['ambiguity_count'], finding_count)
    if 'persons_with_ambiguities' in payload:
        _number(payload['persons_with_ambiguities'], sum(bool(row['ambivalenzen']) for row in persons.values()))
    return _envelope('ambiguity_analysis', material, payload, topics, links,
        {'persons': context, 'counting_note': 'Freie Gesamteinordnung und Kandidatenblock-Grenzen bleiben Kontext ohne eigene Themenhäufigkeit.'}, source=source_person_payload)
