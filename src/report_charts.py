"""Read-only chart data from completed run artifacts, never from live study inputs."""
import json
from collections import defaultdict


def chart_data(directory, modules):
    enabled = {m['id'] for m in modules if m.get('enabled', True)}
    def read(name):
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file(): return {}
        if path.stat().st_size > 20 * 1024 * 1024: return {}
        return json.loads(path.read_text(encoding='utf-8-sig'))
    result = {}
    if 'clusterer' in enabled:
        payload = read('clusters_output.json')
        metadata = payload.get('segment_metadata', {})
        texts = read('id_to_text.json')
        cells = defaultdict(set)
        evidence = {}
        for cluster in payload.get('clusters', []):
            for sid in cluster.get('segments', []):
                if not isinstance(sid, str): continue
                person = metadata.get(sid, {}).get('person')
                code = cluster.get('code_path')
                if not person or not code: continue
                cells[(person, code)].add(sid)
                text = texts.get(sid, '')
                if isinstance(text, dict): text = text.get('text', text.get('segment', ''))
                evidence[sid] = {'person': person, 'text': str(text), 'id': sid}
        if cells:
            result['person_categories'] = [{'person': person, 'code': code, 'ids': sorted(ids)}
                                            for (person, code), ids in sorted(cells.items())]
            result['evidence'] = evidence
    if 'review_queue' in enabled:
        queue = read('review_queue.json')
        result['review_cases'] = [{k: c.get(k) for k in ('case_id', 'case_status', 'person', 'text', 'human_codes', 'predicted_codes')}
                                  for c in queue.get('cases', [])]
    return result
