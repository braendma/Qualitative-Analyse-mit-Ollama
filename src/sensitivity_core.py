"""Descriptive configuration comparison, preserving repetitions and missingness."""
from collections import Counter

from diagnostic_sources import STAGES
from runtime_support import fingerprint
from stability_core import analyze_coding_repetitions, analyze_stage_repetitions, _ratio


def _recurrence(per_configuration):
    observed = [c for c, v in per_configuration.items() if v['evaluated_repetitions']]
    complete = [c for c in observed if per_configuration[c]['evaluated_repetitions'] ==
                per_configuration[c]['planned_repetitions']]
    repeated = [c for c in observed if per_configuration[c]['evaluated_repetitions'] >= 2]
    any_ids = [c for c in observed if per_configuration[c]['present_repetitions']]
    all_ids = [c for c in repeated if per_configuration[c]['present_repetitions'] ==
               per_configuration[c]['evaluated_repetitions']]
    signatures = {(per_configuration[c]['present_repetitions'] /
                   per_configuration[c]['evaluated_repetitions']) for c in observed}
    return {'planned_configurations': len(per_configuration), 'observed_configurations': observed,
        'complete_configurations': complete,
        'excluded_configurations': [c for c in per_configuration if c not in observed],
        'provisional_configurations': [c for c in observed if c not in complete],
        'any_observed_repeat': {**_ratio(len(any_ids), len(observed)), 'configuration_ids': any_ids},
        'all_observed_repeats': {**_ratio(len(all_ids), len(repeated)), 'configuration_ids': all_ids,
                                 'eligible_configuration_ids': repeated},
        'any_repeat_complete_only': _ratio(sum(c in any_ids for c in complete), len(complete)),
        'all_repeats_complete_only': _ratio(sum(c in all_ids for c in complete), len(complete)),
        'observed_patterns_differ': len(signatures) > 1 if len(observed) >= 2 else None}


def _stage_features(within, module_id):
    """Use shared projections; do not infer semantic equivalence from wording."""
    features = {}
    for row in within['record_occurrences']:
        detail = {k: row[k] for k in ('scope', 'kind', 'comparison_context', 'segment_ids',
                  'persons', 'text_preview', 'text_characters', 'text_preview_truncated')}
        features[('exact_projection', row['fingerprint'])] = (detail, set(row['sample_ids']))
        binding = {k: row[k] for k in ('scope', 'kind', 'comparison_context', 'segment_ids', 'persons')}
        key = ('reference_binding', fingerprint(binding))
        features.setdefault(key, (binding, set()))[1].update(row['sample_ids'])
        if module_id == 'clusterer':
            membership = {'segment_ids': sorted(row['segment_ids']), 'persons': row['persons']}
            key = ('cluster_membership', fingerprint(membership))
            features.setdefault(key, (membership, set()))[1].update(row['sample_ids'])
    return features


def _selection_distributions(within):
    """Ranges describe repetitions, never pooled evidence or independent persons."""
    table = {}
    for cid, result in within.items():
        for sample in result.get('sample_details', []):
            for scope, data in sample['coverage']['scopes'].items():
                if not data['measurable']:
                    continue
                distribution = data['distribution']
                level_totals = Counter()
                for row in distribution['by_category']:
                    level_totals[row['level']] += row['selected_coding_rows']
                for kind in ('by_person', 'by_category'):
                    for row in distribution[kind]:
                        if kind == 'by_person':
                            detail = {'person': row['person'], 'material_units': row['material_units']}
                            count, denominator = row['selected_units'], distribution['selected_units']
                        else:
                            detail = {k: row[k] for k in ('level', 'code', 'material_coding_rows')}
                            count, denominator = row['selected_coding_rows'], level_totals[row['level']]
                        key = (scope, kind, fingerprint(detail))
                        entry = table.setdefault(key, {'scope': scope, 'kind': kind, **detail,
                            'per_configuration': {c: {'samples': [], 'planned_repetitions': w['requested_samples']}
                                                  for c, w in within.items()}})
                        entry['per_configuration'][cid]['samples'].append({'sample_id': sample['sample_id'],
                            'selected': count, 'share': _ratio(count, denominator)})
    for entry in table.values():
        for data in entry['per_configuration'].values():
            counts = [s['selected'] for s in data['samples']]
            shares = [s['share']['value'] for s in data['samples'] if s['share']['value'] is not None]
            data.update(evaluated_repetitions=len(counts), selected_range=[min(counts), max(counts)] if counts else None,
                        share_range=[min(shares), max(shares)] if shares else None,
                        repetitions_with_defined_share=len(shares))
    return [table[key] for key in sorted(table)]


def analyze_sensitivity(segments, codebook, module_id, configurations, samples, *, label_mode='single_label'):
    """Configurations have equal weight; every frequency declares its denominator.

    Strict summaries require every planned repeat to be evaluable for that feature.
    Exploratory summaries retain partial observations, explicitly marked provisional.
    No p-values, causal attributions or automatic quality rankings are calculated.
    """
    if not isinstance(configurations, list) or not 2 <= len(configurations) <= 10:
        raise ValueError('Sensitivität benötigt 2 bis 10 Konfigurationen einschließlich Basis.')
    ids = [c.get('configuration_id') for c in configurations]
    if any(not isinstance(c, str) or not c for c in ids) or len(set(ids)) != len(ids) or ids[0] != 'baseline':
        raise ValueError('Ungültige Konfigurationszuordnung.')
    if not isinstance(samples, list) or any(not isinstance(s, dict) or s.get('configuration_id') not in ids for s in samples):
        raise ValueError('Wiederholung ohne geplante Konfiguration.')
    sample_ids = [s.get('sample_id') for s in samples]
    if any(not isinstance(s, str) for s in sample_ids) or len(set(sample_ids)) != len(sample_ids):
        raise ValueError('Wiederholungen müssen serienweit eindeutig sein.')
    within = {}
    for cid in ids:
        group = [s for s in samples if s['configuration_id'] == cid]
        within[cid] = (analyze_stage_repetitions(segments, module_id, group) if module_id in STAGES else
            analyze_coding_repetitions(segments, codebook, module_id, group, label_mode=label_mode))
    if len({w['requested_samples'] for w in within.values()}) != 1:
        raise ValueError('Konfigurationen müssen dieselbe geplante Wiederholungszahl haben.')
    findings = []
    if module_id in STAGES:
        features = {cid: _stage_features(w, module_id) for cid, w in within.items()}
        for key in sorted(set().union(*(set(f) for f in features.values()))):
            detail = next(f[key][0] for f in features.values() if key in f)
            per = {cid: {'present_repetitions': len(features[cid].get(key, ({}, set()))[1]),
                'evaluated_repetitions': len(w['included_samples']), 'planned_repetitions': w['requested_samples']}
                for cid, w in within.items()}
            findings.append({'feature_type': key[0], **detail, 'per_configuration': per, **_recurrence(per)})
    else:
        units = {cid: {u['unit_id']: u for u in w['units']} for cid, w in within.items()}
        for uid, unit in units[ids[0]].items():
            detail = {k: unit[k] for k in ('unit_id', 'segment_ids', 'person', 'text_preview',
                      'text_characters', 'text_preview_truncated')}
            observations = {cid: [r for r in units[cid][uid]['observations'].values()
                                  if r['processing_status'] == 'completed'] for cid in ids}
            decisive = {cid: [r for r in rows if module_id != 'blind_coding' or r['state'] in {'assigned', 'none'}]
                        for cid, rows in observations.items()}
            states = sorted({r['state'] for rows in observations.values() for r in rows})
            codes = sorted({c for rows in decisive.values() for r in rows for c in r['codes']})
            sets = sorted({tuple(r['codes']) for rows in decisive.values() for r in rows})
            for feature, values in [('decision_state', states), ('code_presence', codes), ('code_set', sets)]:
                for value in values:
                    population = observations if feature == 'decision_state' else decisive
                    per = {}
                    for cid, rows in population.items():
                        matches = sum((r['state'] == value if feature == 'decision_state' else
                            value in r['codes'] if feature == 'code_presence' else tuple(r['codes']) == value) for r in rows)
                        per[cid] = {'present_repetitions': matches, 'evaluated_repetitions': len(rows),
                            'planned_repetitions': within[cid]['requested_samples'],
                            'technical_failure_repetitions': len(units[cid][uid]['technical_failure_samples']),
                            'abstention_excluded_repetitions': len(observations[cid]) - len(rows)}
                    findings.append({'feature_type': feature, 'value': list(value) if isinstance(value, tuple) else value,
                        'role': 'blind_assignment' if module_id == 'blind_coding' else 'verification_alternative',
                        **detail, 'per_configuration': per, **_recurrence(per)})
    return {'schema_version': 1, 'module_id': module_id, 'model_calls': 0,
        'processing_status': 'completed' if all(w['processing_status'] == 'completed' for w in within.values()) else 'incomplete',
        'provenance_status': 'caller_must_verify', 'within_configurations': within, 'findings': findings,
        'selection_distributions': _selection_distributions(within) if module_id in STAGES else [],
        'comparison_status': 'available' if sum(bool(w['included_samples']) for w in within.values()) >= 2 else 'not_computable',
        'notes': ['Eine Konfiguration zählt einmal, unabhängig von der Anzahl erfolgreicher Wiederholungen.',
                  'Vorkommen meint exakte Projektionen, Belegbindungen oder Codierentscheidungen, keine semantisch geprüften Themen.',
                  'Alle beobachteten Wiederholungen verlangt mindestens zwei auswertbare Wiederholungen.',
                  'Vollständige Vergleiche verlangen alle geplanten Wiederholungen; Teilbeobachtungen bleiben vorläufig.',
                  'Unterschiede zwischen Konfigurationen können zugleich durch Schwankungen innerhalb einer Konfiguration entstehen.']}
