"""Offline review queue and validated, separately stored human decisions."""
from project_paths import DEFAULT_CONFIG
import argparse
from datetime import datetime
import html
import json
from pathlib import Path
import yaml
from coding_validation_common import load_segments, load_codebook, markdown_escape
from runtime_support import atomic_json, atomic_text, fingerprint


def build_queue(segments, codebook, agreement, verification, blind, audit):
    segs = {s.segment_id:s for s in segments}
    verify = {r['segment_id']:r for r in verification['results']}
    pred = {r['segment_id']:r for r in blind['results']}
    cases = []
    for case in agreement['cases']:
        ids = case.get('segment_ids') or [case['segment_id']]
        if any(sid not in segs or sid not in verify or sid not in pred for sid in ids):
            raise ValueError('Prüffall verweist auf fehlende Eingaben.')
        findings = [f for f in audit.get('befunde',[]) if set(ids)&set(f.get('segment_ids',[]))]
        human = case.get('human_codes', [case.get('human_code')])
        predicted = case.get('predicted_codes')
        if predicted is None: predicted = [case['predicted_code']] if case['predicted_code'] in {c.code for c in codebook} else []
        cid = ('unit:' + case['unit_id']) if case.get('unit_id') else ('row:' + case['segment_id'])
        reasons = list(dict.fromkeys(pred[s]['begruendung'] for s in ids))
        cases.append({'case_id':cid,'unit_id':case.get('unit_id'), 'segment_ids':ids,
            'person':segs[ids[0]].person,'text':segs[ids[0]].text,'human_codes':human,'predicted_codes':predicted,
            'missing_codes':case.get('missing_codes'),'additional_codes':case.get('additional_codes'),
            'case_status':case['case_status'],'needs_review':case['case_status']!='bestätigt',
            'model_reasons':reasons,'verification':[{'segment_id':s,**verify[s]} for s in ids],
            'related_audits':[{'audit_id':f['audit_id'],'thema':f.get('thema'), 'status':f.get('status'),
                'einordnung':f.get('relativierende_einordnung'),'gegenbelege':f.get('gegenbelege',[])} for f in findings]})
    content = {'schema_version':1,'codebook':[c.as_prompt_dict() for c in codebook],'cases':cases,
               'note':'Gegenbelege gehören zu analytischen Befunden; sie sind keine automatische Widerlegung einer einzelnen Codezuordnung.'}
    content['source_fingerprint'] = fingerprint({'segments':[s.__dict__ for s in segments], 'content':content,
                                                'agreement':agreement,'verification':verification,'blind':blind,'audit':audit})
    return content


def validate_decisions(queue, payload, *, draft=False):
    if not isinstance(payload,dict) or payload.get('schema_version')!=1 or payload.get('source_fingerprint')!=queue['source_fingerprint']:
        raise ValueError('Entscheidungen gehören nicht zu dieser Prüfliste/Version.')
    rows = payload.get('decisions')
    if not isinstance(rows,list): raise ValueError('decisions muss eine Liste sein.')
    cases = {c['case_id']:c for c in queue['cases']}
    codes = {c['code'] for c in queue['codebook']}
    seen, validated = set(), []
    for row in rows:
        if not isinstance(row,dict): raise ValueError('Entscheidung muss ein Objekt sein.')
        cid = row.get('case_id')
        if not isinstance(cid,str) or cid not in cases or cid in seen: raise ValueError('Unbekannter oder doppelter Prüffall.')
        seen.add(cid)
        decision = row.get('decision')
        if decision not in {'keep_human','accept_model','custom','unresolved'}: raise ValueError('Ungültige Entscheidung.')
        final = row.get('final_codes')
        if not isinstance(final,list) or any(not isinstance(c,str) or c not in codes for c in final) or len(set(final))!=len(final):
            raise ValueError('Entscheidung enthält ungültige Codes.')
        expected = cases[cid]['human_codes'] if decision=='keep_human' else cases[cid]['predicted_codes'] if decision=='accept_model' else [] if decision=='unresolved' else final
        if set(final)!=set(expected): raise ValueError('Entscheidungsart und finale Codes widersprechen sich.')
        note = row.get('note','')
        reviewer = row.get('reviewer','')
        if not isinstance(note,str) or not isinstance(reviewer,str): raise ValueError('Notiz und prüfende Person müssen Text sein.')
        if len(note)>12000 or len(reviewer)>200: raise ValueError('Notiz oder Name ist zu lang.')
        if not draft and decision!='unresolved' and (not note.strip() or not reviewer.strip()): raise ValueError('Abgeschlossene Entscheidungen benötigen Begründung und prüfende Person.')
        validated.append({'case_id':cid,'decision':decision,'final_codes':sorted(final),'note':note,'reviewer':reviewer})
    return {'schema_version':1,'source_fingerprint':queue['source_fingerprint'], 'validated_at':datetime.now().isoformat(),'decisions':validated}


def render_queue(queue):
    template = Path(__file__).with_name('review_template.html').read_text(encoding='utf-8')
    # Prevent script termination and injection through original interview text.
    data = json.dumps(queue,ensure_ascii=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    return template.replace('__QUEUE_JSON__',data)


from progress_events import track_module

@track_module
def main():
    p=argparse.ArgumentParser(description='Lokale Prüfliste; Entscheidungen verändern keine Originalcodierungen.')
    p.add_argument('--config',default=str(DEFAULT_CONFIG))
    p.add_argument('--input-csv')
    p.add_argument('--agreement-json',default='coding_agreement_v1.json')
    p.add_argument('--verify-json',default='code_verification_v1.json')
    p.add_argument('--blind-json',default='blind_coding_v1.json')
    p.add_argument('--audit-json',default='evidence_audit_v1.json')
    p.add_argument('--queue-json',default='review_queue.json')
    p.add_argument('--out-html',default='review_queue.html')
    p.add_argument('--out-md',default='review_queue.md')
    p.add_argument('--import-decisions')
    p.add_argument('--decisions-out',default='review_decisions.json')
    a=p.parse_args()
    def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if a.import_decisions:
        if Path(a.decisions_out).exists(): raise ValueError('Zieldatei existiert bereits; für jede Prüfversion einen neuen Namen wählen.')
        atomic_json(a.decisions_out, validate_decisions(read(a.queue_json),read(a.import_decisions)))
        return
    config_path=Path(a.config).resolve()
    config=yaml.safe_load(config_path.read_text(encoding='utf-8'))
    def resolve(value):
        path=Path(value)
        return path if path.is_absolute() else config_path.parent/path
    segments=load_segments(resolve(a.input_csv or config['paths']['input_csv']),config['columns'])
    codebook,_=load_codebook(resolve(config['paths']['category_system_csv']))
    queue=build_queue(segments,codebook,read(a.agreement_json),read(a.verify_json),read(a.blind_json),read(a.audit_json))
    atomic_json(a.queue_json,queue)
    atomic_text(a.out_html,render_queue(queue))
    md=['# Prüfliste strittiger Codierungen\n\n',f'Interaktiv lokal öffnen: [{Path(a.out_html).name}]({Path(a.out_html).name}). Entscheidungen separat exportieren und validieren.\n\n',queue['note']+'\n\n']
    for c in queue['cases']:
        if not c['needs_review']: continue
        md.extend([f"## {markdown_escape(c['case_id'])} — {c['case_status']}\n\n",
                   '> '+html.escape(c['text']).replace('\n','\n> ')+'\n\n',
                   f"Mensch: {', '.join(c['human_codes'])}\n\nModell: {', '.join(c['predicted_codes']) or 'keine Zuordnung'}\n\n",
                   '\n\n'.join(c['model_reasons'])+'\n\n'])
    atomic_text(a.out_md,''.join(md))


if __name__=='__main__': main()
