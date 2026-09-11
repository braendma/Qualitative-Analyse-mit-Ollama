import hashlib,json,sys,tempfile,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from coding_validation_common import Segment,CodebookEntry
from multi_label_core import blind_code_units
from code_verification_core import verify_segments
from parallel_items import completed_items

class ParallelItemsTests(unittest.TestCase):
    def test_blind_groups_remain_intact_ordered_and_resumable(self):
        book=[CodebookEntry('A','A','','','','Definition','')]
        segments=[Segment('s1','Text eins','A','P1','u1'),Segment('s2','Text zwei','A','P2','u2'),Segment('s3','Text eins','A','P1','u1')]
        barrier=threading.Barrier(2);calls=[]
        def llm(messages,params):
            payload=json.loads(messages[1]['content']);calls.append(payload)
            barrier.wait(timeout=5)
            return json.dumps({'unit_id':payload['unit_id'],'predicted_codes':['A'],'assignment_status':'assigned','confidence':'hoch','begruendung':'Test'})
        params={'model':'mock','parallel_workers':2}
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'check.json')
            _,out=blind_code_units(segments,book,{}, {},params,llm=llm,checkpoint_path=path)
            self.assertEqual([r['unit_id'] for r in out['unit_results']],['u1','u2'])
            self.assertEqual(out['unit_results'][0]['segment_ids'],['s1','s3'])
            self.assertEqual(len(calls),2)
            self.assertTrue(all('human_code' not in json.dumps(p) and 'P1' not in json.dumps(p) for p in calls))
            _,resumed=blind_code_units(segments,book,{}, {},params,llm=lambda *a: self.fail('Repeated request'),checkpoint_path=path)
            self.assertEqual(resumed['unit_results'],out['unit_results'])
    def test_verification_results_keep_input_order(self):
        book=[CodebookEntry('A','A','','','','Definition','')]
        segments=[Segment('s1','eins','A','P1'),Segment('s2','zwei','A','P2')]
        barrier=threading.Barrier(2)
        def llm(messages,params):
            payload=json.loads(messages[1]['content']);barrier.wait(timeout=5)
            return json.dumps({'segment_id':payload['id'],'human_code':'A','verification':'bestätigt','confidence':'hoch','begruendung':'Test','alternative_codes':[]})
        _,out=verify_segments(segments,book,{'code_verification':{'system':'test','user':'{"id":"{segment_id}"}'}},{},{'model':'mock','parallel_workers':2},llm=llm)
        self.assertEqual([r['segment_id'] for r in out['results']],['s1','s2'])
    def test_failure_drains_completed_items_without_scheduling_rest(self):
        seen=[];received=[]
        def work(i):
            seen.append(i)
            if i==0:raise RuntimeError('failed')
            return i
        with self.assertRaises(RuntimeError):
            for index,result in completed_items(range(10),work,2):received.append(result)
        self.assertEqual(set(seen),{0,1});self.assertEqual(received,[1])

if __name__=='__main__':unittest.main()
