"""Code-specific review hints from verified repetition reports, never new LLM calls."""
from collections import Counter
from multi_label_core import group_units
from sensitivity_core import _recurrence
from coverage_core import markdown_escape as esc

CODING_MODULES = ('blind_coding', 'code_verification')


def _require(condition):
    if not condition:
        raise ValueError('Wiederholungsquelle passt nicht zum Codierbericht oder zur aktuellen Materialbasis.')


def _slice(comparison, segments, codes, mid, label_mode):
    planned = comparison.get('requested_samples')
    included = comparison.get('included_samples')
    _require(comparison.get('schema_version') == 1 and comparison.get('module_id') == mid
             and comparison.get('provenance_status') == 'series_and_artifact_hashes_verified'
             and type(planned) is int and 2 <= planned <= 20
             and isinstance(included, list) and all(isinstance(s, str) for s in included)
             and len(set(included)) == len(included) and len(included) <= planned)
    multi = mid == 'blind_coding' and label_mode == 'multi_label'
    groups = group_units(segments) if multi else {s.segment_id: [s] for s in segments}
    _require(comparison.get('unit_kind') == ('passage' if multi else 'coding_row'))
    units = comparison.get('units')
    _require(isinstance(units, list) and len(units) == len(groups))
    by_id = {}
    comparable = 0
    sample_counts = {sid: Counter() for sid in included}
    sample_denominators = Counter()
    for unit in units:
        uid = unit['unit_id']
        _require(uid in groups and uid not in by_id)
        members = groups[uid]
        _require(unit.get('segment_ids') == [s.segment_id for s in members]
                 and unit.get('person') == members[0].person)
        observations = unit.get('observations')
        _require(isinstance(observations, dict) and set(observations) == set(included))
        counts = Counter(); evaluated = failures = abstentions = 0
        for sid, row in observations.items():
            status = row.get('processing_status')
            _require(status in ('completed', 'failed', 'invalid_input'))
            if status != 'completed':
                failures += 1
                continue
            values = row.get('codes'); state = row.get('state')
            _require(isinstance(values, list) and all(isinstance(c, str) for c in values)
                     and len(set(values)) == len(values) and set(values) <= codes)
            _require(state in (('assigned', 'none', 'abstained') if mid == 'blind_coding'
                               else ('bestätigt', 'teilweise_passend', 'nicht_passend', 'unklar')))
            if mid == 'blind_coding':
                _require((state == 'assigned' and bool(values)) or (state != 'assigned' and not values))
                if state == 'abstained':
                    abstentions += 1
                    continue
            evaluated += 1; counts.update(values);sample_counts[sid].update(values);sample_denominators[sid] += 1
        comparable += evaluated >= 2
        by_id[uid] = {'counts': counts, 'evaluated_repetitions': evaluated,
            'planned_repetitions': planned, 'technical_failure_repetitions': failures,
            'abstention_excluded_repetitions': abstentions,
            'unavailable_repetitions': planned - len(included),
            'segment_ids': [s.segment_id for s in members], 'person': members[0].person,
            'text_preview': members[0].text[:1200], 'text_preview_truncated': len(members[0].text) > 1200}
    return {'units': by_id, 'comparable_units': comparable, 'planned_repetitions': planned,
            'included_repetitions': len(included), 'unit_kind': comparison['unit_kind'],
            'sample_counts': sample_counts, 'sample_denominators': sample_denominators}


def project_repetition_source(payload, kind, segments, codebook, label_mode):
    _require(payload.get('schema_version') == 1 and payload.get('kind') == kind)
    comparisons = payload.get('comparisons')
    _require(isinstance(comparisons, dict))
    codes = {c.code for c in codebook}
    output = {'status': 'available', 'kind': kind, 'modules': [], 'model_calls': 0}
    if kind == 'sensitivity':
        configs = payload.get('configurations')
        _require(isinstance(configs, list) and 2 <= len(configs) <= 10)
        ids = [c['configuration_id'] for c in configs]
        _require(all(isinstance(c, str) for c in ids) and len(set(ids)) == len(ids) and ids[0] == 'baseline')
    else:
        ids = ['baseline']
    for mid in CODING_MODULES:
        if mid not in comparisons:
            continue
        comparison = comparisons[mid]
        within = comparison['within_configurations'] if kind == 'sensitivity' else {'baseline': comparison}
        _require(isinstance(within, dict) and set(within) == set(ids))
        slices = {cid: _slice(within[cid], segments, codes, mid, label_mode) for cid in ids}
        categories, findings = [], []
        for code in sorted(codes):
            within_counts = []
            for cid, part in slices.items():
                varied = sum(0 < u['counts'][code] < u['evaluated_repetitions'] for u in part['units'].values())
                within_counts.append({'configuration_id': cid, 'variable_units': varied,
                    'comparable_units': part['comparable_units'],
                    'planned_repetitions': part['planned_repetitions'],
                    'included_repetitions': part['included_repetitions'],
                    'per_sample': [{'sample_id': sid, 'units': counts[code],
                        'evaluated_units': part['sample_denominators'][sid]}
                        for sid, counts in part['sample_counts'].items()]})
            between, evaluable = 0, 0
            for uid in slices[ids[0]]['units']:
                per = {cid: {k: unit[k] for k in ('evaluated_repetitions', 'planned_repetitions',
                            'technical_failure_repetitions', 'abstention_excluded_repetitions', 'unavailable_repetitions')}
                       | {'present_repetitions': unit['counts'][code]}
                       for cid, part in slices.items() for unit in [part['units'][uid]]}
                recurrence = _recurrence(per)
                varies = any(0 < c['present_repetitions'] < c['evaluated_repetitions'] for c in per.values())
                evaluable += recurrence['observed_patterns_differ'] is not None
                differs = recurrence['observed_patterns_differ'] is True
                between += differs
                if varies or differs:
                    unit = slices[ids[0]]['units'][uid]
                    findings.append({'code': code, 'unit_id': uid,
                        **{k:unit[k] for k in ('segment_ids', 'person', 'text_preview', 'text_preview_truncated')},
                        'within_configuration_variation': varies,
                        'per_configuration': per, **recurrence})
            categories.append({'code': code, 'within_configurations': within_counts,
                'between_configuration_differing_units': between if kind == 'sensitivity' else None,
                'between_configuration_comparable_units': evaluable if kind == 'sensitivity' else None})
        output['modules'].append({'module_id': mid, 'role': 'Blindzuordnung' if mid == 'blind_coding' else 'Verifikationsalternative',
            'unit_kind': slices[ids[0]]['unit_kind'], 'categories': categories, 'findings': findings})
    if not output['modules']:
        output['status'] = 'no_coding_comparison'
    return output


def render_repetition_links(sources):
    lines = ['## Hinweise aus kontrollierten Wiederholungen', '',
        'Zusätzliche Prüfpunkte aus bereits gespeicherten Berichten; keine neuen Modellanfragen. '
        'Schwankungen innerhalb gleicher Einstellungen und Unterschiede zwischen Einstellungen bleiben getrennt. '
        'Sie beweisen weder einen Codebuchfehler noch die Überlegenheit eines Modells.', '']
    for kind, source in sources.items():
        lines += ['### ' + ('Stabilität' if kind == 'stability' else 'Sensitivität'), '']
        if source['status'] != 'available':
            labels = {'unavailable':'Nicht ausgewählt oder noch kein verifizierter Bericht verfügbar.',
                      'invalid':'Quelle ungültig oder unvollständig; keine Zählung daraus.',
                      'no_coding_comparison':'Bericht enthält keinen Blindcodier- oder Verifikationsvergleich.'}
            lines += [labels.get(source['status'], 'Nicht auswertbar.'), ''];continue
        lines += ['Quelldatei: ' + esc(source['artifact']) + '. Im Gesamtbericht den zugehörigen Diagnoseabschnitt öffnen.', '']
        for module in source['modules']:
            lines += ['#### ' + module['role'], '',
                'Verifikationsalternativen sind keine Blindzuordnungen. Inhaltliche Enthaltungen und technische '
                'Fehler zählen nicht als fehlendes Code-Vorkommen. Die Tabelle nennt Einheiten mit mindestens '
                'zwei entscheidbaren Wiederholungen als Nenner; vollständige Einzelzähler stehen im JSON.', '',
                '| Code | Einstellung | Schwankende / vergleichbare Einheiten | Verfügbare / geplante Wiederholungen |',
                '|---|---|---:|---:|']
            for category in module['categories']:
                for counts in category['within_configurations']:
                    lines += ['| '+esc(category['code'])+' | '+esc(counts['configuration_id'])+
                        f" | {counts['variable_units']}/{counts['comparable_units']} | {counts['included_repetitions']}/{counts['planned_repetitions']} |"]
                if kind == 'sensitivity':
                    lines += ['| '+esc(category['code'])+' | Zwischen Einstellungen: unterschiedliche beobachtete Anteile | '+
                        f"{category['between_configuration_differing_units']}/{category['between_configuration_comparable_units']} | – |"]
            lines += ['', '0/0 bedeutet nicht berechenbar, nicht fehlerfrei. Zwischen Einstellungen können schon '
                'teilweise beobachtete Wiederholungen verglichen sein; das ist kein Nachweis einer Parameterursache.', '']
            for finding in module['findings'][:30]:
                lines += ['**'+esc(finding['code'])+'** – Person '+esc(finding['person'])+': '+esc(finding['text_preview']), '']
                if finding['text_preview_truncated']:lines += ['Auszug gekürzt; Originaltext für die Beurteilung öffnen.', '']
                for cid, count in finding['per_configuration'].items():
                    lines += ['- '+esc(cid)+f": Vorkommen {count['present_repetitions']}/{count['evaluated_repetitions']} auswertbaren Wiederholungen; "
                        f"geplant {count['planned_repetitions']}, technische Fehler {count['technical_failure_repetitions']}, "
                        f"Enthaltungen {count['abstention_excluded_repetitions']}, nicht verfügbare Wiederholungen {count['unavailable_repetitions']}."]
                lines += ['']
            if len(module['findings']) > 30:lines += [f"{len(module['findings']) - 30} weitere Prüfpunkte stehen vollständig im JSON.", '']
    return lines
