"""Bounded cross-source comparisons; all original findings remain in the registry."""
import json
from collections import defaultdict, deque
from runtime_support import PartCheckpoint, fingerprint
from progress_events import update_progress
from summary_reduction import reduce_prompt
from parallel_items import completed_items


def compare_blocks(findings, prompt, params, compare, summarize):
    limit=int(params.get('num_ctx',16384)); answer=int(params.get('max_tokens',6000))
    def fits(values):
        s,u=prompt(values)
        return len((s+u).encode('utf-8'))+answer+1024 <= limit
    if not fits([]):raise ValueError('Feste Meta-SWOT-Anweisung überschreitet das Kontextfenster.')
    groups=defaultdict(deque)
    for finding in findings:groups[finding['source_id']].append(finding)
    ordered=[]
    while any(groups.values()):
        for group in groups.values():
            if group:ordered.append(group.popleft())
    blocks=[];current=[];reductions={}
    for original in ordered:
        finding=original
        if not fits([finding]):
            from_system,_=prompt([])
            source=json.dumps(original,ensure_ascii=False,indent=2)
            summary=reduce_prompt(from_system,source,params,summarize,target_bytes=1000)
            finding={'finding_id':original['finding_id'],'source_id':original['source_id'],'analyse':summary}
            reductions[finding['finding_id']]={'source_sha256':fingerprint(original),'summary':summary}
            if not fits([finding]):raise ValueError('Einzelner Meta-SWOT-Befund passt nach Verdichtung nicht; keine Kürzung.')
        if current and (len(current)>=12 or not fits(current+[finding])):
            blocks.append(current);current=[]
        current.append(finding)
    if current:blocks.append(current)
    source_id=fingerprint(findings)
    results=[None]*len(blocks)
    update_progress(detail_completed=0,detail_total=len(blocks))
    def compute(item):
        index,block=item
        system,user=prompt(block)
        # Validate against this block only; IDs from another block are not evidence.
        return PartCheckpoint('meta_swot_blocks',params).run(
            [source_id,index],{'system':system,'user':user},
            lambda: compare(system,user,block))
    # Honor the configured worker count; shared provider/queue bounds remain active.
    workers=min(4,int(params.get('parallel_workers',1)))
    for done,(index,value) in enumerate(completed_items(list(enumerate(blocks)),compute,workers),1):
        results[index]=value
        update_progress(detail_completed=done,detail_total=len(blocks))
    clusters=[cluster for result in results for cluster in result]
    return clusters,{'parts':len(blocks),'finding_ids':[f['finding_id'] for f in ordered],
        'reduced_findings':reductions,'source_sha256':fingerprint(findings),
        'method':'Quellenweise durchmischte Teilvergleiche; Union der validierten Muster. '
                 'Keine zusätzliche globale Zusammenführung über Blockgrenzen. '
                 'Ähnliche Befunde in verschiedenen Blöcken können unverbunden bleiben.'}
