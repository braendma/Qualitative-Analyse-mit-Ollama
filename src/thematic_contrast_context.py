"""Explicit global/case comparison spaces; linked findings are separate context."""


def contrast_context(material, counted, register, source_links):
    rows = {row['topic_id']: row for row in counted['topics']}
    topics = {row['topic_id']: row for row in counted['definitions']}
    if (counted['person_basis'] != 'confirmed' or not isinstance(source_links, dict)
            or set(source_links) != set(rows)):
        raise ValueError('Kontrastinterpretation benötigt bestätigte Personen und vollständige Themenherkunft.')
    global_ids = []; cases = {}
    for tid, row in rows.items():
        link = source_links[tid]
        if not isinstance(link, dict):
            raise ValueError('Kontrastthema benötigt eine eindeutige Scope-Rolle.')
        kind = link.get('scope_kind')
        if kind == 'global_pattern':
            if row['scope']['unit_ids'] != sorted(material['units']):
                raise ValueError('Globales Kontrastmuster benötigt den vollständigen Originalumfang.')
            global_ids.append(tid)
        elif kind == 'individual_countercase':
            person = link.get('person')
            full_case = sorted(uid for uid, unit in material['units'].items() if unit['person'] == person)
            if not full_case or row['scope']['unit_ids'] != full_case or row['scope']['person_ids'] != [person]:
                raise ValueError('Gegenfall benötigt den vollständigen Originalumfang seiner bestätigten Person.')
            cases.setdefault(person, []).append(tid)
        else:
            raise ValueError('Kontrastthema benötigt eine eindeutige Scope-Rolle.')
    for tids in cases.values():
        for tid in tids:
            if source_links[tid].get('pattern_topic_id') not in global_ids:
                raise ValueError('Gegenfall benötigt einen eindeutigen Bezug auf ein globales Kontrastmuster.')
    # Equal titles can denote different findings, so scalar labels alone do
    # not identify the meaning being compared. Keep every full definition.
    by_id = {entry['topic_id']: {**entry, 'definition': topics[entry['topic_id']]['definition']}
             for entry in register}
    result = {}
    def reference(tid):
        link = source_links[tid]
        return {'topic_id': tid, 'scope_kind': link['scope_kind'],
                'person': link.get('person'), 'definition': topics[tid]['definition']}
    for tid in rows:
        link = source_links[tid]
        if tid in global_ids:
            compared = global_ids
            linked = sorted(cid for tids in cases.values() for cid in tids
                            if source_links[cid]['pattern_topic_id'] == tid)
            # The reciprocal adapter link is part of the explicit provenance.
            if link.get('countercase_topic_ids') != linked:
                raise ValueError('Globale Gegenfallverweise stimmen nicht mit den gebundenen Fallthemen überein.')
            scope = 'global_patterns'
        else:
            compared = cases[link['person']]
            linked = [link['pattern_topic_id']]
            scope = 'same_person_countercases'
        result[tid] = {'register': [by_id[key] for key in compared],
                       'comparison_scope': scope,
                       'reference_context': [reference(key) for key in linked]}
    return result
