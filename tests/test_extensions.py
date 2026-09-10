import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from coding_validation_common import Segment,CodebookEntry
from multi_label_core import blind_code_units,calculate_set_agreement,group_units
from review_queue import build_queue,validate_decisions,render_queue
from hierarchical_synthesis import reduce_sources,fits
from llm_client import ContextBudgetError

BOOK=[CodebookEntry(c,c,'','','',c,c) for c in ['A','B','C']]
SEGS=[Segment('S1','Gleicher Text','A','P1','U1'),Segment('S2','Gleicher Text','B','P1','U1'),Segment('S3','Anderer Text','A','P2','U2')]
VERIFY={'results':[{'segment_id':s.segment_id,'human_code':s.human_code,'verification':'bestätigt','begruendung':'Beleg','processing_status':'completed'} for s in SEGS]}
PARAMS={'model':'mock','max_tokens':200,'num_ctx':8000}
def fake_blind(messages,params):
    data=json.loads(messages[1]['content'])
    codes=['A','C'] if data['segment']=='Gleicher Text' else ['A']
    return json.dumps({'unit_id':data['unit_id'],'predicted_codes':codes,'assignment_status':'assigned','confidence':'mittel','begruendung':'Test'})


class ExtensionTests(unittest.TestCase):
    def test_units_require_explicit_consistent_identity(self):
        for segments in ([Segment('a','t','A','p')], [*SEGS,Segment('S4','changed','B','P1','U1')], [*SEGS,Segment('S4','Gleicher Text','B','P2','U1')]):
            with self.assertRaises(ValueError):group_units(segments)

    def test_multi_label_one_blind_call_per_unit_and_checkpoint(self):
        calls=[]
        def fake(messages,params):
            calls.append(messages)
            data=json.loads(messages[1]['content'])
            self.assertEqual(set(data),{'unit_id','segment','codebook','context'})
            self.assertNotIn('U1',data['unit_id'])
            return fake_blind(messages,params)
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'checkpoint.json')
            _,output=blind_code_units(SEGS,BOOK,{}, {},PARAMS,llm=fake,checkpoint_path=path)
            self.assertEqual(len(calls),2)
            self.assertEqual(output['unit_count'],2)
            blind_code_units(SEGS,BOOK,{}, {},PARAMS,llm=lambda *a: self.fail('Checkpoint not reused'),checkpoint_path=path)

    def test_exact_set_metrics_and_missing_additional(self):
        _,blind=blind_code_units(SEGS,BOOK,{}, {},PARAMS,llm=fake_blind)
        _,out=calculate_set_agreement(SEGS,BOOK,VERIFY,blind)
        self.assertEqual(out['exact_agreement']['rate'],.5)
        self.assertEqual(out['set_metrics']['micro_precision'],2/3)
        self.assertEqual(out['set_metrics']['micro_recall'],2/3)
        self.assertEqual(out['set_metrics']['micro_f1'],2/3)
        self.assertEqual(out['cases'][0]['missing_codes'],['B'])
        self.assertEqual(out['cases'][0]['additional_codes'],['C'])
        self.assertEqual(out['set_metrics']['mean_jaccard'],(1/3+1)/2)
        self.assertFalse(out['cohens_kappa']['calculated'])

    def test_abstention_not_empty_prediction_but_none_is_scored(self):
        _,blind=blind_code_units(SEGS,BOOK,{}, {},PARAMS,llm=fake_blind)
        row=blind['unit_results'][0]
        row.update(predicted_codes=[],assignment_status='abstained')
        _,out=calculate_set_agreement(SEGS,BOOK,VERIFY,blind)
        self.assertEqual(out['coverage']['evaluated_units'],1)
        self.assertIsNone(out['cases'][0]['missing_codes'])
        row['assignment_status']='none'
        _,out=calculate_set_agreement(SEGS,BOOK,VERIFY,blind)
        self.assertEqual(out['coverage']['evaluated_units'],2)
        self.assertEqual(out['set_metrics']['missing'],2)
        row['processing_status']='failed'
        _,out=calculate_set_agreement(SEGS,BOOK,VERIFY,blind)
        self.assertEqual(out['coverage']['evaluated_units'],1)

    def test_legacy_row_predictions_not_misrepresented_as_sets(self):
        with self.assertRaises(ValueError):calculate_set_agreement(SEGS,BOOK,VERIFY,{'results':[]})

    def test_review_decisions_roundtrip_and_stale_or_forged_rejected(self):
        _,blind=blind_code_units(SEGS,BOOK,{}, {},PARAMS,llm=fake_blind)
        _,out=calculate_set_agreement(SEGS,BOOK,VERIFY,blind)
        queue=build_queue(SEGS,BOOK,out,VERIFY,blind,{'befunde':[]})
        payload={'schema_version':1,'source_fingerprint':queue['source_fingerprint'],'decisions':[
            {'case_id':'unit:U1','decision':'custom','final_codes':['A','B','C'],'note':'Beide Aspekte belegt.','reviewer':'Test'}]}
        result=validate_decisions(queue,payload)
        self.assertEqual(result['decisions'][0]['final_codes'],['A','B','C'])
        self.assertEqual(queue['cases'][0]['human_codes'],['A','B'])
        for change in ({'decision':'accept_model'},{'final_codes':['unknown']},{'reviewer':''}):
            bad=json.loads(json.dumps(payload));bad['decisions'][0].update(change)
            with self.assertRaises(ValueError):validate_decisions(queue,bad)
        with self.assertRaises(ValueError):validate_decisions(queue,{**payload,'source_fingerprint':'old'})
        queue['cases'][0]['text']='</script><script>alert(1)</script>'
        self.assertNotIn('</script><script>alert(1)',render_queue(queue))
        self.assertIn("connect-src 'none'",render_queue(queue))

    def test_hierarchy_all_sources_preserved_with_bounded_requests(self):
        sources={'A':{'findings':[{'thema':str(i),'text':'Beleg mit Widerspruch. '*90,'segment_ids':[str(i)]} for i in range(12)]}}
        params={**PARAMS,'num_ctx':6000,'hierarchical_synthesis':{'batch_items':3,'summary_chars':300}}
        calls=[]
        def final(payload):return 'final',json.dumps(payload,ensure_ascii=False)
        def llm(messages,params):
            self.assertTrue(fits(messages[0]['content'],messages[1]['content'],params))
            batch=json.loads(messages[1]['content'])['items'];calls.append(batch)
            return json.dumps({'summary':'Teilbefunde zeigen Unterstützung und Widerspruch.'})
        payload,ledger=reduce_sources(sources,final,params,llm)
        self.assertTrue(ledger['used']);self.assertGreater(len(calls),1)
        self.assertEqual(len(ledger['leaves']),12)
        def leaves(nid):
            if nid in ledger['leaves']:return {nid}
            return set().union(*(leaves(i) for i in ledger['nodes'][nid]['input_ids']))
        self.assertEqual(set().union(*(leaves(n) for n in ledger['final_node_ids'])),set(ledger['leaves']))
        self.assertTrue(fits(*final(payload),params))

    def test_hierarchy_unknown_ids_budget_and_nonconvergence(self):
        sources={'A':{'items':[{'text':'a '*900} for _ in range(5)]}}
        params={**PARAMS,'num_ctx':5000,'hierarchical_synthesis':{'force':True,'max_calls':1}}
        final=lambda data:('final',json.dumps(data))
        with self.assertRaises(ContextBudgetError):
            reduce_sources(sources,final,params,lambda *args:json.dumps({'summaries':[{'text':'x','input_ids':['unknown']}]}))
        params['hierarchical_synthesis']['max_calls']=3
        with self.assertRaises(ValueError):
            reduce_sources(sources,final,params,lambda *args:json.dumps({'summaries':[{'text':'x','input_ids':['unknown']}]}))
        with self.assertRaises(ContextBudgetError):reduce_sources({'A':{'thema':'huge','text':'x'*50000}},final,params,lambda *a:self.fail('Oversized atomic finding sent'))

    def test_hierarchy_multiple_levels(self):
        sources={'A':{'findings':[{'thema':str(i),'text':'Beleg. '*550} for i in range(40)]}}
        params={**PARAMS,'num_ctx':6000,'hierarchical_synthesis':{'batch_items':3,'summary_chars':500,'max_calls':128}}
        final=lambda data:('final',json.dumps(data))
        def llm(messages,params):
            batch=json.loads(messages[1]['content'])['items']
            return json.dumps({'summary':'Beleg mit Widerspruch. '*16})
        _,ledger=reduce_sources(sources,final,params,llm)
        self.assertGreaterEqual(ledger['levels'],2)
        self.assertEqual(len(ledger['leaves']),40)

    def test_hierarchy_oversized_static_prompt_stops_without_model_call(self):
        with self.assertRaises(ContextBudgetError):
            reduce_sources({'A':{'text':'test'}},lambda data:('x'*10000,json.dumps(data)),PARAMS,
                           lambda *args:self.fail('Unnecessary cloud call for impossible final prompt'))

if __name__=='__main__':unittest.main()
