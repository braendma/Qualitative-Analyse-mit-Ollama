"""Deterministic codebook review hints from existing, validated coding outputs."""
from collections import Counter, defaultdict
from itertools import combinations
import unicodedata

from coding_agreement_core import _index_exact, _rows, calculate_agreement
from coding_validation_common import UNKNOWN_CODES
from coverage_core import markdown_escape
from multi_label_core import group_units, validate_prediction
from runtime_support import fingerprint
from diagnostic_sources import make_snapshot

PROCESSING = {'completed', 'failed', 'invalid_input'}
VERIFICATIONS = {'bestätigt', 'teilweise_passend', 'nicht_passend', 'unklar'}
PAIR_EVENT_LIMIT = 100000


def _normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def _processing(row):
    state = row.get('processing_status', 'completed')
    if state not in PROCESSING:
        raise ValueError('Codebook-Diagnose: unbekannter Verarbeitungsstatus.')
    return state


def _verification(segments, payload, codes):
    if payload is None:
        return None
    indexed = _index_exact(_rows(payload, 'Verify-Output'), {s.segment_id for s in segments}, 'Verify-Output')
    for segment in segments:
        row = indexed[segment.segment_id]
        if row.get('human_code') != segment.human_code or row.get('verification') not in VERIFICATIONS:
            raise ValueError('Codebook-Diagnose: Verifikation passt nicht zur ursprünglichen Codierung.')
        _processing(row)
        alternatives = row.get('alternative_codes', [])
        if not isinstance(alternatives, list) or any(not isinstance(c, str) or c not in codes for c in alternatives):
            raise ValueError('Codebook-Diagnose: ungültige Alternativcodes.')
    return indexed


def _blind(groups, payload, codes, multi):
    if payload is None:
        return None
    if not multi:
        indexed = _index_exact(_rows(payload, 'Blind-Output'), {s.segment_id for g in groups.values() for s in g}, 'Blind-Output')
        result = {}
        for uid, members in groups.items():
            row = indexed[members[0].segment_id]
            prediction = row.get('predicted_code')
            if not isinstance(prediction, str) or prediction not in codes | UNKNOWN_CODES:
                raise ValueError('Codebook-Diagnose: unbekannte Blindcodierung.')
            state = 'assigned' if prediction in codes else 'none' if prediction == 'keine_zuordnung' else 'abstained'
            result[uid] = {'predicted_codes': [prediction] if state == 'assigned' else [],
                           'assignment_status': state, 'processing_status': _processing(row)}
        return result
    if payload.get('label_mode') != 'multi_label' or not isinstance(payload.get('unit_results'), list):
        raise ValueError('Codebook-Diagnose: unabhängige Multi-Label-Vorhersagen fehlen.')
    result = {}
    for row in payload['unit_results']:
        uid = row.get('unit_id') if isinstance(row, dict) else None
        if not isinstance(uid, str) or uid not in groups or uid in result:
            raise ValueError('Codebook-Diagnose: unbekannte oder doppelte Blind-Passage.')
        ids = row.get('segment_ids')
        if not isinstance(ids, list) or any(not isinstance(s, str) for s in ids) or len(set(ids)) != len(ids) or set(ids) != {s.segment_id for s in groups[uid]}:
            raise ValueError('Codebook-Diagnose: abweichende Zeilenzuordnung der Blind-Passage.')
        validate_prediction(row, uid, codes)
        _processing(row)
        result[uid] = row
    if result.keys() != groups.keys():
        raise ValueError('Codebook-Diagnose: unvollständige Blind-Passagen.')
    # Older row copies are used by the review queue. They must agree with unit_results.
    expanded = _index_exact(_rows(payload, 'Blind-Output'), {s.segment_id for g in groups.values() for s in g}, 'Blind-Output')
    for uid, members in groups.items():
        for member in members:
            row = expanded[member.segment_id]
            for field in ('unit_id', 'predicted_codes', 'assignment_status', 'processing_status'):
                if row.get(field) != result[uid].get(field):
                    raise ValueError('Codebook-Diagnose: Zeilenkopie widerspricht unabhängiger Blind-Passage.')
    return result


def _text_groups(codebook, field):
    groups = defaultdict(list)
    for entry in codebook:
        value = _normalized(getattr(entry, field))
        if value:
            groups[value].append(entry.code)
    return [{'codes': sorted(codes), 'normalized_text_fingerprint': fingerprint(text)}
            for text, codes in groups.items() if len(codes) > 1]


def analyze_codebook(segments, codebook, *, verification=None, blind=None, agreement=None, review=None, settings=None):
    settings = settings or {}
    mode = settings.get('label_mode', 'unspecified')
    if any(payload is not None and not isinstance(payload, dict) for payload in (verification, blind, agreement, review)):
        raise ValueError('Codebook-Diagnose: Quellen müssen JSON-Objekte sein.')
    if mode not in {'unspecified', 'single_label', 'multi_label'}:
        raise ValueError('Codebook-Diagnose: ungültiger label_mode.')
    multi = mode == 'multi_label'
    codes = {entry.code for entry in codebook}
    if len(codes) != len(codebook) or len({s.segment_id for s in segments}) != len(segments):
        raise ValueError('Codebook-Diagnose: doppelte Codes oder Segment-IDs.')
    if any(s.human_code not in codes for s in segments):
        raise ValueError('Codebook-Diagnose: menschlicher Code fehlt im Codebuch.')
    if codes & UNKNOWN_CODES:
        raise ValueError('Codebook-Diagnose: Codepfad kollidiert mit reserviertem Zuordnungsstatus; vollständigen eindeutigen Codepfad verwenden.')
    groups = group_units(segments) if multi else {s.segment_id: [s] for s in segments}
    verify = _verification(segments, verification, codes)
    predictions = _blind(groups, blind, codes, multi)
    expected_agreement = None
    if agreement is not None or review is not None:
        if verification is None or blind is None:
            raise ValueError('Codebook-Diagnose: Agreement/Prüfliste benötigt verifizierbare Codierquellen.')
        _, expected_agreement = calculate_agreement(segments, codebook, verification, blind, settings=settings)
    if agreement is not None:
        for field in ('cases', 'case_counts', 'label_mode', 'confusion_matrix', 'confusion_pairs',
                      'coverage', 'n_segments', 'n_units', 'exact_agreement', 'set_metrics', 'level_agreement'):
            if agreement.get(field) != expected_agreement.get(field):
                raise ValueError('Codebook-Diagnose: gespeichertes Agreement widerspricht den Codierquellen.')
    review_by_id = {}
    if review is not None:
        if review.get('codebook') != [c.as_prompt_dict() for c in codebook]:
            raise ValueError('Codebook-Diagnose: Prüfliste gehört zu einem anderen Codebuch.')
        cases = review.get('cases')
        if not isinstance(cases, list):
            raise ValueError('Codebook-Diagnose: Prüfliste ohne Fälle.')
        expected = {('unit:' + c['unit_id']) if multi else ('row:' + c['segment_id']): c for c in expected_agreement['cases']}
        for row in cases:
            cid = row.get('case_id') if isinstance(row, dict) else None
            if cid not in expected or cid in review_by_id:
                raise ValueError('Codebook-Diagnose: unbekannter oder doppelter Prüffall.')
            original = expected[cid]
            original_ids = original.get('segment_ids', [original.get('segment_id')])
            if row.get('segment_ids') != original_ids or row.get('case_status') != original['case_status'] or row.get('needs_review') is not (original['case_status'] != 'bestätigt'):
                raise ValueError('Codebook-Diagnose: Prüffall widerspricht dem Agreement.')
            human = original.get('human_codes', [original.get('human_code')])
            predicted = original.get('predicted_codes', [original.get('predicted_code')] if original.get('predicted_code') in codes else [])
            if row.get('human_codes') != human or row.get('predicted_codes') != predicted:
                raise ValueError('Codebook-Diagnose: Prüfcodes widersprechen dem Agreement.')
            member = groups[original['unit_id'] if multi else original['segment_id']][0]
            if row.get('person') != member.person or row.get('text') != member.text:
                raise ValueError('Codebook-Diagnose: Prüffall enthält veränderte Originaldaten.')
            review_by_id[cid] = row
        if set(review_by_id) != set(expected):
            raise ValueError('Codebook-Diagnose: Prüffälle fehlen.')
    counters = {code: Counter() for code in codes}
    persons = defaultdict(set)
    alternatives = Counter()
    for s in segments:
        counters[s.human_code]['human_rows'] += 1
        persons[s.human_code].add(s.person)
        if verify is not None:
            v = verify[s.segment_id]
            counters[s.human_code]['verification_rows'] += 1
            if _processing(v) != 'completed':
                counters[s.human_code]['verification_technical_rows'] += 1
            else:
                counters[s.human_code]['verification_completed_rows'] += 1
                counters[s.human_code]['verification_' + v['verification']] += 1
                alternatives.update((s.human_code, code) for code in set(v.get('alternative_codes', [])) if code != s.human_code)
    patterns, pattern_cases = Counter(), defaultdict(list)
    unit_states = Counter()
    cooccurrence = Counter()
    pair_events = sum(len({s.human_code for s in g}) * (len({s.human_code for s in g}) - 1) // 2 for g in groups.values())
    pair_measurable = multi and pair_events <= PAIR_EVENT_LIMIT
    for uid, members in groups.items():
        human = {s.human_code for s in members}
        for code in human:
            counters[code]['human_units'] += 1
        if pair_measurable:
            cooccurrence.update(combinations(sorted(human), 2))
        cid = ('unit:' if multi else 'row:') + uid
        if cid in review_by_id and review_by_id[cid]['needs_review']:
            for code in human:
                counters[code]['review_flagged_units'] += 1
        if predictions is None:
            continue
        b = predictions[uid]
        pred = set(b['predicted_codes'])
        technical = b['processing_status'] != 'completed' or (verify is not None and any(_processing(verify[s.segment_id]) != 'completed' for s in members))
        if b['processing_status'] != 'completed':
            state = 'technical_failure'
        else:
            state = b['assignment_status']
        unit_states[state] += 1
        for code in human:
            counters[code]['blind_' + state + '_units'] += 1
            counters[code]['comparison_technical_failure_units'] += technical
        if b['processing_status'] == 'completed' and b['assignment_status'] == 'assigned':
            for code in pred:
                counters[code]['predicted_units'] += 1
        evaluated = not technical and (state == 'assigned' or (multi and state == 'none'))
        if not evaluated:
            continue
        for code in human:
            counters[code]['evaluated_human_units'] += 1
        for code in human - pred:
            counters[code]['missing_in_blind'] += 1
        for code in pred - human:
            counters[code]['additional_in_blind'] += 1
        if human != pred:
            pattern = (tuple(sorted(human - pred)), tuple(sorted(pred - human)))
            patterns[pattern] += 1
            pattern_cases[pattern].append(cid)
    metadata = []
    keys = ('human_rows', 'human_units', 'predicted_units', 'evaluated_human_units', 'missing_in_blind', 'additional_in_blind',
            'verification_rows', 'verification_completed_rows', 'verification_technical_rows', 'verification_unklar',
            'verification_teilweise_passend', 'verification_nicht_passend', 'blind_none_units', 'blind_abstained_units',
            'blind_technical_failure_units', 'comparison_technical_failure_units', 'review_flagged_units')
    for entry in sorted(codebook, key=lambda c: c.code):
        counts = counters[entry.code]
        flags = []
        if not counts['human_units']:
            flags.append('not_used_in_human_material')
        elif counts['human_units'] < 3:
            flags.append('fewer_than_three_human_units')
        if not entry.ankerbeispiel.strip():
            flags.append('no_anchor_example')
        elif _normalized(entry.definition) == _normalized(entry.ankerbeispiel):
            flags.append('anchor_repeats_definition')
        if not entry.definition.strip():
            flags.append('empty_definition')
        if counts['verification_unklar'] or counts['blind_abstained_units']:
            flags.append('uncertain_assignments_need_review')
        if counts['missing_in_blind'] or counts['additional_in_blind']:
            flags.append('assignment_difference_needs_review')
        fields = {}
        for key in keys:
            available = verify is not None if key.startswith('verification_') else review is not None if key.startswith('review_') else predictions is not None if key not in ('human_rows', 'human_units') else True
            fields[key] = counts[key] if available else None
        metadata.append({'code': entry.code, **fields, 'persons': len(persons[entry.code]), 'hints': flags,
                         'definition_preview': entry.definition[:600], 'definition_characters': len(entry.definition),
                         'definition_preview_truncated': len(entry.definition) > 600,
                         'definition_fingerprint': fingerprint(entry.definition),
                         'has_inclusion_rules': bool(entry.einschluss.strip()), 'has_exclusion_rules': bool(entry.ausschluss.strip()),
                         'has_boundary_rules': bool(entry.abgrenzung.strip())})
    pairs = [{'codes': list(pair), 'coassigned_units': count,
              'smaller_category_units': min(counters[c]['human_units'] for c in pair),
              'overlap_coefficient': count / min(counters[c]['human_units'] for c in pair),
              'repeated_coassignment_hint': count >= 3 and count / min(counters[c]['human_units'] for c in pair) >= .8}
             for pair, count in sorted(cooccurrence.items(), key=lambda x: (-x[1], x[0]))]
    incomplete = unit_states['technical_failure'] > 0 or any(c['verification_technical_rows'] for c in counters.values()) or any(
        source is not None and source.get('processing_status', 'completed') != 'completed' for source in (verification, blind, agreement, review))
    return {'schema_version': 1, 'processing_status': 'incomplete' if incomplete else 'completed', 'model_calls': 0,
            'label_mode': mode, 'unit_basis': 'explicit_passages' if multi else 'coding_rows',
            'n_rows': len(segments), 'n_units': len(groups), 'codebook_fingerprint': fingerprint([c.as_prompt_dict() for c in codebook]),
            'input_fingerprint': make_snapshot(segments, {})['input_fingerprint'],
            'source_availability': {'verification': verify is not None, 'blind': predictions is not None,
                                    'agreement': agreement is not None, 'review': review is not None},
            'categories': metadata, 'blind_unit_states': {k: unit_states[k] for k in ('assigned', 'none', 'abstained', 'technical_failure')} if predictions is not None else None,
            'identical_definitions': _text_groups(codebook, 'definition'), 'shared_anchor_examples': _text_groups(codebook, 'ankerbeispiel'),
            'verification_alternatives': [{'human_code': pair[0], 'alternative_code': pair[1], 'rows': count}
                                         for pair, count in sorted(alternatives.items(), key=lambda x: (-x[1], x[0]))],
            'coassignments': {'status': 'calculated' if pair_measurable else 'not_calculated' if multi else 'not_applicable',
                             'pair_events': pair_events if multi else None, 'event_limit': PAIR_EVENT_LIMIT, 'pairs': pairs},
            'difference_patterns': [{'missing_codes': list(p[0]), 'additional_codes': list(p[1]), 'units': count,
                                     'case_ids': pattern_cases[p], 'is_single_code_pair': len(p[0]) == len(p[1]) == 1}
                                    for p, count in sorted(patterns.items(), key=lambda x: (-x[1], x[0]))],
            'methodological_note': 'Hinweise zur menschlichen Prüfung, keine automatische Codebuchänderung. '
                'Menschliche Codierungen sind Vergleichsreferenz, kein Wahrheitsmaßstab. Gemeinsame Codierung ist keine Verwechslung. '
                'Ähnliche Bedeutung oder Qualität von Definitionen und Ankerbeispielen wird nicht semantisch beurteilt.',
            'limits': ['Unverwendet oder weniger als drei Einheiten ist ein transparenter Prüfhinweis, kein Grund zum Löschen.',
                       'Identische Texte nach NFKC, Kleinschreibung und Leerzeichennormalisierung beweisen keine inhaltliche Redundanz.',
                       'Single-Label: nur gültige konkrete Blindcodes vergleichen; keine Zuordnung separat zählen. Multi-Label: none ist eine gültige leere Menge.',
                       'Enthaltungen und technische Fehler gehen nicht in Mengenabweichungen ein. Verifikation zählt Codierzeilen, Blindcodierung die gewählte Analyseeinheit.',
                       'Der gespeicherte Prüfbedarf ist kein aktueller Fortschritt menschlicher Entscheidungen.',
                       'Stabilitäts- und Sensitivitätsergebnisse werden erst nach Implementierung dieser Module angebunden.']}


def render_codebook_diagnostics(result):
    lines = ['# Codebook-Diagnostik', '', result['methodological_note'], '']
    if result['processing_status'] != 'completed':
        lines += ['Vorläufige Diagnose: Technische Fehler oder unvollständige Quellen zuerst beheben.', '']
    lines += [f"{result['n_rows']} Codierzeilen; {result['n_units']} Analyseeinheiten ({result['unit_basis']}).", '',
              '| Code | Menschliche Einheiten | Modellzuordnungen | Verifikation unklar (Zeilen) | Blind-Enthaltungen (Einheiten) | Keine Blindzuordnung (Einheiten) | Technisch nicht vergleichbar (Einheiten) |', '|---|---:|---:|---:|---:|---:|---:|']
    def display(value):
        return 'nicht verfügbar' if value is None else str(value)
    for row in result['categories']:
        lines.append('| ' + markdown_escape(row['code']) + ' | ' + ' | '.join(display(row[k]) for k in (
            'human_units', 'predicted_units', 'verification_unklar', 'blind_abstained_units', 'blind_none_units', 'comparison_technical_failure_units')) + ' |')
    lines += ['', '## Konkrete Mengenabweichungen', '']
    for row in result['difference_patterns']:
        lines += [f"{row['units']} Einheiten: menschliche Codes ohne Blindzuordnung " + markdown_escape(', '.join(row['missing_codes']) or 'keine') +
                  '; zusätzliche Blindcodes ' + markdown_escape(', '.join(row['additional_codes']) or 'keine') + '.', '',
                  'Prüffälle: ' + ', '.join(map(markdown_escape, row['case_ids'])), '']
    if not result['difference_patterns']:
        lines += ['Keine auswertbaren Mengenabweichungen gespeichert. Quellenverfügbarkeit und technische Fehler getrennt prüfen.', '']
    lines += ['## Gleiche Definitionen und Ankertexte', '']
    for label, key in (('Gleiche Definition', 'identical_definitions'), ('Gleicher Ankertext', 'shared_anchor_examples')):
        for group in result[key]:
            lines += [label + ': ' + ', '.join(map(markdown_escape, group['codes'])), '']
    lines += ['## Alternativen aus der Code-Verifikation', '', 'Vorgeschlagene Alternativen sind keine zusätzlichen Blindzuordnungen.', '']
    for alternative in result['verification_alternatives']:
        lines += [markdown_escape(alternative['human_code']) + ' → ' + markdown_escape(alternative['alternative_code']) + f": {alternative['rows']} Codierzeilen.", '']
    lines += ['## Gemeinsame menschliche Codierungen', '']
    co = result['coassignments']
    if co['status'] == 'not_applicable':
        lines += ['Im Zeilen-/Single-Label-Modus nicht ausgewertet. Gemeinsame Codemengen benötigen den Mehrfachmodus mit expliziten Passage-IDs.', '']
    elif co['status'] != 'calculated':
        lines += [f"Nicht berechnet: {co['pair_events']} Paarereignisse überschreiten die Grenze {co['event_limit']}. Kategorieeinzelzahlen bleiben verfügbar.", '']
    for pair in co['pairs']:
        lines += [markdown_escape(' / '.join(pair['codes'])) + f": {pair['coassigned_units']} gemeinsame Einheiten; Anteil an der kleineren Kategorie {pair['overlap_coefficient']:.1%}. Gemeinsame Codierung ist keine Verwechslung.", '']
    hints = {'not_used_in_human_material': 'Im menschlich codierten Material nicht verwendet.',
             'fewer_than_three_human_units': 'Weniger als drei menschliche Einheiten: geringe Datenbasis beachten.',
             'no_anchor_example': 'Kein Ankerbeispiel gespeichert; bei Bedarf fachlich ergänzen.',
             'anchor_repeats_definition': 'Ankerbeispiel wiederholt die Definition; ein konkretes Beispiel prüfen.',
             'empty_definition': 'Definition fehlt.', 'uncertain_assignments_need_review': 'Unklare Zuordnungen am Original prüfen.',
             'assignment_difference_needs_review': 'Abweichende Codezuordnungen am Original prüfen.'}
    lines += ['## Prüfpunkte je Code', '']
    for row in result['categories']:
        if row['hints']:
            lines += ['### ' + markdown_escape(row['code']), ''] + ['- ' + hints[h] for h in row['hints']] + ['']
    lines += ['## Methodische Grenzen', ''] + ['- ' + markdown_escape(x) for x in result['limits']]
    return '\n'.join(lines)
