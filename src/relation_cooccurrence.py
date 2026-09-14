"""Pure co-occurrence of existing exact code paths, never semantic relations.

Confirmation/file provenance belongs to load_counting_material at the caller.
This helper verifies the complete row index against material units and counts
all unordered distinct-code pairs, including pairs with no common people.
"""
from itertools import combinations

from coverage_core import markdown_escape
from thematic_counts import _hash, _material, _material_index


NOTE = ('Gezählt werden vorhandene exakte Codezuordnungen im exportierten Material, '
        'keine neu geprüften thematischen Nennungen, semantischen Beziehungen oder Ursachen. '
        'Codes bei derselben Person können in verschiedenen Passagen vorkommen. '
        'Nur explizite Passage-IDs belegen dieselbe Passage; gleicher Text genügt nicht. '
        'Bei fehlenden Passage-IDs sind bekannte Passagen beobachtete Untergrenzen; '
        'exakte Passagezahlen und Passageanteile bleiben unbestimmt.')


def _verified_index(material):
    """Compatibility entry point for the common original-row validation."""
    return _material_index(material)


def count_code_path_cooccurrences(material):
    """Count a complete exact-code register and every unordered code pair.

    Person shares use all confirmed people in the export. Passage shares exist
    only when every material unit has an explicit passage ID. No input mutation,
    I/O, model calls, ancestor-code expansion, or text-based deduplication.
    """
    material = _material(material)
    if material['person_basis'] != 'confirmed':
        raise ValueError('Code-Kovorkommen benötigt zuerst eine bestätigte Personenzuordnung.')
    index = _verified_index(material)
    units = material['units']
    all_people = sorted(material['persons'])
    known_passages = {uid for uid, unit in units.items() if unit['kind'] == 'passage'}
    complete_passages = len(known_passages) == len(units)
    by_code = {}
    for sid, row in sorted(index.items()):
        entry = by_code.setdefault(row['code_path'], {'segment_ids': [], 'unit_ids': set(), 'person_ids': set()})
        entry['segment_ids'].append(sid)
        entry['unit_ids'].add(row['unit_id'])
        entry['person_ids'].add(units[row['unit_id']]['person'])

    def person_count(ids):
        return {'person_ids': sorted(ids), 'count': len(ids),
                'share_in_export': len(ids) / len(all_people) if all_people else None}

    def passage_count(ids):
        ids = set(ids) & known_passages
        return {'observed_known_passage_ids': sorted(ids), 'observed_known_passage_count': len(ids),
                'exact_passage_count': len(ids) if complete_passages else None,
                'share_in_export': len(ids) / len(known_passages) if complete_passages and known_passages else None}

    codes = []
    for code, row in sorted(by_code.items()):
        codes.append({'code_path': code, 'coding_row_ids': list(row['segment_ids']),
                      'coding_row_count': len(row['segment_ids']), 'material_unit_ids': sorted(row['unit_ids']),
                      'material_unit_count': len(row['unit_ids']),
                      'persons': person_count(row['person_ids']), 'passages': passage_count(row['unit_ids'])})
    pairs = []
    for a, b in combinations(sorted(by_code), 2):
        first, second = by_code[a], by_code[b]
        pairs.append({'pair_key': 'code_pair_' + _hash([a, b])[:24], 'code_a': a, 'code_b': b,
                      'persons': {'a': person_count(first['person_ids']), 'b': person_count(second['person_ids']),
                                  'intersection': person_count(first['person_ids'] & second['person_ids'])},
                      'passages': {'a': passage_count(first['unit_ids']), 'b': passage_count(second['unit_ids']),
                                   'intersection': passage_count(first['unit_ids'] & second['unit_ids'])}})
    content_hash = _hash({key: material[key] for key in ('units', 'persons', 'person_basis')})
    result = {'schema_version': 1, 'count_basis': 'existing_code_path_assignments',
              'basis_fingerprint': material['basis_fingerprint'],
              'material_content_fingerprint': content_hash,
              'cooccurrence_basis_fingerprint': _hash({'schema_version': 1,
                  'count_basis': 'existing_code_path_assignments',
                  'material_content_fingerprint': content_hash, 'segment_index': index}),
              'scope': {'person_ids': all_people, 'person_count': len(all_people),
                        'material_unit_count': len(units), 'coding_row_count': len(index),
                        'passage_basis_complete': complete_passages,
                        'observed_known_passage_count': len(known_passages),
                        'exact_passage_count': len(known_passages) if complete_passages else None},
              'code_paths': codes, 'pairs': pairs, 'model_calls': 0,
              'methodological_note': NOTE}
    result['result_fingerprint'] = _hash(result)
    return result


def code_path_cooccurrences_markdown(result):
    """Render this deterministic result without exporting raw segment text."""
    if (not isinstance(result, dict) or result.get('schema_version') != 1
            or result.get('count_basis') != 'existing_code_path_assignments'
            or result.get('result_fingerprint') != _hash({k: v for k, v in result.items() if k != 'result_fingerprint'})):
        raise ValueError('Code-Kovorkommensbericht benötigt ein unverändertes Zählergebnis.')
    people = result['scope']['person_count']
    lines = ['## Gemeinsames Auftreten vorhandener Codepfade', markdown_escape(NOTE),
             'Personenbezugsmenge: ' + str(people) + ' bestätigte Personen im Export.',
             '| Code A | Code B | Personen mit A | Personen mit B | Personen mit beiden Codes | Gemeinsame bekannte Passagen | Exakte gemeinsame Passagen |',
             '|---|---|---:|---:|---:|---:|---:|']
    for row in result['pairs']:
        exact = row['passages']['intersection']['exact_passage_count']
        cells = [row['code_a'], row['code_b'], row['persons']['a']['count'], row['persons']['b']['count'],
                 row['persons']['intersection']['count'], row['passages']['intersection']['observed_known_passage_count'],
                 exact if exact is not None else 'nicht bestimmbar']
        lines.append('| ' + ' | '.join(markdown_escape(value) for value in cells) + ' |')
    if not result['pairs']:
        lines.append('Weniger als zwei verschiedene Codepfade; keine Codepaare vorhanden.')
    return '\n\n'.join(lines[:3]) + '\n\n' + '\n'.join(lines[3:]) + '\n'
