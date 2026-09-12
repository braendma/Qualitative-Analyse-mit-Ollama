"""Resolve saved reduction references without inventing statement-level evidence."""
import re

SEGMENT_FIELDS = {'segment_ids', 'segment_ids_a', 'segment_ids_b', 'segments', 'segment_id'}
SOURCE_NOTE = ('Diese Analysen und Textstellen gehören zum Eingabematerial einer Zwischenzusammenfassung. '
               'Sie sind keine automatisch bestätigten Belege für jede Aussage der Gesamtsynthese. '
               'Die inhaltliche Zuordnung muss am Original geprüft werden.')


def source_details(payload):
    reduction = payload.get('hierarchical_reduction') or {}
    nodes, leaves = reduction.get('nodes', {}), reduction.get('leaves', {})
    cited = []
    for key in ('kernergebnisse', 'uebergreifende_muster', 'spannungen_und_relativierungen'):
        for entry in payload.get(key, []):
            for rid in entry.get('quellen', []):
                if rid not in cited:
                    cited.append(rid)
    result = {}
    for index, rid in enumerate(cited, 1):
        labels, segments, visited, missing = set(), set(), set(), set()
        todo = [(rid, frozenset())]
        def collect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in SEGMENT_FIELDS:
                        values = item if isinstance(item, list) else [item]
                        segments.update(x for x in values if isinstance(x, str))
                    elif isinstance(item, (dict, list)):
                        collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
        while todo:
            current, ancestors = todo.pop()
            if current in ancestors:
                missing.add(current)
                continue
            if current in visited:
                continue
            visited.add(current)
            if current in nodes:
                node = nodes[current]
                todo.extend((x, ancestors | {current}) for x in node.get('input_ids', []) if isinstance(x, str))
                # Labels remain useful even if an old ledger lacks a leaf.
                labels.update(x for x in node.get('source_labels', []) if isinstance(x, str))
            elif current in leaves:
                leaf = leaves[current]
                if isinstance(leaf.get('source'), str):
                    labels.add(leaf['source'])
                collect(leaf.get('content'))
            elif current in payload.get('source_labels', []):
                labels.add(current)
            else:
                missing.add(current)
        result[rid] = {'title': 'Quellengruppe ' + str(index), 'labels': sorted(labels),
                       'summary': str(nodes.get(rid, {}).get('text', '')),
                       'segment_ids': sorted(segments), 'unresolved': bool(missing),
                       'note': SOURCE_NOTE}
    return result


def readable_source_line(ids, details):
    labels = sorted({label for rid in ids for label in details.get(rid, {}).get('labels', [])})
    names = ', '.join(labels) or 'Herkunft nicht vollständig auflösbar'
    refs = ', '.join('`' + str(rid).replace('`', '') + '`' for rid in ids)
    return f'**Grundlage aus vorherigen Analysen:** {names}\n\n**Herkunftsdetails:** {refs}\n\n'


def clarify_source_lines(markdown, details):
    # Also upgrades old saved reports when exported again; analysis artifacts stay unchanged.
    pattern = r'^\*\*Analytische Quellen:\*\* (.+)$'
    def replace(match):
        ids = [item.strip().strip('`') for item in match[1].split(',')]
        return readable_source_line(ids, details).rstrip()
    return re.sub(pattern, replace, markdown, flags=re.M)
