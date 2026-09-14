"""Pure descriptive comparisons of repetitions; no model calls or truth scores.

The caller must verify series identity and artifact hashes before supplying samples.
This core checks schema/input links, not runtime provenance. No files are changed.
"""
from collections import Counter
from itertools import combinations
import unicodedata

from codebook_diagnostics_core import _blind, _verification
from coding_validation_common import UNKNOWN_CODES
from coverage_core import analyze_coverage
from diagnostic_sources import STAGES, make_snapshot, project_stage
from multi_label_core import group_units
from runtime_support import fingerprint

PAIR_EVENT_LIMIT = 100000
SAMPLE_STATES = {'success', 'failed', 'interrupted', 'paused', 'pending', 'invalid'}


def _ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def _overlap(left, right):
    """Multiset Jaccard; empty evidence is uninformative, never perfect evidence."""
    left, right = Counter(left), Counter(right)
    return _ratio(sum((left & right).values()), sum((left | right).values()))


def _samples(samples, project, *, include_sample=False):
    if not isinstance(samples, list) or not 2 <= len(samples) <= 20:
        raise ValueError('Stabilität benötigt 2 bis 20 ausdrücklich benannte Wiederholungen.')
    valid, excluded, ids = {}, [], set()
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError('Ungültige Wiederholung.')
        sid, status = sample.get('sample_id'), sample.get('status')
        if not isinstance(sid, str) or not sid.strip() or sid in ids or status not in SAMPLE_STATES:
            raise ValueError('Wiederholungs-ID oder Status fehlt, ist doppelt oder ungültig.')
        ids.add(sid)
        if status != 'success':
            excluded.append({'sample_id': sid, 'reason': status})
            continue
        try:
            payload = sample['payload']
            if not isinstance(payload, dict) or payload.get('processing_status', 'completed') != 'completed':
                raise ValueError('Unvollständiges Ergebnis.')
            valid[sid] = project(payload, sample) if include_sample else project(payload)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            # No raw exception/prompt/research text in the exclusion reason.
            excluded.append({'sample_id': sid, 'reason': 'invalid_artifact'})
    return valid, excluded


def _base(samples, valid, excluded):
    return {'schema_version': 1, 'requested_samples': len(samples),
            'included_samples': list(valid), 'excluded_samples': excluded,
            'comparison_status': 'available' if len(valid) >= 2 else 'not_computable',
            'processing_status': 'incomplete' if excluded else 'completed',
            'provenance_status': 'caller_must_verify', 'model_calls': 0}


def _normalized(text):
    # Preserve case, punctuation, negation and numbers. Only canonical Unicode/space.
    return ' '.join(unicodedata.normalize('NFC', text).split())


def _record_identity(row, *, include_text=True):
    identity = {key: row[key] for key in ('kind', 'scope', 'comparison_context', 'segment_ids', 'persons')}
    if include_text:
        identity['text'] = _normalized(row['text'])
    return fingerprint(identity)


def _cluster_pairs(rows):
    groups = [r['segment_ids'] for r in rows if r['kind'] == 'cluster']
    events = sum(len(g) * (len(g) - 1) // 2 for g in groups)
    if events > PAIR_EVENT_LIMIT:
        return {'status': 'not_calculated', 'pair_events': events, 'limit': PAIR_EVENT_LIMIT}, None
    return {'status': 'calculated', 'pair_events': events, 'limit': PAIR_EVENT_LIMIT}, {
        pair for group in groups for pair in combinations(sorted(group), 2)}


def _distribution_changes(left, right):
    """Compare shared Coverage counts. These are selected sources, not all mentions."""
    result = []
    for scope in left['scopes']:
        a, b = left['scopes'][scope], right['scopes'][scope]
        if not (a['record_count'] or b['record_count'] or a['measurable'] or b['measurable']):
            continue
        item = {'scope': scope, 'comparable': a['measurable'] and b['measurable'],
                'persons_named_left': a['persons_named'], 'persons_named_right': b['persons_named'],
                'by_person': [], 'by_category': []}
        result.append(item)
        if not item['comparable']:
            item['reason'] = 'person_references_only' if scope == 'person_reference' else 'missing_segment_links'
            continue
        a, b = a['distribution'], b['distribution']
        if len(a['by_person']) != len(b['by_person']) or len(a['by_category']) != len(b['by_category']):
            raise ValueError('Materialbasis der Wiederholungen weicht ab.')
        item.update(selected_units_left=a['selected_units'], selected_units_right=b['selected_units'],
                    material_units=a['material_units'])
        for p, q in zip(a['by_person'], b['by_person']):
            if p['person'] != q['person'] or p['material_units'] != q['material_units']:
                raise ValueError('Personenbasis der Wiederholungen weicht ab.')
            item['by_person'].append({'person': p['person'], 'material_units': p['material_units'],
                'selected_units_left': p['selected_units'], 'selected_units_right': q['selected_units'],
                'share_left': p['evidence_share'], 'share_right': q['evidence_share'],
                'share_delta': q['evidence_share'] - p['evidence_share']
                    if p['evidence_share'] is not None and q['evidence_share'] is not None else None})
        level_a, level_b = Counter(), Counter()
        for row in a['by_category']:
            level_a[row['level']] += row['selected_coding_rows']
        for row in b['by_category']:
            level_b[row['level']] += row['selected_coding_rows']
        for p, q in zip(a['by_category'], b['by_category']):
            if (p['level'], p['code'], p['material_coding_rows']) != (q['level'], q['code'], q['material_coding_rows']):
                raise ValueError('Kategorienbasis der Wiederholungen weicht ab.')
            item['by_category'].append({'level': p['level'], 'code': p['code'],
                'material_coding_rows': p['material_coding_rows'],
                'selected_coding_rows_left': p['selected_coding_rows'], 'selected_coding_rows_right': q['selected_coding_rows'],
                'level_selected_rows_left': level_a[p['level']], 'level_selected_rows_right': level_b[p['level']],
                'share_left': p['evidence_share_at_level'], 'share_right': q['evidence_share_at_level'],
                'share_delta': q['evidence_share_at_level'] - p['evidence_share_at_level']
                    if p['evidence_share_at_level'] is not None and q['evidence_share_at_level'] is not None else None})
    return result


def analyze_stage_repetitions(segments, module_id, samples):
    """Compare projected records/evidence, not semantic equivalence of whole reports."""
    if module_id not in STAGES:
        raise ValueError('Unbekanntes analytisches Modul.')
    # Validate original IDs even when all samples fail.
    baseline = analyze_coverage(make_snapshot(segments, {}))

    def project(payload, sample):
        projected = project_stage(module_id, payload, segments=segments,
                                  upstream_payloads=sample.get('upstream_payloads'))
        projected['status'] = 'available'
        snapshot = make_snapshot(segments, {module_id: projected})
        checked = snapshot['stages'][module_id]
        if any(not row['valid'] for row in checked['records']):
            raise ValueError('Unaufgelöste oder fremde Referenzen.')
        checked['coverage'] = analyze_coverage(snapshot)['stages'][module_id]
        return checked

    valid, excluded = _samples(samples, project, include_sample=True)
    result = {**_base(samples, valid, excluded), 'module_id': module_id,
              'material': baseline['material'], 'unit_basis': baseline['unit_basis'],
              'pairs': [], 'record_occurrences': [], 'sample_details': [],
              'interpretation': 'Beschreibende Wiederholbarkeit, keine Richtigkeit oder semantische Gleichheit.'}
    identities, inventories, representatives, cluster_pairs = {}, {}, {}, {}
    for sid, data in valid.items():
        rows = data['records']
        identities[sid] = Counter(_record_identity(r) for r in rows)
        inventories[sid] = {}
        for row in rows:
            key = (row['scope'], row['kind'], tuple(row['comparison_context']))
            inv = inventories[sid].setdefault(key, {'segments': set(), 'persons': set()})
            inv['segments'].update(row['segment_ids'])
            inv['persons'].update(row['persons'])
            rid = _record_identity(row)
            representatives.setdefault(rid, {'fingerprint': rid, 'scope': row['scope'], 'kind': row['kind'],
                'comparison_context': row['comparison_context'], 'segment_ids': row['segment_ids'],
                'persons': row['persons'], 'text_preview': row['text'][:1200],
                'text_characters': len(row['text']), 'text_preview_truncated': len(row['text']) > 1200})
        details = {'sample_id': sid, 'projected_records': len(rows), 'warnings': data['warnings'],
                   'coverage': data['coverage']}
        if module_id == 'clusterer':
            details['coassignment'], cluster_pairs[sid] = _cluster_pairs(rows)
        result['sample_details'].append(details)
    for rid, record in sorted(representatives.items()):
        present = [sid for sid in valid if identities[sid][rid]]
        result['record_occurrences'].append({**record, 'sample_ids': present,
            'sample_frequency': _ratio(len(present), len(valid)),
            'counts_per_sample': {sid: identities[sid][rid] for sid in valid},
            'repeat_status': 'not_computable' if len(valid) < 2 else
                'present_in_all' if len(present) == len(valid) else 'variable'})
    for left, right in combinations(valid, 2):
        pair = {'left': left, 'right': right,
                'selection_distribution_changes': _distribution_changes(valid[left]['coverage'], valid[right]['coverage']),
                'projected_record_overlap': _overlap(identities[left], identities[right]),
                'projected_reference_binding_overlap': _overlap(
                    Counter(_record_identity(r, include_text=False) for r in valid[left]['records']),
                    Counter(_record_identity(r, include_text=False) for r in valid[right]['records'])),
                'reference_comparisons': []}
        for key in sorted(inventories[left].keys() | inventories[right].keys()):
            a = inventories[left].get(key, {'segments': set(), 'persons': set()})
            b = inventories[right].get(key, {'segments': set(), 'persons': set()})
            pair['reference_comparisons'].append({'scope': key[0], 'kind': key[1],
                'comparison_context': list(key[2]), 'segment_overlap': _overlap(a['segments'], b['segments']),
                'person_overlap': _overlap(a['persons'], b['persons'])})
        if module_id == 'clusterer':
            # Arbitrary cluster names and array positions are deliberately ignored.
            memberships = lambda sid: Counter(tuple(r['segment_ids']) for r in valid[sid]['records'] if r['kind'] == 'cluster')
            pair['cluster_membership_overlap'] = _overlap(memberships(left), memberships(right))
            a, b = cluster_pairs[left], cluster_pairs[right]
            pair['coassignment_overlap'] = _overlap(a, b) if a is not None and b is not None else None
        result['pairs'].append(pair)
    return result


def analyze_coding_repetitions(segments, codebook, module_id, samples, *, label_mode='single_label'):
    """Exact model-to-model decisions, separately from abstention and technical failure."""
    if module_id not in {'blind_coding', 'code_verification'} or label_mode not in {'single_label', 'multi_label'}:
        raise ValueError('Ungültiger Codiervergleich.')
    make_snapshot(segments, {})
    codes = {c.code for c in codebook}
    if len(codes) != len(codebook) or codes & UNKNOWN_CODES or any(s.human_code not in codes for s in segments):
        raise ValueError('Ungültiges oder unpassendes Kategoriensystem.')
    multi = label_mode == 'multi_label' and module_id == 'blind_coding'
    groups = group_units(segments) if multi else {s.segment_id: [s] for s in segments}

    def project(payload):
        if module_id == 'blind_coding':
            raw = _blind(groups, payload, codes, multi)
            return {uid: {'state': row['assignment_status'], 'codes': sorted(row['predicted_codes']),
                          'processing_status': row.get('processing_status', 'completed')} for uid, row in raw.items()}
        raw = _verification(segments, payload, codes)
        return {uid: {'state': row['verification'], 'codes': sorted(set(row.get('alternative_codes', []))),
                      'processing_status': row.get('processing_status', 'completed')} for uid, row in raw.items()}

    valid, excluded = _samples(samples, project)
    result = {**_base(samples, valid, excluded), 'module_id': module_id,
              'unit_kind': 'passage' if multi else 'coding_row', 'n_units': len(groups),
              'pairs': [], 'units': [], 'code_occurrences': [],
              'interpretation': 'Modell–Modell-Wiederholbarkeit, keine Übereinstimmung mit menschlicher Wahrheit.'}
    for uid in groups:
        observations = {sid: rows[uid] for sid, rows in valid.items()}
        failed = [sid for sid, row in observations.items() if row['processing_status'] != 'completed']
        if failed:
            result['processing_status'] = 'incomplete'
        result['units'].append({'unit_id': uid, 'segment_ids': [s.segment_id for s in groups[uid]],
            'person': groups[uid][0].person, 'text_preview': groups[uid][0].text[:1200],
            'text_characters': len(groups[uid][0].text), 'text_preview_truncated': len(groups[uid][0].text) > 1200,
            'observations': observations, 'technical_failure_samples': failed})
    for left, right in combinations(valid, 2):
        usable = [uid for uid in groups if all(valid[sid][uid]['processing_status'] == 'completed' for sid in (left, right))]
        decisive = [uid for uid in usable if all(valid[sid][uid]['state'] in {'assigned', 'none'} for sid in (left, right))]
        pair = {'left': left, 'right': right, 'technical_excluded_units': len(groups) - len(usable),
            'state_agreement': _ratio(sum(valid[left][u]['state'] == valid[right][u]['state'] for u in usable), len(usable))}
        if module_id == 'blind_coding':
            pair['code_set_agreement'] = _ratio(sum(valid[left][u]['codes'] == valid[right][u]['codes'] for u in decisive), len(decisive))
            pair['abstention_excluded_units'] = len(usable) - len(decisive)
        else:
            pair['alternative_set_agreement'] = _ratio(sum(valid[left][u]['codes'] == valid[right][u]['codes'] for u in usable), len(usable))
        result['pairs'].append(pair)
    for code in sorted(codes):
        result['code_occurrences'].append({'code': code,
            'role': 'blind_assignment' if module_id == 'blind_coding' else 'verification_alternative',
            'per_sample': [{'sample_id': sid,
                'units': sum(code in r['codes'] for r in rows.values() if r['processing_status'] == 'completed'),
                'evaluated_units': sum(r['processing_status'] == 'completed' and
                    (module_id != 'blind_coding' or r['state'] in {'assigned', 'none'}) for r in rows.values())}
                for sid, rows in valid.items()]})
    return result
