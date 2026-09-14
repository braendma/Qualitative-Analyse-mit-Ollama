"""Test harness: execute real module CLIs; replace only the model transport."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import types
import hashlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import clusterer_core
call_counts={}

def fake_chat(messages, **kwargs):
    block = os.environ.get('MOCK_BLOCK_SIGNAL')
    if block:
        from runtime_support import atomic_json
        import time
        atomic_json(Path(block), {'pid':os.getpid()})
        time.sleep(120)
    module=messages[0]['content'].split('\n',1)[0]
    text=messages[1]['content']
    logical_module='hierarchical_reduction' if module.startswith('Verdichte analytische Teilbefunde') else module
    call_counts[logical_module]=call_counts.get(logical_module,0)+1
    if os.environ.get('MOCK_TRACE_PATH'):
        with open(os.environ['MOCK_TRACE_PATH'],'a',encoding='utf-8') as trace:
            trace.write(json.dumps({'module':logical_module,'prompt_sha256':hashlib.sha256(json.dumps(messages,sort_keys=True).encode()).hexdigest()})+'\n')
    if os.environ.get('MOCK_FAIL_MODULE')==logical_module and call_counts[logical_module]>int(os.environ.get('MOCK_FAIL_AFTER','0')):
        raise RuntimeError('Simulated interruption')
    if module.startswith('Ordne jede angeforderte Zelle'):
        data, _ = json.JSONDecoder().raw_decode(text)
        return json.dumps({'assignments':[{**cell, 'status':'supported'} for cell in data['cells']]})
    if module.startswith('Du interpretierst festgelegte qualitative Themen'):
        data=json.loads(text)
        return json.dumps({'topic_id':data['topic']['topic_id'], 'interpretation':'Häufigkeitsinformierte synthetische Einordnung.',
                           'counterpositions':'Seltene Gegenpositionen bleiben relevant.', 'limitations':'Keine menschliche Bestätigung.'})
    if module.startswith('Codiere die gesamte Passage'):
        data=json.loads(text)
        codes=['A > B > C > '+code for needle,code in [('gut','positiv'),('schlecht','negativ')] if needle in data['segment']]
        return json.dumps({'unit_id':data['unit_id'],'predicted_codes':codes,'assignment_status':'assigned','confidence':'mittel','begruendung':'Beleg vorhanden'})
    if module.startswith('Verdichte analytische Teilbefunde'):
        data=json.loads(text)
        return json.dumps({'summary':'Belegte Teilanalyse einschließlich Gegenbelegen.'})
    if module in ('cluster_summary','category_summary'):
        return 'Belegte synthetische Zusammenfassung.'
    data=json.loads(text)
    if module=='cluster_analysis':
        result={'clusters':[{'cluster_name':'Test','definition':'Testcluster','segments':[s['id'] for s in data]}]}
    elif module=='code_verification':
        result={**data,'verification':'bestätigt','confidence':'mittel','begruendung':'Beleg vorhanden','alternative_codes':[]}
    elif module=='blind_coding':
        result={'segment_id':data['segment_id'],'predicted_code': 'A > B > C > '+('positiv' if 'gut' in data['segment'] else 'negativ'),
                'confidence':'mittel','begruendung':'Beleg vorhanden','alternative_codes':[]}
        if os.environ.get('MOCK_BLIND_CODE'):
            result['predicted_code'] = os.environ['MOCK_BLIND_CODE']
    elif module=='swot_analysis':
        ids=[s['id'] for c in data['clusters'] for s in c['segments']]
        result={d:[] for d in ('Stärken','Schwächen','Chancen','Risiken')}
        result['Stärken']=[{'thema':'Testthema','analyse':'Beleg vorhanden','segment_ids':ids}]
        result['Schwächen']=[{'thema':'Testgrenze','analyse':'Gegenläufiger Beleg','segment_ids':ids}]
    elif module=='meta_swot':
        result={'cluster':[{'thema':'Gemeinsam','verdichtung':'Testmuster','finding_ids':[f['finding_id'] for f in data]}]}
    elif module=='person_analysis':
        result={'zentrale_themen':[{'thema':'Testthema','verdichtung':'Test','segment_ids':[s['id'] for s in data['segments']]}],
                'perspektiven':[],'spannungsfelder':[],'kontrastierende_aspekte':[],'gesamtverdichtung':'Test'}
    elif module=='person_comparison':
        people=[p['person'] for p in data['personen']]
        result={'gemeinsame_muster':[{'thema':'Test','verdichtung':'Test','personen':people}],
                'zentrale_unterschiede':[],'typen':[], 'nicht_zugeordnete_personen':[], 'gesamtvergleich':'Test'}
    elif module=='contrast_analysis':
        result={'dominante_muster':[],'negativfaelle':[{'person':'P1','bezugs_muster':'Test','abweichung':'Gegenbeleg','begruendung':'Test'}],
                'spannungen_zwischen_typen':[],'relativierungen':[],'gesamteinordnung':'Test'}
    elif module=='relation_analysis':
        result={'beziehungen':[{'pair_id':p['pair_id'],'thema':'Test','beziehungstyp':'tritt_gemeinsam_auf','beschreibung':'Test',
                              'segment_ids_a':[p['segmente_a'][0]['id']],'segment_ids_b':[p['segmente_b'][0]['id']]} for p in data['kandidaten']],
                'gesamteinordnung':'Test'}
    elif module=='ambiguity_analysis':
        result={'ambivalenzen':[],'gesamteinordnung':'Keine Ambivalenz im Test.'}
    elif module=='evidence_audit':
        result={'zuordnungen':[{'audit_id':a['audit_id'],'gegenbeleg_ids':[c['counter_id'] for c in data['moegliche_gegenbelege']], 'einordnung':'Testgegenbeleg'} for a in data['audit_befunde']]}
    elif module=='overall_synthesis':
        result={'kernergebnisse':[{'thema':'Test','verdichtung':'Belegte Synthese','quellen':[data['verfuegbare_analytische_quellen'][0]]}],
                'uebergreifende_muster':[],'spannungen_und_relativierungen':[],'methodische_einordnung':['Test'], 'gesamtsynthese':'Test'}
    else:
        raise AssertionError(f'Unexpected test call: {module}')
    return json.dumps(result,ensure_ascii=False)

if os.environ.get('MOCK_RUNTIME_EVIDENCE') == '1':
    # Keep the real request/receipt layer while replacing only model I/O.
    import ollama_capacity
    def fake_metadata(endpoint, **kwargs):
        return {'models':[{'name':os.environ.get('MOCK_MODEL_NAME','mock:latest'), 'digest':os.environ.get('MOCK_MODEL_DIGEST','a'*64),
                           'context_length':32768}]}
    ollama_capacity.metadata = fake_metadata
    class ReceiptBackend:
        def chat(self, **request):
            return {'model':request['model'], 'message':{'content':fake_chat(request['messages'])}}
    clusterer_core.ollama = types.SimpleNamespace(Client=lambda **kwargs:ReceiptBackend())
else:
    clusterer_core.ollama_chat=fake_chat
original_run=subprocess.run

if os.environ.get('MOCK_RUNTIME_TRACE'):
    import managed_ollama
    class TraceManaged:
        def __init__(self,*args):self.active=False
        def start(self):
            self.active=True;os.environ[managed_ollama.HOST_ENV]='http://127.0.0.1:12345'
            with open(os.environ['MOCK_RUNTIME_TRACE'],'a') as trace:trace.write('start\n')
            return {'managed':True,'parallel_workers':2,'host':'http://127.0.0.1:12345'}
        def close(self):
            os.environ.pop(managed_ollama.HOST_ENV,None)
            if self.active:
                with open(os.environ['MOCK_RUNTIME_TRACE'],'a') as trace:trace.write('close\n')
            self.active=False
    managed_ollama.ManagedOllama=TraceManaged
def execute(command, **kwargs):
    if len(command)>1 and str(command[1]).endswith('.py'):
        if os.environ.get('MOCK_RUNTIME_TRACE'):
            with open(os.environ['MOCK_RUNTIME_TRACE'],'a') as trace:
                trace.write(Path(command[1]).stem+':'+str(bool(kwargs.get('env',{}).get('QUALITATIVE_MANAGED_OLLAMA_HOST')))+'\n')
        old_cwd=Path.cwd()
        old_argv=sys.argv
        old_env=dict(os.environ)
        try:
            if 'env' in kwargs:
                os.environ.clear()
                os.environ.update(kwargs['env'])
            os.chdir(kwargs['cwd'])
            sys.argv=command[1:]
            try:
                runpy.run_path(command[1],run_name='__main__')
            except SystemExit as exc:
                return types.SimpleNamespace(returncode=exc.code if type(exc.code) is int else 0 if exc.code is None else 1)
            return types.SimpleNamespace(returncode=0)
        finally:
            os.chdir(old_cwd)
            sys.argv=old_argv
            os.environ.clear()
            os.environ.update(old_env)
    return original_run(command,**kwargs)

subprocess.run=execute
import diagnostic_series
diagnostic_series._runner_command=lambda:[sys.executable,str(ROOT/'tests/mock_pipeline.py')]
if os.environ.get('MOCK_PAUSE_AFTER_FIRST_REPETITION') == '1':
    original_series_execute=diagnostic_series._execute
    def pause_after_repetition(command,directory,log,env):
        result=original_series_execute(command,directory,log,env)
        if os.environ.get('WORKFLOW_MODULE') in ('stability','sensitivity') and os.environ.get('WORKFLOW_PAUSE_FILE'):
            Path(os.environ['WORKFLOW_PAUSE_FILE']).touch()
        return result
    diagnostic_series._execute=pause_after_repetition
runpy.run_path(str(ROOT/'src/00_WORKFLOW_RUNNER.py'),run_name='__main__')
