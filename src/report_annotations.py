"""Bind editable prose to typed model fields; quotes and data are never editable."""
import hashlib
import json
import re
from collections import defaultdict
from coverage_core import markdown_escape

NARRATIVE = {'interpretation', 'counterpositions', 'limitations', 'analyse', 'summary', 'verdichtung',
             'zusammenfassung', 'interpretation_text'}
PROTECTED = {'zitate', 'quotes', 'evidence', 'segment_metadata', 'source_links',
             'counting', 'assignments', 'segment_index', 'id_to_text'}
PROTECTED |= {'finding_registry', 'qualitative_source'}


def finding_identity(source, dimension, label, analysis, ids):
    """Content-bound identity, never the order-dependent S0001 counter alone."""
    if not all(isinstance(x, str) and x.strip() for x in (source, dimension, label, analysis)):
        return ''
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids): return ''
    identity = [source, dimension, label.strip(), analysis.strip(), sorted(set(ids))]
    return 'swot-finding:' + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def review_identity(payload, context, path, link):
    """Use explicit SWOT finding registries, not similarity or shared names."""
    item, parents = '', []
    if len(path) >= 4 and path[0] == 'swot':
        item = finding_identity(path[1], path[2], context.get('thema'), context.get('analyse'), context.get('segment_ids'))
    elif link.get('module_id') == 'swot':
        item = finding_identity(link.get('code_path'), link.get('dimension'), link.get('thema'), link.get('qualitative_text'), link.get('selected_evidence_segment_ids'))
    dimension = path[1] if len(path) >= 4 and path[0] == 'meta_swot' else link.get('dimension')
    if (len(path) >= 4 and path[0] == 'meta_swot') or link.get('module_id') == 'meta_swot':
        refs = link.get('finding_ids', context.get('finding_ids', [context['finding_id']] if 'finding_id' in context else []))
        registry = payload.get('finding_registry', {})
        for fid in refs:
            row = registry.get(fid, {})
            parent = finding_identity(row.get('source_id'), dimension, row.get('thema'), row.get('analyse'), row.get('segment_ids'))
            if parent: parents.append({'id': parent, 'reference': fid})
        if parents and len(parents) == len(refs):
            label = link.get('thema', context.get('thema'))
            text = link.get('qualitative_text', context.get('verdichtung'))
            item = 'meta-finding:' + hashlib.sha256(json.dumps([dimension, label, text, sorted(p['id'] for p in parents)], ensure_ascii=False).encode()).hexdigest()
    return {'item_id': item, 'parent_items': parents} if item or parents else {}


def editable_fields(markdown, payload, texts=None):
    """Fail closed on ambiguous text matches or embedded verbatim quotations.

    A generic Markdown paragraph is NOT an editing permission. It must match a
    named narrative field in the associated JSON artifact. No model calls.
    """
    texts = texts or {}
    perspective = payload.get('analysis_perspective', {})
    links = perspective.get('source_links', {})
    metadata = payload.get('segment_metadata', {})
    candidates = defaultdict(list)
    quoted = {v for v in texts.values() if isinstance(v, str) and v}

    def quotes(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ('zitate', 'quotes') and isinstance(value, list):
                    for q in value:
                        if isinstance(q, dict) and isinstance(q.get('text'), str):
                            quoted.add(q['text'])
                quotes(value)
        elif isinstance(node, list):
            for value in node: quotes(value)
    quotes(payload)

    def walk(node, path=(), inherited=None):
        if isinstance(node, list):
            for index, value in enumerate(node): walk(value, path+(index,), inherited)
        elif isinstance(node, dict):
            context = node if any(k in node for k in ('segment_ids', 'segments', 'zitate', 'topic_id', 'finding_ids', 'finding_id', 'segment_ids_a', 'segment_ids_b')) else inherited or {}
            for key, value in node.items():
                if key in PROTECTED: continue
                if key in NARRATIVE and isinstance(value, str) and value.strip():
                    if any(q.strip() and q in value for q in quoted): continue
                    link = links.get(context.get('topic_id'), {})
                    ids = link.get('selected_evidence_segment_ids', link.get('member_segment_ids', context.get('segment_ids', context.get('segments', context.get('segment_ids_a', []) + context.get('segment_ids_b', [])))))
                    if not isinstance(ids, list): ids = []
                    if not ids and ('finding_ids' in context or 'finding_id' in context):
                        refs = context.get('finding_ids', [context['finding_id']] if 'finding_id' in context else [])
                        ids = [sid for fid in refs for sid in payload.get('finding_registry', {}).get(fid, {}).get('segment_ids', [])]
                    stored = {q.get('segment_id'): q.get('text') for q in context.get('zitate', []) if isinstance(q, dict)}
                    evidence = []
                    for sid in dict.fromkeys(s for s in ids if isinstance(s, str)):
                        if sid in texts and sid in stored and texts[sid] != stored[sid]:
                            raise ValueError('Gespeichertes Zitat weicht von der Originaltext-Zuordnung ab.')
                        text = texts.get(sid, stored.get(sid, ''))
                        evidence.append({'id': sid, 'text': text if isinstance(text, str) else '',
                                         'person': metadata.get(sid, {}).get('person', '')})
                    entry = {'path': list(path+(key,)), 'original': value, 'label': key,
                             'topic_id': context.get('topic_id', ''), 'evidence': evidence}
                    entry.update(review_identity(payload, context, path, link))
                    entry['element_label'] = link.get('thema', context.get('thema', context.get('topic_id', key)))
                    related_topics = list(link.get('countercase_topic_ids', []))
                    if link.get('pattern_topic_id'): related_topics.append(link['pattern_topic_id'])
                    if related_topics: entry['related_topic_ids'] = sorted(set(related_topics))
                    if link.get('module_id') == 'ambiguity_analysis' and link.get('pair_id'):
                        entry['related_pair_id'] = link['pair_id']
                    if 'selected_evidence_segment_ids' not in link and 'member_segment_ids' in link:
                        entry['evidence_note'] = 'Vollständige Clusterbasis: Diese Zitate gehören zum Cluster, belegen aber nicht automatisch jede Aussage der Deutung.'
                    for rendered in {value, markdown_escape(value)}:
                        candidates[rendered].append(entry)
                elif isinstance(value, (dict, list)): walk(value, path+(key,), context)
    walk(payload)
    lines = markdown.splitlines()
    occurrences = defaultdict(list)
    fenced = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith('```'): fenced = not fenced; continue
        if fenced or re.match(r'^\s*(?:[>#|!]|[-*] |\*\*)', line): continue
        if line in candidates: occurrences[line].append(i)
    fields = {}
    for line, positions in occurrences.items():
        # Duplicates have no trustworthy paragraph-to-field identity.
        entries = candidates[line]
        if len(positions) != 1 or len(entries) != 1: continue
        index = positions[0]
        fields[str(index)] = {**entries[0], 'original_markdown': line,
                             'source_sha256': hashlib.sha256(json.dumps(entries[0], sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
    return fields


def load_fields(directory, module, markdown, local_file):
    args = module.get('args', [])
    if '--out-json' not in args: return {}
    path = local_file(directory, args[args.index('--out-json')+1])
    if path.stat().st_size > 20*1024*1024: raise ValueError('Berichtsquelle zu gross.')
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    map_flag = next((flag for flag in ('--id-to-text', '--idmap-json') if flag in args), None)
    name = args[args.index(map_flag)+1] if map_flag else 'id_to_text.json'
    idmap = local_file(directory, name)
    texts = json.loads(idmap.read_text(encoding='utf-8-sig')) if idmap.is_file() and idmap.stat().st_size <= 20*1024*1024 else {}
    fields = editable_fields(markdown, payload, texts)
    flags_path = local_file(directory, 'report_review_flags.json')
    if flags_path.is_file():
        flags = json.loads(flags_path.read_text(encoding='utf-8'))
        if flags.get('schema_version') != 1: raise ValueError('Unbekannte Pruefhinweise.')
        for flag in flags['flags']:
            if flag['module_id'] != module['id']: continue
            for field in fields.values():
                if field['topic_id'] == flag['topic_id'] and field['label'] == flag['field']:
                    if field['original'] != flag['original']: raise ValueError('Pruefhinweis passt nicht zum Originaltext.')
                    field['review_note'] = str(flag['note'])
    return fields
