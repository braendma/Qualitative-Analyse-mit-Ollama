"""Deterministic topic counts from explicit scoped assignments; no I/O or LLM.

Observed counts are lower bounds whenever a scoped assignment is unclear or
unavailable. Exact counts describe the supplied complete assignment matrix, not
human validation, latent beliefs, or material outside the imported export.
"""
import hashlib
import json
import re

STATUSES = frozenset({'supported', 'opposed', 'both', 'no_evidence', 'unclear', 'failed', 'not_checked'})
DECIDED = frozenset({'supported', 'opposed', 'both', 'no_evidence'})
STANCES = ('supporting', 'opposing', 'both', 'mentioned')


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _strings(values, label, *, nonempty=False):
    if (not isinstance(values, list) or (nonempty and not values) or
            any(not isinstance(value, str) or not value.strip() for value in values) or
            len(set(values)) != len(values)):
        raise ValueError(label + ': eindeutige, nichtleere Kennungen als Liste erforderlich.')
    return sorted(values)


def _material(material):
    if (not isinstance(material, dict) or material.get('schema_version') != 1 or
            type(material.get('schema_version')) is not int or
            not isinstance(material.get('basis_fingerprint'), str) or not material['basis_fingerprint'] or
            material.get('person_basis') not in ('confirmed', 'unconfirmed') or
            not isinstance(material.get('units'), dict)):
        raise ValueError('Thematische Zählung benötigt eine gültige eingefrorene Materialbasis.')
    persons = _strings(material.get('persons'), 'Personenbasis')
    seen_rows = set()
    actual_persons = set()
    for uid, unit in material['units'].items():
        if (not isinstance(uid, str) or not uid.strip() or not isinstance(unit, dict) or
                unit.get('kind') not in ('passage', 'coding_row') or
                not isinstance(unit.get('person'), str) or not unit['person'].strip() or
                not isinstance(unit.get('text'), str)):
            raise ValueError('Ungültige Materialeinheit für die thematische Zählung.')
        rows = _strings(unit.get('segment_ids'), 'Codierzeilen einer Einheit', nonempty=True)
        _strings(unit.get('code_paths'), 'Codepfade einer Einheit', nonempty=True)
        if seen_rows.intersection(rows) or (unit['kind'] == 'coding_row' and len(rows) != 1):
            raise ValueError('Codierzeilen dürfen nicht mehreren Materialeinheiten zugeordnet sein.')
        seen_rows.update(rows)
        actual_persons.add(unit['person'])
    if set(persons) != actual_persons:
        raise ValueError('Personenverzeichnis passt nicht zu den Materialeinheiten.')
    return material


def _topics(material, topics):
    if not isinstance(topics, list):
        raise ValueError('Themen müssen als Liste übergeben werden.')
    normalized = []
    seen = set()
    allowed = {'topic_id', 'definition', 'inclusion', 'exclusion', 'kind', 'scope_unit_ids', 'label'}
    for topic in topics:
        if not isinstance(topic, dict) or set(topic) - allowed:
            raise ValueError('Thema enthält unbekannte Felder oder ist keine Zuordnung.')
        tid = topic.get('topic_id')
        if (not isinstance(tid, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]{0,119}', tid) or tid in seen):
            raise ValueError('Themen benötigen eindeutige stabile IDs.')
        if topic.get('kind') not in ('explicit', 'derived', 'membership'):
            raise ValueError('Thema muss explizite Äußerung, analytische Ableitung oder Gruppen-/Clusterzugehörigkeit kennzeichnen.')
        if (any(not isinstance(topic.get(key), str) for key in ('definition', 'inclusion', 'exclusion')) or
                not topic['definition'].strip() or ('label' in topic and
                (not isinstance(topic['label'], str) or not topic['label'].strip()))):
            raise ValueError('Thema benötigt Definition und textuelle Ein-/Ausschlussregeln; Regeln dürfen leer sein.')
        scope = _strings(topic.get('scope_unit_ids'), 'Thematischer Bezugsraum')
        if set(scope) - material['units'].keys():
            raise ValueError('Thematischer Bezugsraum enthält unbekannte Materialeinheiten.')
        normalized.append({**topic, 'scope_unit_ids': scope})
        seen.add(tid)
    return sorted(normalized, key=lambda topic: topic['topic_id'])


def _assignments(topics, assignments):
    if not isinstance(assignments, list):
        raise ValueError('Thematische Zuordnungen müssen als Liste vorliegen.')
    scopes = {topic['topic_id']: set(topic['scope_unit_ids']) for topic in topics}
    given = {}
    for row in assignments:
        if not isinstance(row, dict) or set(row) != {'topic_id', 'unit_id', 'status'}:
            raise ValueError('Thematische Zuordnung benötigt genau topic_id, unit_id und status.')
        tid, uid, status = row['topic_id'], row['unit_id'], row['status']
        if (not isinstance(tid, str) or not isinstance(uid, str) or not isinstance(status, str) or
                tid not in scopes or uid not in scopes[tid] or status not in STATUSES):
            raise ValueError('Thematische Zuordnung enthält unbekannte IDs, Status oder eine Einheit außerhalb ihres Bezugsraums.')
        key = (tid, uid)
        if key in given:
            raise ValueError('Doppelte thematische Zuordnung; je Thema und Einheit ist genau eine Entscheidung zulässig.')
        given[key] = status
    return [{'topic_id': topic['topic_id'], 'unit_id': uid,
             'status': given.get((topic['topic_id'], uid), 'not_checked')}
            for topic in topics for uid in topic['scope_unit_ids']]


def _scope(material, unit_ids):
    units = material['units']
    kinds = {units[uid]['kind'] for uid in unit_ids}
    basis = 'empty' if not kinds else 'passages' if kinds == {'passage'} else 'coding_rows' if kinds == {'coding_row'} else 'mixed_units'
    confirmed = material['person_basis'] == 'confirmed'
    persons = sorted({units[uid]['person'] for uid in unit_ids})
    return {'unit_ids': sorted(unit_ids), 'unit_count': len(unit_ids), 'unit_basis': basis,
            'coding_row_count': sum(len(units[uid]['segment_ids']) for uid in unit_ids),
            'passage_count': len(unit_ids) if basis == 'passages' else None,
            'person_count': len(persons) if confirmed else None,
            'person_ids': persons if confirmed else None,
            'export_person_count': len(material['persons']) if confirmed else None,
            'export_unit_count': len(units)}


def _counts(material, scope, supporting, opposing, complete):
    unit_sets = {'supporting': set(supporting), 'opposing': set(opposing),
                 'both': set(supporting) & set(opposing), 'mentioned': set(supporting) | set(opposing)}
    people = {key: {material['units'][uid]['person'] for uid in values} for key, values in unit_sets.items()}
    # A person may voice the two positions in different passages.
    people['both'] = people['supporting'] & people['opposing']
    confirmed = material['person_basis'] == 'confirmed'
    passage_basis = scope['unit_basis'] == 'passages'
    out = {}
    for stance in STANCES:
        count = len(unit_sets[stance])
        person_count = len(people[stance]) if confirmed else None
        out[stance] = {'unit_ids': sorted(unit_sets[stance]), 'observed_unit_count': count,
            'exact_unit_count': count if complete else None,
            'observed_passage_count': count if passage_basis else None,
            'exact_passage_count': count if complete and passage_basis else None,
            'person_ids': sorted(people[stance]) if confirmed else None,
            'observed_person_count': person_count,
            'exact_person_count': person_count if complete else None,
            'unit_share_in_scope': count / scope['unit_count'] if complete and scope['unit_count'] else None,
            'person_share_in_scope': person_count / scope['person_count'] if complete and confirmed and scope['person_count'] else None}
    return out


def _coverage(rows):
    counts = {status: sum(row['status'] == status for row in rows) for status in sorted(STATUSES)}
    complete = all(row['status'] in DECIDED for row in rows)
    return {'expected_cells': len(rows), 'decided_cells': sum(counts[status] for status in DECIDED),
            'status_counts': counts, 'complete': complete}


def _topic_result(material, topic, rows):
    supporting = {row['unit_id'] for row in rows if row['status'] in ('supported', 'both')}
    opposing = {row['unit_id'] for row in rows if row['status'] in ('opposed', 'both')}
    scope = _scope(material, topic['scope_unit_ids'])
    coverage = _coverage(rows)
    return {'topic_id': topic['topic_id'], 'definition_fingerprint': _hash(topic), 'kind': topic['kind'],
            'count_meaning': {'explicit': 'expressed_topic_positions', 'derived': 'material_support_for_inference',
                              'membership': 'model_assigned_group_membership'}[topic['kind']],
            'scope': scope, 'coverage': coverage,
            'counts': _counts(material, scope, supporting, opposing, coverage['complete'])}


def count_topics(material, topics, assignments):
    """Count complete scoped assignments; missing cells remain not_checked.

    Inclusion/exclusion may be empty strings, but definition and kind are explicit.
    'both' persons can hold opposite positions in separate passages. Unconfirmed
    person mappings never produce person counts. Mixed/coding-row scopes never
    masquerade as passage counts. Complete means technically decided, not true.
    """
    material = _material(material)
    topics = _topics(material, topics)
    rows = _assignments(topics, assignments)
    by_topic = {topic['topic_id']: [] for topic in topics}
    for row in rows:
        by_topic[row['topic_id']].append(row)
    result = {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
              'material_content_fingerprint': _hash({key: material[key] for key in ('units', 'persons', 'person_basis')}),
              'person_basis': material['person_basis'], 'definitions': topics, 'assignments': rows,
              'assignment_review_status': 'not_verified_by_counting',
              'topics': [_topic_result(material, topic, by_topic[topic['topic_id']]) for topic in topics]}
    result['result_fingerprint'] = _hash(result)
    return result


def union_topics(material, results, *, topic_id, member_topic_ids, definition, exact_union=False,
                 inclusion='', exclusion='', label=None):
    """Explicit OR of scoped topics on one material basis, never a semantic guess.

    Supporting/opposing sets refer to at least one selected member theme; opposing
    positions do not establish logical rejection of an entire abstract meta-theme.
    A newly reworded/narrower theme needs its own assignment matrix instead.
    """
    if exact_union is not True:
        raise ValueError('Themenunion muss ausdrücklich als exakte ODER-Verknüpfung der benannten Quellthemen festgelegt sein.')
    material = _material(material)
    members = _strings(member_topic_ids, 'Quellthemen der Union', nonempty=True)
    sources = results if isinstance(results, list) else [results]
    by_id = {}
    for source in sources:
        if not isinstance(source, dict) or source.get('basis_fingerprint') != material['basis_fingerprint']:
            raise ValueError('Themenunion benötigt dieselbe eingefrorene Materialbasis.')
        rebuilt = count_topics(material, source.get('definitions'), source.get('assignments'))
        if rebuilt != source:
            raise ValueError('Quellzählung verändert oder nicht aus validierten Zuordnungen reproduzierbar.')
        for row in rebuilt['topics']:
            tid = row['topic_id']
            if tid in by_id:
                raise ValueError('Mehrdeutige Quellthemen-ID in der Union.')
            by_id[tid] = row
    if not isinstance(topic_id, str) or set(members) - by_id.keys() or topic_id in by_id:
        raise ValueError('Unbekannte Quellthemen oder bereits verwendete ID der Themenunion.')
    chosen = [by_id[tid] for tid in members]
    kinds = {row['kind'] for row in chosen}
    if len(kinds) != 1:
        raise ValueError('Unterschiedliche Zuordnungsarten dürfen nicht als eine Nennungshäufigkeit vereinigt werden.')
    unit_ids = sorted({uid for row in chosen for uid in row['scope']['unit_ids']})
    topic = {'topic_id': topic_id, 'definition': definition, 'inclusion': inclusion,
             'exclusion': exclusion, 'kind': next(iter(kinds)), 'scope_unit_ids': unit_ids}
    if label is not None:
        topic['label'] = label
    topic = _topics(material, [topic])[0]
    supporting = {uid for row in chosen for uid in row['counts']['supporting']['unit_ids']}
    opposing = {uid for row in chosen for uid in row['counts']['opposing']['unit_ids']}
    scope = _scope(material, unit_ids)
    coverage = {'expected_cells': sum(row['coverage']['expected_cells'] for row in chosen),
                'decided_cells': sum(row['coverage']['decided_cells'] for row in chosen),
                'status_counts': {status: sum(row['coverage']['status_counts'][status] for row in chosen)
                                  for status in sorted(STATUSES)},
                'complete': all(row['coverage']['complete'] for row in chosen)}
    result = {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
              'person_basis': material['person_basis'], 'definition': topic,
              'definition_fingerprint': _hash(topic), 'member_topic_ids': members,
              'union_semantics': 'explicit_or_of_scoped_topics',
              'position_semantics': 'position_towards_at_least_one_member_topic',
              'count_meaning': chosen[0]['count_meaning'],
              'scope': scope, 'coverage': coverage,
              'counts': _counts(material, scope, supporting, opposing, coverage['complete']),
              'assignment_review_status': 'not_verified_by_counting',
              'source_result_fingerprints': sorted(source['result_fingerprint'] for source in sources)}
    result['result_fingerprint'] = _hash(result)
    return result
