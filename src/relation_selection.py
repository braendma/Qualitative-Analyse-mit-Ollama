"""Pure replayable relation selection from verified complete original material."""
from copy import deepcopy

from runtime_support import fingerprint
from thematic_adapters import _require, _nonempty, build_summary_topics
from thematic_counts import count_topics
from thematic_person_adapters import _unweighted

ALGORITHM = 'person_paired_round_robin_v1'


def _parameters(max_pairs, max_segments_per_path):
    _require(type(max_pairs) is int and max_pairs >= 0, 'max_pairs muss eine ganze Zahl ab null sein; null bedeutet alle Paare.')
    _require(type(max_segments_per_path) is int and max_segments_per_path > 0,
             'max_segments_per_path muss eine positive ganze Zahl sein.')


def _originals(material, cluster_payload, summary_payload):
    # The existing thematic validator checks each original code row, complete
    # membership, confirmed person metadata and exact summary/cluster identity.
    _require(isinstance(material, dict) and material.get('person_basis') == 'confirmed',
             'Relationsauswahl benötigt eine bestätigte vollständige Personenbasis.')
    from thematic_counts import _material
    from relation_cooccurrence import _verified_index
    _verified_index(_material(material))
    clusters = _unweighted(cluster_payload); summaries = _unweighted(summary_payload)
    build_summary_topics(material, clusters, summaries)
    texts = {sid: material['units'][row['unit_id']]['text'] for sid, row in material['segment_index'].items()}
    from relation_analysis_core import build_units
    units = build_units(clusters['clusters'], texts, summaries, clusters['segment_metadata'])
    return clusters, summaries, texts, units


def _key(pair):
    return 'relation_pair_' + fingerprint({'algorithm': ALGORITHM, 'pfad_a': pair['pfad_a'], 'pfad_b': pair['pfad_b']})[:24]


def build_relation_selection(material, cluster_payload, summary_payload, *, max_pairs, max_segments_per_path):
    """Capture actual existing core selection without inventing another sampler.

    Contains identities/hashes, not duplicate quote texts. All ranked *eligible*
    pairs are recorded; zero shared-person pairs are explicitly outside eligibility.
    """
    _parameters(max_pairs, max_segments_per_path)
    clusters, summaries, texts, units = _originals(material, cluster_payload, summary_payload)
    from relation_analysis_core import build_candidate_pairs, candidate_pair_index
    all_pairs = candidate_pair_index(units)
    selected, selected_total = build_candidate_pairs(units, max_pairs, max_segments_per_path)
    _require(selected_total == len(all_pairs))
    chosen = {_key(pair): pair for pair in selected}
    paths = {}
    for path, unit in sorted(units.items()):
        ids = unit['segment_ids']
        expected = {sid for sid, row in material['segment_index'].items() if row['code_path'] == path}
        _require(set(ids) == expected, 'Relationscodepfad stimmt nicht mit sämtlichen Originalcodierzeilen überein.')
        paths[path] = {'segment_ids': list(ids), 'person_ids': sorted(unit['personen']),
            'unit_ids': sorted({material['segment_index'][sid]['unit_id'] for sid in ids})}
    candidates = []; submitted = {}
    for rank, (_, path_a, path_b, shared) in enumerate(all_pairs, 1):
        key = _key({'pfad_a': path_a, 'pfad_b': path_b})
        candidates.append({'pair_key': key, 'rank': rank, 'pfad_a': path_a, 'pfad_b': path_b,
            'shared_person_ids': list(shared), 'selected': key in chosen,
            'pair_id': chosen[key]['pair_id'] if key in chosen else None})
    for key, pair in chosen.items():
        submitted[key] = {'pair_id': pair['pair_id'], 'pfad_a': pair['pfad_a'], 'pfad_b': pair['pfad_b'],
            'segment_ids_a': [row['id'] for row in pair['segmente_a']],
            'segment_ids_b': [row['id'] for row in pair['segmente_b']],
            'sampled_person_ids': list(pair['gemeinsame_personen']),
            'shared_person_ids': list(pair['gemeinsame_personen_gesamt']),
            'selection_rule': pair['auswahlregel'], 'original_pair_fingerprint': fingerprint(pair)}
    receipt = {'schema_version': 1, 'verification_level': 'confirmed_original_material', 'algorithm': ALGORITHM,
        'parameters': {'max_pairs': max_pairs, 'max_segments_per_path': max_segments_per_path},
        'basis_fingerprint': material['basis_fingerprint'],
        'material_content_fingerprint': count_topics(material, [], [])['material_content_fingerprint'],
        'source_cluster_fingerprint': fingerprint(clusters), 'source_summary_fingerprint': fingerprint(summaries),
        'idmap_fingerprint': fingerprint(texts), 'path_registry': paths,
        'candidate_pairs': candidates, 'submitted_pairs': dict(sorted(submitted.items())),
        'eligibility_note': 'Nur Codepfadpaare mit mindestens einer gemeinsamen bestätigten Person sind Modellkandidaten. Nicht ausgewählte oder befundlose Paare sind keine nachgewiesenen Nullrelationen.'}
    receipt['selection_fingerprint'] = fingerprint(receipt)
    return receipt


def _ids(values, *, nonempty=False):
    _require(isinstance(values, list) and (values or not nonempty) and all(_nonempty(v) for v in values))
    _require(len(values) == len(set(values)))
    return values


def _number(value, expected):
    _require(type(value) is int and value == expected, 'Relationsstatistik passt nicht zur gespeicherten Originalauswahl.')


def validate_relation_selection(material, payload, cluster_payload, summary_payload):
    """Replay selection and validate actual output evidence, never infer causality.

    Legacy outputs remain caller-readable, but cannot pass this complete-evidence
    contract without their own recorded parameters and verified original basis.
    """
    original = _unweighted(payload)
    saved = original.get('selection_provenance')
    _require(isinstance(saved, dict) and saved.get('verification_level') == 'confirmed_original_material',
             'Historischer oder unbestätigter Relationsauswahlumfang ist nicht vollständig nachweisbar.')
    params = saved.get('parameters')
    _require(isinstance(params, dict) and set(params) == {'max_pairs', 'max_segments_per_path'})
    expected = build_relation_selection(material, cluster_payload, summary_payload, **params)
    _require(fingerprint(saved) == fingerprint(expected), 'Gespeicherte Relationsauswahl stimmt nicht vollständig mit den Originalvorstufen überein.')
    clusters, summaries, texts, units = _originals(material, cluster_payload, summary_payload)
    from relation_analysis_core import build_candidate_pairs, ALLOWED_RELATION_TYPES
    pairs, total = build_candidate_pairs(units, **params)
    lookup = {pair['pair_id']: pair for pair in pairs}
    for field, source in (('source_cluster_created_at', clusters), ('source_summary_created_at', summaries)):
        _require(field in original and original[field] == source.get('created_at'))
    records = original.get('beziehungen')
    _require(isinstance(records, list) and isinstance(original.get('gesamteinordnung'), str))
    _number(original.get('codepfad_count'), len(units))
    for field, number in (('candidate_pair_count_total', total), ('omitted_pair_count', total-len(pairs)),
        ('candidate_pair_count_submitted', len(pairs)), ('candidate_pair_count_with_relation', len(records)),
        ('candidate_pair_count_without_validated_relation', len(pairs)-len(records))):
        _number(original.get(field), number)
    seen = set()
    fields = {'bezugsebene', 'beidseitig_belegte_personen', 'relation_id', 'pair_id', 'thema', 'beziehungstyp',
              'beschreibung', 'pfad_a', 'pfad_b', 'gemeinsame_personen', 'segment_ids_a', 'segment_ids_b', 'belege_a', 'belege_b'}
    for index, row in enumerate(records, 1):
        _require(isinstance(row, dict) and set(row) == fields)
        pair_id = row['pair_id']
        _require(isinstance(pair_id, str) and pair_id in lookup and pair_id not in seen)
        seen.add(pair_id); pair = lookup[pair_id]
        _require(row['relation_id'] == f'REL{index:04d}' and _nonempty(row['thema']) and isinstance(row['beschreibung'], str))
        _require(isinstance(row['beziehungstyp'], str) and row['beziehungstyp'] in ALLOWED_RELATION_TYPES)
        _require(row['gemeinsame_personen'] == pair['gemeinsame_personen'])
        selected_people = {}
        for side in ('a', 'b'):
            _require(row['pfad_' + side] == pair['pfad_' + side])
            ids = _ids(row['segment_ids_' + side], nonempty=True)
            _require(set(ids) <= {entry['id'] for entry in pair['segmente_' + side]}, 'Relationsbeleg liegt außerhalb der tatsächlich übermittelten Seite.')
            _require(row['belege_' + side] == [{'segment_id': sid, 'text': texts[sid]} for sid in ids],
                     'Relationszitate entsprechen nicht exakt den gespeicherten Originalbelegen.')
            selected_people[side] = {material['units'][material['segment_index'][sid]['unit_id']]['person'] for sid in ids}
        shared = sorted(selected_people['a'] & selected_people['b'])
        _require(row['beidseitig_belegte_personen'] == shared)
        _require(row['bezugsebene'] == ('innerhalb_person' if shared else 'personenuebergreifend'))
    reductions = original.get('context_reduction')
    _require(isinstance(reductions, dict) and set(reductions) <= set(lookup))
    for pair_id, sides in reductions.items():
        _require(isinstance(sides, dict) and set(sides) == {'a', 'b'})
        for side, receipt in sides.items():
            _require(isinstance(receipt, dict) and type(receipt.get('used')) is bool)
            _require(receipt.get('source_sha256') == fingerprint(lookup[pair_id]['cluster_' + side]),
                     'Relations-Kontextverdichtung verweist auf einen anderen Originalclusterkontext.')
            if receipt['used']:
                _require(set(receipt) == {'used', 'source_sha256', 'summary', 'note'} and
                         _nonempty(receipt['summary']) and isinstance(receipt['note'], str))
            else:
                _require(set(receipt) == {'used', 'source_sha256'})
    return deepcopy(expected)
