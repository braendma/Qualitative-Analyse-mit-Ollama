"""Strict pure provenance replay for actual qualitative synthesis source graphs.

File/run and module/material contracts belong to the caller. This validates the
saved structural derivation, not semantic accuracy of summaries or final claims.
"""
from collections import Counter
import json
import math

from runtime_support import fingerprint
from overall_synthesis_core import project_synthesis_source


def _require(value, message='Synthese-Herkunft stimmt nicht vollständig mit den tatsächlichen Originalquellen überein.'):
    if not value:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _json(value):
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        _require(math.isfinite(value)); return
    if isinstance(value, list):
        for item in value: _json(item)
        return
    _require(isinstance(value, dict) and all(isinstance(key, str) for key in value))
    for item in value.values(): _json(item)


def _ids(value, *, nonempty=True):
    _require(isinstance(value, list) and (bool(value) or not nonempty) and all(_text(v) for v in value))
    _require(len(value) == len(set(value)))
    return value


def _resolve(value, path):
    _require(isinstance(path, list))
    for step in path:
        if isinstance(value, dict):
            _require(isinstance(step, str) and step in value, 'Syntheseblatt verweist auf einen unbekannten Originalschlüssel.')
        elif isinstance(value, list):
            _require(type(step) is int and 0 <= step < len(value), 'Syntheseblatt benötigt einen gültigen echten Listenindex.')
        else:
            _require(False, 'Syntheseblattpfad führt durch einen skalaren Originalwert.')
        value = value[step]
    return value


def _cover(value, paths, *, top=False):
    """Replay legal structural subdivisions, including empty/scalar leaves."""
    if () in paths:
        _require(len(paths) == 1, 'Syntheseblätter überlappen sich.')
        _require(not (top and isinstance(value, dict)), 'Top-Level-Quellobjekte werden im Core feldweise zerlegt.')
        return
    if top and isinstance(value, dict):
        # An empty top-level dictionary produces no leaves in reduce_sources.
        expected = set(value)
        _require({path[0] for path in paths if path} == expected)
        for key, item in value.items():
            child = {path[1:] for path in paths if path and path[0] == key}
            if isinstance(item, list) and item:
                _require(() not in child, 'Nichtleere Top-Level-Listen werden vom Core elementweise zerlegt.')
            _cover(item, child)
        return
    if isinstance(value, list) and value:
        _require({path[0] for path in paths if path} == set(range(len(value))))
        for index, item in enumerate(value):
            _cover(item, {path[1:] for path in paths if path and path[0] == index})
        return
    if isinstance(value, dict) and value:
        _require(any(isinstance(v, (dict, list)) for v in value.values()) and
                 not any(key in value for key in ('thema', 'verdichtung', 'analyse', 'beschreibung', 'aussage')),
                 'Ein atomarer analytischer Befund darf nicht strukturell zerlegt werden.')
        _require({path[0] for path in paths if path} == set(value))
        for key, item in value.items():
            _cover(item, {path[1:] for path in paths if path and path[0] == key})
        return
    _require(False, 'Leere Container und skalare Originalwerte benötigen ein vollständiges Syntheseblatt.')


def _findings(payload, allowed, *, reduced):
    entries = []
    for section in ('kernergebnisse', 'uebergreifende_muster', 'spannungen_und_relativierungen'):
        rows = payload.get(section)
        _require(isinstance(rows, list))
        fields = {'aussage', 'einordnung', 'quellen'} if section == 'spannungen_und_relativierungen' else {'thema', 'verdichtung', 'quellen'}
        for row in rows:
            _require(isinstance(row, dict) and set(row) == fields)
            _require(all(isinstance(row[key], str) for key in fields - {'quellen'}))
            if 'thema' in row: _require(_text(row['thema']))
            _require(set(_ids(row['quellen'])) <= allowed, 'Synthesebefund verweist nicht auf eine zulässige finale Quelle.')
        entries.extend(rows)
    _require(not reduced or bool(entries), 'Reduzierte Synthese benötigt mindestens einen gültigen finalen Quellenverweis.')
    _require(isinstance(payload.get('methodische_einordnung'), list) and all(_text(v) for v in payload['methodische_einordnung']))
    _require(payload.get('gesamtsynthese') == ' '.join(row['verdichtung'] for row in payload['kernergebnisse']),
             'Zusammengesetzte Gesamtsynthese stimmt nicht mit ihren ursprünglichen Kernergebnissen überein.')


def validate_synthesis_provenance(payload, source_payloads_by_label):
    """Return verified reference origins for the exact real source projection.

    No inference, I/O, or source mutation. Reference origins denote source
    material of a reduction; they are never statement-level quote evidence.
    """
    _json(payload); _json(source_payloads_by_label)
    _require(isinstance(payload, dict) and payload.get('processing_status', 'completed') == 'completed')
    _require(isinstance(source_payloads_by_label, dict) and bool(source_payloads_by_label))
    _require(all(_text(label) and label == label.strip() for label in source_payloads_by_label))
    for source in source_payloads_by_label.values():
        if isinstance(source, dict):
            _require(source.get('processing_status', 'completed') == 'completed')
    labels = _ids(payload.get('source_labels'))
    _require(set(labels) == set(source_payloads_by_label))
    dates = payload.get('source_created_at')
    expected_dates = {label: source.get('created_at') if isinstance(source, dict) else None for label, source in source_payloads_by_label.items()}
    _require(isinstance(dates, dict) and fingerprint(dates) == fingerprint(expected_dates))
    projected = {label: project_synthesis_source(source) for label, source in source_payloads_by_label.items()}
    projected_hashes = {label: fingerprint(value) for label, value in projected.items()}
    if 'source_projection_fingerprints' in payload:
        hashes = payload['source_projection_fingerprints']
        _require(isinstance(hashes, dict) and fingerprint(hashes) == fingerprint(projected_hashes),
                 'Gespeicherter Projektionsnachweis passt nicht zu den tatsächlichen Synthesequellen.')
    ledger = payload.get('hierarchical_reduction')
    _require(isinstance(ledger, dict) and type(ledger.get('used')) is bool)
    references = {}
    if not ledger['used']:
        expected = {'used': False, 'model_calls': 0, 'levels': 0, 'nodes': {}, 'leaves': {}}
        _require(fingerprint(ledger) == fingerprint(expected), 'Unreduzierte Synthese besitzt widersprüchliche Reduktionsangaben.')
        for label in sorted(labels):
            references[label] = {'source_labels': [label], 'leaf_ids': [],
                'source_paths': [{'source': label, 'path': [], 'content_fingerprint': fingerprint(projected[label])}]}
    else:
        _require(set(ledger) == {'used', 'model_calls', 'reused_batches', 'levels', 'leaves', 'nodes', 'final_node_ids'})
        leaves = ledger['leaves']; nodes = ledger['nodes']
        _require(isinstance(leaves, dict) and bool(leaves) and isinstance(nodes, dict) and bool(nodes))
        levels = ledger['levels']
        _require(type(levels) is int and 1 <= levels <= len(nodes))
        _require(type(ledger['model_calls']) is int and len(nodes) <= ledger['model_calls'] <= 2 * len(nodes))
        _require(type(ledger['reused_batches']) is int and 0 <= ledger['reused_batches'] <= len(nodes))
        finals = _ids(ledger['final_node_ids'])
        by_source = {label: set() for label in labels}
        for lid, leaf in leaves.items():
            _require(isinstance(leaf, dict) and set(leaf) == {'source', 'path', 'content'})
            label = leaf['source']; path = leaf['path']
            _require(isinstance(label, str) and label in projected)
            actual = _resolve(projected[label], path)
            _require(fingerprint(actual) == fingerprint(leaf['content']), 'Syntheseblattinhalt wurde gegenüber der tatsächlichen Originalquelle verändert.')
            _require(lid == 'L' + fingerprint([label, path, leaf['content']])[:20], 'Syntheseblatthash ist ungültig.')
            key = tuple(path)
            _require(key not in by_source[label], 'Doppeltes Syntheseblatt.')
            by_source[label].add(key)
        for label in labels:
            _cover(projected[label], by_source[label], top=True)
        input_levels = {lid: 0 for lid in leaves}; sources = {lid: {row['source']} for lid, row in leaves.items()}
        descendants = {lid: {lid} for lid in leaves}; parents = Counter()
        for nid, node in nodes.items():
            _require(isinstance(node, dict) and set(node) == {'text', 'input_ids', 'source_labels', 'level'})
            _require(_text(node['text']) and type(node['level']) is int and 1 <= node['level'] <= levels)
            _ids(node['input_ids']); _ids(node['source_labels'])
            _require(nid == 'N' + fingerprint([node['level'] - 1, {'text': node['text'], 'input_ids': node['input_ids']}])[:20],
                     'Syntheseknotenhash stimmt nicht mit Text, Reihenfolge und Reduktionsstufe überein.')
            _require(nid not in leaves)
        for nid, node in sorted(nodes.items(), key=lambda item: (item[1]['level'], item[0])):
            children = node['input_ids']
            _require(all(child in input_levels and input_levels[child] == node['level'] - 1 for child in children),
                     'Syntheseknoten benötigt echte Eingänge der unmittelbar vorherigen Stufe; Zyklen und fehlende Eingänge sind unzulässig.')
            union = set().union(*(sources[child] for child in children))
            _require(node['source_labels'] == sorted(union), 'Syntheseknoten enthält eine falsche transitive Quellenunion.')
            input_levels[nid] = node['level']; sources[nid] = union
            descendants[nid] = set().union(*(descendants[child] for child in children))
            parents.update(children)
        _require(max(node['level'] for node in nodes.values()) == levels)
        _require(set(finals) == {nid for nid, node in nodes.items() if node['level'] == levels}, 'Finale Synthesewurzeln sind unvollständig oder stammen aus einer anderen Stufe.')
        _require(all(parents[rid] == (0 if rid in finals else 1) for rid in set(leaves) | set(nodes)),
                 'Synthesegraph enthält überlappende Elternschaft, verwaiste Knoten oder unverbundene Blätter.')
        for rid in finals:
            leaf_ids = sorted(descendants[rid])
            paths = [{'source': leaves[lid]['source'], 'path': list(leaves[lid]['path']),
                      'content_fingerprint': fingerprint(leaves[lid]['content'])} for lid in leaf_ids]
            paths.sort(key=lambda item: (item['source'], json.dumps(item['path'], ensure_ascii=False)))
            references[rid] = {'source_labels': sorted(sources[rid]), 'leaf_ids': leaf_ids, 'source_paths': paths}
    _findings(payload, set(references), reduced=ledger['used'])
    result = {'schema_version': 1, 'reduction_used': ledger['used'], 'source_labels': sorted(labels),
        'projected_source_fingerprints': dict(sorted(projected_hashes.items())),
        'projected_sources_fingerprint': fingerprint(projected), 'references': dict(sorted(references.items())),
        'methodological_note': 'Geprüfte Quellenpfade beschreiben das Eingabematerial analytischer Teilverdichtungen, keine bestätigten Zitate oder semantische Wahrheit einzelner Syntheseaussagen.'}
    result['provenance_fingerprint'] = fingerprint(result)
    return result
