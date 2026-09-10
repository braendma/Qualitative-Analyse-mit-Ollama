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
sys.path.insert(0,str(ROOT))
import clusterer_core
call_counts={}

def fake_chat(messages, **kwargs):
    module=messages[0]['content']
    text=messages[1]['content']
    logical_module='hierarchical_reduction' if module.startswith('Verdichte analytische Teilbefunde') else module
    call_counts[logical_module]=call_counts.get(logical_module,0)+1
    if os.environ.get('MOCK_TRACE_PATH'):
        with open(os.environ['MOCK_TRACE_PATH'],'a',encoding='utf-8') as trace:
            trace.write(json.dumps({'module':logical_module,'prompt_sha256':hashlib.sha256(json.dumps(messages,sort_keys=True).encode()).hexdigest()})+'\n')
    if os.environ.get('MOCK_FAIL_MODULE')==logical_module and call_counts[logical_module]>int(os.environ.get('MOCK_FAIL_AFTER','0')):
        raise RuntimeError('Simulated interruption')
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

clusterer_core.ollama_chat=fake_chat
original_run=subprocess.run
def execute(command, **kwargs):
    if len(command)>1 and str(command[1]).endswith('.py'):
        old_cwd=Path.cwd()
        old_argv=sys.argv
        try:
            os.chdir(kwargs['cwd'])
            sys.argv=command[1:]
            runpy.run_path(command[1],run_name='__main__')
            return types.SimpleNamespace(returncode=0)
        finally:
            os.chdir(old_cwd)
            sys.argv=old_argv
    return original_run(command,**kwargs)

subprocess.run=execute
runpy.run_path(str(ROOT/'00_WORKFLOW_RUNNER.py'),run_name='__main__')
