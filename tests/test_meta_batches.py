import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from meta_batches import compare_blocks
from meta_swot_core import _build_dimension_meta
from summary_reduction import reduce_prompt

class BoundedMetaTests(unittest.TestCase):
    def test_nonshrinking_response_gets_bounded_full_text_retry(self):
        original='x'*1100; seen=[]
        def model(system,user,params):
            seen.append((system,user))
            return 'kurz' if system.startswith('Verdichte alle') else 'x'*2000
        result=reduce_prompt('sys',original,{'num_ctx':8192,'max_tokens':2048},model,target_bytes=256)
        self.assertEqual(result,'kurz')
        self.assertEqual(seen[-1][1],original,'Repair must receive complete current input')

    def test_permanent_nonconvergence_remains_bounded(self):
        calls=[]
        def model(s,u,p):calls.append(s);return 'x'*3000
        with self.assertRaises(ValueError):
            reduce_prompt('sys','x'*1100,{'num_ctx':8192,'max_tokens':2048},model,target_bytes=256)
        self.assertEqual(len(calls),4)

    def fixtures(self):
        return [{'finding_id':f'F{i}','source_id':f'S{i//15}','thema':'Thema','analyse':'Befund '*150,
                 'segment_ids':[f'seg{i}']} for i in range(45)]

    def test_all_findings_once_context_bounded_source_interleaving_and_resume(self):
        findings=self.fixtures();seen=[]
        prompt=lambda fs:('Vergleiche',json.dumps(fs,ensure_ascii=False))
        params={'num_ctx':8192,'max_tokens':2048}
        def compare(s,u,block):
            seen.extend(f['finding_id'] for f in block)
            self.assertLessEqual(len((s+u).encode())+2048+1024,8192)
            if len(block)>1:self.assertGreater(len({f['source_id'] for f in block}),1)
            return [{'thema':'T','verdichtung':'V','finding_ids':[f['finding_id'] for f in block]}]
        with tempfile.TemporaryDirectory() as tmp:
            params['partial_checkpoint_dir']=tmp
            out,ledger=compare_blocks(findings,prompt,params,compare,lambda *a:self.fail())
            self.assertCountEqual(seen,[f['finding_id'] for f in findings]);self.assertEqual(len(set(seen)),45)
            again,_=compare_blocks(findings,prompt,params,lambda *a:self.fail('Repeated block'),lambda *a:self.fail())
            self.assertEqual(out,again);self.assertGreater(ledger['parts'],1)

    def test_invalid_ids_never_remove_unassigned_original_findings(self):
        findings=self.fixtures()
        with patch('meta_swot_core.llm_meta_swot',return_value=json.dumps({'cluster':[{'thema':'T',
                'verdichtung':'V','finding_ids':['invented']}]})):
            out=_build_dimension_meta('Stärken',findings,{'num_ctx':8192,'max_tokens':2048,'partial_checkpoints':False},
                {'meta_swot':{'system':'system','user':'{clusters}'}},{})
        self.assertEqual(len(out['einzelbefunde']),45)
        self.assertEqual(out['uebergreifende_muster'],[])
        self.assertEqual(out['statistik']['befunde'],45)

if __name__=='__main__':unittest.main()
