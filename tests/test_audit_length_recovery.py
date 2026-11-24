import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import evidence_audit_core as audit
from llm_client import LLMOutputLimitError,LLMResponseError,LLMTransportError


class AuditLengthRecoveryTests(unittest.TestCase):
    def fixtures(self,n=4,m=3):
        return ([{'audit_id':f'A{i}','text':'complete finding '+str(i)} for i in range(n)],
                [{'counter_id':f'C{i}','text':'complete candidate '+str(i)} for i in range(m)])

    def prompt(self,aa,cc):return 'fixed complete context',json.dumps({'audits':aa,'counters':cc})

    def response(self,aa,cc):
        return json.dumps({'zuordnungen':[{'audit_id':a['audit_id'],
          'gegenbeleg_ids':[c['counter_id'] for c in cc],'einordnung':'Synthetic validated explanation'} for a in aa]})

    def test_length_splits_both_axes_without_losing_pairs_and_resume_calls_no_model(self):
        aa,cc=self.fixtures();seen=[];calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            params={'max_tokens':10000,'num_ctx':65536,'parallel_workers':1,'partial_checkpoint_dir':tmp}
            def model(s,u,p):
                data=json.loads(u);a,c=data['audits'],data['counters'];calls.append((a,c))
                self.assertEqual(s,'fixed complete context');self.assertEqual(p['max_tokens'],10000)
                if len(a)>1 or len(c)>1:raise LLMOutputLimitError('Antwortlimit erreicht.')
                seen.extend((x['audit_id'],y['counter_id']) for x in a for y in c)
                return self.response(a,c)
            with patch.object(audit,'_llm',side_effect=model):
                result,count=audit.map_audit_blocks(aa,cc,self.prompt,params)
            self.assertCountEqual(seen,[(a['audit_id'],c['counter_id']) for a in aa for c in cc])
            self.assertEqual(len(seen),len(set(seen)));self.assertEqual(len(calls),23)
            for value in result.values():self.assertEqual(value['gegenbeleg_ids'],['C0','C1','C2'])
            with patch.object(audit,'_llm',side_effect=AssertionError('recomputed successful block')):
                again,_=audit.map_audit_blocks(aa,cc,self.prompt,params)
            self.assertEqual(result,again)

    def test_singleton_failure_is_not_saved_or_relabelled_success(self):
        aa,cc=self.fixtures(1,1)
        with tempfile.TemporaryDirectory() as tmp:
            params={'max_tokens':10000,'num_ctx':65536,'partial_checkpoint_dir':tmp}
            with patch.object(audit,'_llm',side_effect=LLMOutputLimitError('Antwortlimit erreicht.')):
                with self.assertRaises(LLMResponseError):audit.map_audit_blocks(aa,cc,self.prompt,params)
            self.assertEqual(list(Path(tmp).rglob('*.json')),[])

    def test_unrelated_transport_confidence_and_validation_errors_are_not_split(self):
        aa,cc=self.fixtures()
        for exc in (LLMTransportError('authentication'),LLMResponseError('Antwortformat ungültig'),ValueError('unknown ID')):
            with self.subTest(error=type(exc).__name__),patch.object(audit,'_llm',side_effect=exc) as model:
                with self.assertRaises(type(exc)):audit.map_audit_blocks(aa,cc,self.prompt,{'num_ctx':65536,'max_tokens':10000})
                self.assertEqual(model.call_count,1)

if __name__=='__main__':unittest.main()
