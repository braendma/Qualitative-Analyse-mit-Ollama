"""Pure adapters from existing unweighted outputs to explicit thematic contracts.

Callers verify artifact/run provenance before these structural adapters. Selected
SWOT evidence never becomes complete membership. No model requests or file I/O.
"""
from copy import deepcopy

from runtime_support import fingerprint
from thematic_material import unit_ids_for_segments
from thematic_memberships import cluster_memberships
from thematic_counts import _material as validate_material, _topics as validate_topics

DIMENSIONS = ('Stärken', 'Schwächen', 'Chancen', 'Risiken')


def _require(condition, message='Analysequelle passt nicht zur geprüften thematischen Materialbasis.'):
    if not condition:
        raise ValueError(message)


def _completed(payload):
    # Existing successful SWOT/summary payloads predate a top-level status field.
    _require(isinstance(payload, dict) and payload.get('processing_status', 'completed') == 'completed',
             'Für die Themenvorbereitung wird eine vollständige Analysequelle benötigt.')


def _source_metadata(material, metadata):
    index = material['segment_index']
    _require(isinstance(metadata, dict) and set(metadata) == set(index))
    for sid, row in metadata.items():
        unit = material['units'][index[sid]['unit_id']]
        passage = index[sid]['unit_id'][len('passage:'):] if unit['kind'] == 'passage' else None
        _require(isinstance(row, dict) and row.get('person') == unit['person'] and row.get('unit_id') == passage)


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _ids(values):
    _require(isinstance(values, list) and bool(values) and all(_nonempty(s) for s in values))
    _require(len(values) == len(set(values)))
    return sorted(values)


def _cluster_key(row):
    _require(isinstance(row, dict))
    _require(all(_nonempty(row.get(key)) for key in ('code_path', 'cluster_name', 'definition')))
    return (row['code_path'], row['cluster_name'], row['definition'], tuple(_ids(row.get('segments'))))


def _cluster_topic_id(row):
    code, name, definition, members = _cluster_key(row)
    return 'cluster_' + fingerprint({'code_path': code, 'label': name,
        'definition': definition, 'member_segment_ids': list(members)})[:24]


def build_cluster_topics(material, payload):
    """Complete existing memberships, with explicit links to unweighted clusters."""
    membership = cluster_memberships(material, payload)
    links = {}
    for cluster in payload['clusters']:
        tid = _cluster_topic_id(cluster)
        links[tid] = {'module_id': 'clusterer', 'code_path': cluster['code_path'],
            'cluster_name': cluster['cluster_name'], 'member_segment_ids': sorted(cluster['segments']),
            'counting_basis': 'complete_cluster_membership',
            'qualitative_text': cluster['definition']}
    _require(set(links) == {topic['topic_id'] for topic in membership['topics']})
    return {**membership, 'source_links': links, 'qualitative_source': deepcopy(payload)}


def build_summary_topics(material, cluster_payload, summary_payload):
    """Reuse checked cluster membership; summary sentences receive no new labels.

    Every summary must match one complete original cluster by path, name,
    definition and segment set. A final free summary stays context only.
    """
    _completed(summary_payload)
    result = build_cluster_topics(material, cluster_payload)
    rows = summary_payload.get('cluster_summaries')
    _require(isinstance(rows, list))
    expected = {_cluster_key(row): _cluster_topic_id(row) for row in cluster_payload['clusters']}
    seen = set(); links = {}
    for row in rows:
        key = _cluster_key(row)
        _require(key in expected and key not in seen,
            'Clusterzusammenfassungen müssen eindeutig mit den vollständigen Originalclustern übereinstimmen.')
        _require(_nonempty(row.get('summary')))
        tid = expected[key]; seen.add(key)
        links[tid] = {**result['source_links'][tid], 'module_id': 'summarizer',
            'qualitative_text': row['summary'],
            'counting_note': 'Die Zahlen beschreiben die vollständige Clusterbasis, nicht jede freie Aussage der Zusammenfassung.'}
    _require(seen == set(expected), 'Eine vollständige Clusterzusammenfassung fehlt; keine vollständige Perspektivgrundlage.')
    _require(_nonempty(summary_payload.get('final_summary')))
    return {**result, 'source_links': links, 'qualitative_source': deepcopy(summary_payload),
        'source_fingerprint': fingerprint({'clusters': cluster_payload, 'summaries': summary_payload}),
        'source_cluster_fingerprint': fingerprint(cluster_payload),
        'unassigned_context': {'final_summary': summary_payload['final_summary'],
            'counting_note': 'Für diese freie Gesamtzusammenfassung ist keine aussagenspezifische Zuordnungsmatrix vorhanden.'}}


def build_swot_topics(material, payload):
    """Fixed analytical topics for full assignment across each actual code path.

    The current SWOT schema does not distinguish literal mention from inference.
    Therefore every finding is conservatively derived. No assignments are seeded
    from selected evidence. Identical duplicate findings are rejected explicitly.
    """
    validate_material(material)
    _completed(payload)
    _source_metadata(material, payload.get('segment_metadata'))
    expected = {}
    for sid, row in material['segment_index'].items():
        expected.setdefault(row['code_path'], set()).add(sid)
    groups = payload.get('swot')
    _require(isinstance(groups, dict) and set(groups) == set(expected),
             'SWOT-Codepfade müssen den vollständigen tatsächlichen Materialumfang abdecken.')
    if 'swot_unit_count' in payload:
        _require(type(payload['swot_unit_count']) is int and payload['swot_unit_count'] == len(groups))
    topics = []; links = {}
    for code in sorted(groups):
        group = groups[code]
        _require(isinstance(group, dict) and group.get('code_path') == code)
        if 'segment_count' in group:
            _require(type(group['segment_count']) is int and group['segment_count'] == len(expected[code]))
        scope = unit_ids_for_segments(material, expected[code])
        for dimension in DIMENSIONS:
            findings = group.get(dimension)
            _require(isinstance(findings, list))
            for finding in findings:
                _require(isinstance(finding, dict) and _nonempty(finding.get('thema')) and _nonempty(finding.get('analyse')))
                evidence = _ids(finding.get('segment_ids'))
                _require(set(evidence) <= expected[code], 'SWOT-Belege enthalten unbekannte oder codefremde Segment-IDs.')
                if 'zitate' in finding:
                    quotes = finding['zitate']
                    _require(isinstance(quotes, list) and len(quotes) == len(evidence))
                    seen_quotes = set()
                    for quote in quotes:
                        _require(isinstance(quote, dict) and isinstance(quote.get('segment_id'), str))
                        sid = quote['segment_id']
                        _require(sid in evidence and sid not in seen_quotes)
                        text = material['units'][material['segment_index'][sid]['unit_id']]['text']
                        _require(quote.get('text') == text, 'Gespeichertes SWOT-Zitat stimmt nicht mit dem Originalmaterial überein.')
                        seen_quotes.add(sid)
                definition = finding['thema'] + '\nAnalytischer Befund: ' + finding['analyse']
                tid = 'swot_' + fingerprint({'code_path': code, 'dimension': dimension,
                    'label': finding['thema'], 'definition': finding['analyse']})[:24]
                _require(tid not in links, 'Doppelter identischer SWOT-Befund: vor der Themenzuordnung eindeutig machen.')
                topics.append({'topic_id': tid, 'label': finding['thema'], 'definition': definition,
                    'inclusion': 'Material, das den bezeichneten analytischen Befund in dieser SWOT-Dimension stützt. '
                        'Eine ausdrücklich entgegenstehende Position getrennt als Gegenposition zuordnen.',
                    'exclusion': 'Bloße Zugehörigkeit zum Codepfad oder eine Erwähnung des Oberthemas reicht nicht aus. '
                        'Keine nicht geäußerten Überzeugungen aus fehlender Evidenz ableiten.',
                    'kind': 'derived', 'scope_unit_ids': scope})
                links[tid] = {'module_id': 'swot', 'code_path': code, 'dimension': dimension,
                    'thema': finding['thema'], 'qualitative_text': finding['analyse'],
                    'selected_evidence_segment_ids': evidence,
                    'counting_basis': 'full_assignment_required',
                    'counting_note': 'Gezählt wird stützende oder entgegenstehende Materialbasis, keine automatisch unterstellte wörtliche Nennung.'}
    # Reuse the shared schema validation without allocating a full empty matrix;
    # the assignment executor plans bounded blocks later.
    topics = validate_topics(material, topics)
    return {'schema_version': 1, 'basis_fingerprint': material['basis_fingerprint'],
        'source_fingerprint': fingerprint(payload), 'assignment_origin': 'requires_full_thematic_assignment',
        'topics': topics, 'assignments': None, 'source_links': dict(sorted(links.items())),
        'qualitative_source': deepcopy(payload), 'model_calls': 0,
        'methodological_note': 'Alle Materialeinheiten des jeweiligen Codepfads müssen gegen die festen Themen geprüft werden. '
            'Ausgewählte Beleg-IDs sind keine vollständigen Zuordnungen. SWOT-Befunde werden als analytische Ableitungen behandelt.'}
