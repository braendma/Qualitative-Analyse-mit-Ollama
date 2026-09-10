import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import clusterer_core as cluster
from coding_validation_common import Segment, CodebookEntry, load_segments, code_hierarchy
from code_verification_core import verify_segments
from blind_coding_core import blind_code_segments
from coding_validation_common import MockLLM
from evidence_audit_core import normalize_mappings
from person_analysis_core import normalize_person_analysis, build_person_payloads
from overall_synthesis_core import normalize_overall_synthesis
from relation_analysis_core import build_candidate_pairs
from coding_agreement_core import calculate_agreement
from runtime_support import Checkpoint
from llm_client import LLMTransportError, LLMResponseError, ContextBudgetError
import pandas as pd

def load_runner():
    spec=importlib.util.spec_from_file_location('workflow',ROOT/'00_WORKFLOW_RUNNER.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SafetyTests(unittest.TestCase):
    def test_synthesis_projection_keeps_findings_status_and_reference_ids(self):
        from overall_synthesis_core import project_synthesis_source
        source={'befunde':[{'thema':'Test','status':'quellenspezifisch','gegenbeleg_count':1,
                 'segment_ids':['ID1'],'finding_ids':['F1'],'source_id':'source-A','belegbeispiele':[{'text':'repeated quotation'}]}],
                'finding_registry':{'F1':{'text':'repeated quotation'}}}
        projected=project_synthesis_source(source)
        self.assertEqual(projected['befunde'][0]['segment_ids'],['ID1'])
        self.assertEqual(projected['befunde'][0]['source_id'],'source-A')
        self.assertEqual(projected['befunde'][0]['gegenbeleg_count'],1)
        self.assertEqual(projected['befunde'][0]['status'],'quellenspezifisch')
        self.assertNotIn('repeated quotation',json.dumps(projected))
    def test_response_schema_keys_match_existing_prompts(self):
        import yaml
        from response_schemas import SCHEMAS
        prompts=yaml.safe_load((ROOT/'config_v2.yaml').read_text(encoding='utf-8'))['prompts']
        self.assertNotIn('darf ein Audit-Befund fehlen',prompts['evidence_audit']['user'])
        self.assertIn('genau einmal',prompts['evidence_audit']['user'])
        for module,schema in SCHEMAS.items():
            if module in {'clusterer','swot','meta_swot'}:
                continue
            prompt=prompts[module]['user']
            for key in schema['properties']:
                self.assertIn('"'+key+'"',prompt,f'{module}: {key}')

    def test_audit_repair_receives_missing_befund_context(self):
        import evidence_audit_core as audit
        from runtime_support import atomic_json
        calls=[]
        def fake(messages,**kwargs):
            calls.append(messages)
            if len(calls)==1:
                return '{"zuordnungen":[]}'
            self.assertIn('EVA0001',messages[1]['content'])
            self.assertIn('Gegenbefund',messages[1]['content'])
            return '{"zuordnungen":[{"audit_id":"EVA0001","gegenbeleg_ids":[],"einordnung":"Kein passender Gegenbeleg"}]}'
        with tempfile.TemporaryDirectory() as tmp,patch.object(audit,'ollama_chat',side_effect=fake):
            folder=Path(tmp)
            finding={'source_id':'A','segment_ids':['P1#SEG0'],'thema':'Test','analyse':'Test'}
            files={'swot':{},'meta':{'finding_registry':{'F1':finding},'meta_swot':{'Stärken':{'einzelbefunde':[{'finding_id':'F1','thema':'Test'}]}}},
                   'contrast':{'negativfaelle':[{'person':'P1','abweichung':'Gegenbefund'}]},'ambiguity':{},'map':{'P1#SEG0':'Beleg'}}
            for name,data in files.items(): atomic_json(folder/(name+'.json'),data)
            _,output=audit.build_evidence_audit(*[str(folder/(name+'.json')) for name in files],
                {'model':'mock','temperature':0,'max_tokens':1000}, {'evidence_audit':{'system':'Test','user':'{data}'}},{})
            self.assertEqual(len(calls),2)
            self.assertEqual(output['befunde'][0]['gegenbeleg_count'],0)
            self.assertEqual(output['processing_status'],'completed')
    def test_batches_preserve_all_items_and_budget(self):
        from batching import bounded_batches
        items=[{'id':i,'text':'x'*40} for i in range(20)]
        batches=list(bounded_batches(items,lambda batch:('sys',json.dumps(batch)),
                                     {'num_ctx':800,'max_tokens':100,'batch_items':3}))
        self.assertEqual([x for batch,_,_ in batches for x in batch],items)
        self.assertTrue(all(len(batch)<=3 for batch,_,_ in batches))
        with self.assertRaises(ContextBudgetError):
            list(bounded_batches([{'text':'x'*1000}],lambda batch:('sys',json.dumps(batch)),{'num_ctx':300}))

    def test_schema_is_sent_locally_but_not_to_cloud(self):
        from llm_client import request_chat
        class Backend:
            def __init__(self): self.requests=[]; self.options=[]
            def Client(self,**kwargs): self.options.append(kwargs); return self
            def chat(self,**kwargs): self.requests.append(kwargs); return {'message':{'content':'{}'}}
        backend=Backend()
        request={'model':'mock','messages':[],'options':{'num_predict':100}}
        request_chat(backend,request,{'response_schema':{'type':'object'}})
        self.assertEqual(backend.requests[0]['format'],{'type':'object'})
        with patch.dict(os.environ,{'TEST_CLOUD_KEY':'synthetic-key'}):
            request_chat(backend,{'model':'mock','messages':[],'options':{'num_predict':100}},
                         {'host':'https://ollama.com','api_key_env':'TEST_CLOUD_KEY','response_schema':{'type':'object'}})
        self.assertNotIn('format',backend.requests[1])
        self.assertNotIn('num_ctx',backend.requests[1]['options'])
        self.assertEqual(backend.options[1]['host'],'https://ollama.com')

    def test_synthetic_demo_covers_hierarchies_and_multiple_coding(self):
        from coding_validation_common import load_codebook
        spec=importlib.util.spec_from_file_location('demo_generator',ROOT/'tests/generate_demo.py')
        generator=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory() as tmp:
            generator.ROOT=Path(tmp)
            generator.generate()
            segs=load_segments(Path(tmp)/'maxqda_export.csv',{'unit_id':'PassageID'})
            _,book=load_codebook(Path(tmp)/'Kategoriesystem.csv')
        self.assertEqual(len(segs),50)
        self.assertEqual(len({s.unit_id for s in segs}),43)
        self.assertTrue(all(s.segment_id.startswith('SYN-') and s.human_code in book for s in segs))
        self.assertEqual({len(c.split(' > ')) for c in book},{1,2,3,4})

    def test_transport_failure_does_not_become_empty_success(self):
        class Backend:
            def chat(self,**kwargs): raise ConnectionError('secret transport details')
        with patch.object(cluster,'ollama',Backend()),self.assertRaises(LLMTransportError) as ctx:
            cluster.ollama_chat([], 'mock', 0, 100, settings={'max_attempts':1})
        self.assertNotIn('secret',str(ctx.exception))

    def test_context_guard_prevents_request(self):
        with patch.object(cluster,'ollama') as backend,self.assertRaises(ContextBudgetError):
            cluster.ollama_chat([{'role':'user','content':'x'*1000}], 'mock',0,100,settings={'num_ctx':256})
        backend.Client.assert_not_called()

    def test_audit_requires_all_ids_and_known_counters(self):
        for payload in (None, {}, {'zuordnungen':[]}, {'zuordnungen':[{'audit_id':'A','gegenbeleg_ids':['invented']}]}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                normalize_mappings(payload,{'A'},{'C':{}})
        ok=normalize_mappings({'zuordnungen':[{'audit_id':'A','gegenbeleg_ids':[]}]},{'A'},{'C':{}})
        self.assertEqual(ok['A']['gegenbeleg_ids'],[])

    def test_no_evidence_no_empirical_claim_or_free_summary(self):
        p=normalize_person_analysis({'zentrale_themen':[{'thema':'Invented','segment_ids':['fake']}],
                                     'gesamtverdichtung':'Invented summary'}, {'id1'},{'id1':'Original'})
        self.assertEqual(p['zentrale_themen'],[])
        self.assertEqual(p['gesamtverdichtung'],'')
        p=normalize_overall_synthesis({'kernergebnisse':[{'thema':'Invented','quellen':['fake']}],
                                      'gesamtsynthese':'Invented summary'},['source'])
        self.assertEqual(p['kernergebnisse'],[])
        self.assertEqual(p['gesamtsynthese'],'')

    def test_external_ids_and_raw_text_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input.csv'
            pd.DataFrame([{'Dokumentname':'P1','Code':'A > B','Segment':'a  b\nc','ID':'external'}]).to_csv(path,sep=';',index=False)
            s=load_segments(path)[0]
            self.assertEqual(s.segment_id,'external')
            self.assertEqual(s.text,'a  b\nc')
            mapping=Path(tmp)/'mapping.json'
            with self.assertRaises(FileNotFoundError): load_segments(path,id_to_text_path=mapping)
            mapping.write_text('{}')
            with self.assertRaises(ValueError): load_segments(path,id_to_text_path=mapping)

    def test_hierarchy_and_external_ids_survive_clustering_and_people(self):
        frame=pd.DataFrame([{'Dokumentname':'P1','Code':'A > B > C > positiv','Segment':'yes','ID':'x'},
                            {'Dokumentname':'P1','Code':'A > B > C > negativ','Segment':'no','ID':'y'},
                            {'Dokumentname':'P2','Code':'A > B','Segment':'short','ID':'z'}])
        def fake(system,user,params):
            return json.dumps({'clusters':[{'cluster_name':'same','definition':'Test','segments':[x['id'] for x in json.loads(user)]}]})
        with tempfile.TemporaryDirectory() as tmp,patch.object(cluster,'llm_cluster',fake),patch.object(cluster,'plot_clusters',return_value=None):
            _,data=cluster.run_clustering(frame,{'model':'mock','temperature':0,'max_tokens':100},
                {'cluster_analysis':{'system':'test','user':'{segments}'},'json_schema':'{}'}, {},
                plots_dir=tmp,id_to_text_path=str(Path(tmp)/'map.json'))
            self.assertEqual(len(data['clusters']),3)
            self.assertEqual({c['code_path'] for c in data['clusters']},set(frame.Code))
            people=build_person_payloads(data['clusters'],{'x':'yes','y':'no','z':'short'},{},data['segment_metadata'])
            self.assertEqual(set(people),{'P1','P2'})
            self.assertEqual(len(people['P1']['segments']),2)

    def test_invalid_cluster_response_fails(self):
        frame=pd.DataFrame([{'Dokumentname':'P1','Code':'A > B','Segment':'x'}])
        with tempfile.TemporaryDirectory() as tmp,patch.object(cluster,'llm_cluster',return_value='bad'),patch.object(cluster,'llm_self_repair',return_value='bad'):
            with self.assertRaises(LLMResponseError):
                cluster.run_clustering(frame,{'model':'mock','temperature':0,'max_tokens':100},
                    {'cluster_analysis':{'system':'test','user':'{segments}'},'self_repair':{'system':'fix','user':'{clusters}'},'json_schema':'{}'}, {},plots_dir=tmp)

    def test_person_paired_sampling(self):
        units={'A':{'personen':['P1','P2'],'segmente':[{'id':'P1#SEG0'},{'id':'P2#SEG1'}],'cluster':[]},
               'B':{'personen':['P1','P2'],'segmente':[{'id':'P2#SEG2'},{'id':'P1#SEG3'}],'cluster':[]}}
        pairs,_=build_candidate_pairs(units,10,1)
        self.assertTrue(pairs[0]['segmente_a'][0]['id'].startswith('P1'))
        self.assertTrue(pairs[0]['segmente_b'][0]['id'].startswith('P1'))
        self.assertEqual(pairs[0]['gemeinsame_personen'],['P1'])

    def test_checkpoint_resume_after_interruption_and_mismatch(self):
        book=[CodebookEntry('A','A','','','','definition','example')]
        segs=[Segment('s1','one','A','P1'),Segment('s2','two','A','P2')]
        prompts={'blind_coding':{'system':'blind','user':'{segment_id} {segment} {codebook}'}}
        good={'segment_id':'s1','predicted_code':'A','confidence':'hoch','begruendung':'ok','alternative_codes':[]}
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'checkpoint.json')
            with self.assertRaises(RuntimeError):
                blind_code_segments(segs,book,prompts,{}, {'model':'mock'},llm=MockLLM([good]),checkpoint_path=path)
            mock=MockLLM([{**good,'segment_id':'s2'}])
            _,out=blind_code_segments(segs,book,prompts,{}, {'model':'mock'},llm=mock,checkpoint_path=path)
            self.assertEqual(len(mock.calls),1)
            self.assertEqual(out['processing_status'],'completed')
            with self.assertRaises(ValueError):
                blind_code_segments(segs,book,prompts,{}, {'model':'changed'},llm=mock,checkpoint_path=path)

    def test_agreement_reports_abstentions_and_gates_kappa(self):
        book=[CodebookEntry('A','A','','','','','')]
        segs=[Segment(f's{i}','x','A','P1') for i in range(100)]
        verify={'results':[{'segment_id':s.segment_id,'human_code':'A','verification':'bestätigt'} for s in segs]}
        blind={'results':[{'segment_id':s.segment_id,'predicted_code':'A' if i<10 else 'unklar'} for i,s in enumerate(segs)]}
        _,out=calculate_agreement(segs,book,verify,blind)
        self.assertEqual(out['exact_agreement']['rate'],1)
        self.assertEqual(out['coverage']['assignment_rate'],.1)
        self.assertEqual(out['coverage']['blind_abstentions'],90)
        self.assertFalse(out['cohens_kappa']['calculated'])

    def test_stale_output_cannot_pass_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'old.json').write_text('{}')
            with self.assertRaises(RuntimeError):
                load_runner().run_step({'id':'noop','name':'noop','outputs':['old.json']},[sys.executable,'-c','pass'],Path(tmp))

if __name__=='__main__': unittest.main()
