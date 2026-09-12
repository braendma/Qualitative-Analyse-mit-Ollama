import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from meta_batches import compare_blocks


class MetaParallelTests(unittest.TestCase):
    def test_parallel_blocks_preserve_order_and_reuse_all_checkpoints(self):
        findings=[{'finding_id':f'F{i}','source_id':'S','text':'x'*900} for i in range(16)]
        prompt=lambda fs:('sys',json.dumps(fs))
        entered=threading.Barrier(2)
        lock=threading.Lock();active=0;peak=0;calls=[]
        def compare(s,u,block):
            nonlocal active,peak
            with lock:
                active+=1;peak=max(peak,active);calls.append(block[0]['finding_id'])
            try:entered.wait(timeout=5)
            finally:
                with lock:active-=1
            return [{'finding_ids':[f['finding_id'] for f in block]}]
        with tempfile.TemporaryDirectory() as tmp:
            params={'num_ctx':4096,'max_tokens':1024,'parallel_workers':2,'partial_checkpoint_dir':tmp}
            out,ledger=compare_blocks(findings,prompt,params,compare,lambda *a:self.fail())
            self.assertEqual(peak,2)
            self.assertEqual([i for c in out for i in c['finding_ids']],[f['finding_id'] for f in findings])
            self.assertEqual(len(calls),ledger['parts'])
            repeated,_=compare_blocks(findings,prompt,params,lambda *a:self.fail('Cache not reused'),lambda *a:self.fail())
            self.assertEqual(out,repeated)

    def test_failed_block_does_not_drop_successful_inflight_checkpoint(self):
        findings=[{'finding_id':f'F{i}','source_id':'S','text':'x'*900} for i in range(4)]
        prompt=lambda fs:('sys',json.dumps(fs))
        barrier=threading.Barrier(2)
        def compare(s,u,block):
            barrier.wait(timeout=5)
            if block[0]['finding_id']=='F0':raise RuntimeError('failed')
            return [{'finding_ids':[f['finding_id'] for f in block]}]
        with tempfile.TemporaryDirectory() as tmp:
            params={'num_ctx':4096,'max_tokens':1024,'parallel_workers':2,'partial_checkpoint_dir':tmp}
            with self.assertRaisesRegex(RuntimeError,'failed'):
                compare_blocks(findings,prompt,params,compare,lambda *a:self.fail())
            cached=list((Path(tmp)/'meta_swot_blocks').glob('*.json'))
            self.assertEqual(len(cached),1)
            self.assertEqual(json.loads(cached[0].read_text())['result'][0]['finding_ids'],['F2','F3'])


if __name__=='__main__':unittest.main()
