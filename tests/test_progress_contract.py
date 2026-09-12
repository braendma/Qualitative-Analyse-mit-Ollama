import os,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from progress_events import begin_phase,update_progress,track_module,request_event

class ProgressContractTests(unittest.TestCase):
    def test_phase_change_clears_previous_total_but_preserves_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'progress.json'
            with patch.dict(os.environ,{'WORKFLOW_PROGRESS_FILE':str(p),'WORKFLOW_MODULE':'person_comparison'}):
                begin_phase('person_reduction',12,'persons')
                update_progress(completed=12,requests=30,detail_total=3,detail_completed=3)
                begin_phase('comparison',1)
                state=json.loads(p.read_text())
                self.assertEqual((state['completed'],state['total'],state['requests']),(0,1,30))
                self.assertIsNone(state['detail_total'])

    def test_nested_batches_do_not_change_outer_dimensions(self):
        from meta_batches import compare_blocks
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'progress.json'
            with patch.dict(os.environ,{'WORKFLOW_PROGRESS_FILE':str(p),'WORKFLOW_MODULE':'meta_swot'}):
                begin_phase('analysis',4,'dimensions');update_progress(completed=2)
                compare_blocks([{'finding_id':'F1','source_id':'S1','analyse':'Artificial'}],lambda x:('system',json.dumps(x)),{'num_ctx':4096,'max_tokens':1024,'partial_checkpoint_dir':tmp},lambda *a:[],lambda *a:'short')
                state=json.loads(p.read_text())
                self.assertEqual((state['completed'],state['total'],state['unit']),(2,4,'dimensions'))
                self.assertEqual((state['detail_completed'],state['detail_total']),(1,1))

    def test_cpu_boundary_finishes_only_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'progress.json'
            with patch.dict(os.environ,{'WORKFLOW_PROGRESS_FILE':str(p),'WORKFLOW_MODULE':'review_queue'}):
                @track_module
                def success():return 'result'
                self.assertEqual(success(),'result')
                self.assertEqual(json.loads(p.read_text())['phase'],'finished')
                @track_module
                def failure():raise RuntimeError('synthetic error')
                with self.assertRaises(RuntimeError):failure()
                state=json.loads(p.read_text())
                self.assertEqual(state['phase'],'preparation');self.assertIsNone(state['total'])

    def test_new_module_does_not_inherit_old_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'progress.json';p.write_text(json.dumps({'module':'old','total':841,'completed':841}))
            with patch.dict(os.environ,{'WORKFLOW_PROGRESS_FILE':str(p),'WORKFLOW_MODULE':'new'}):update_progress(requests=1)
            self.assertNotIn('total',json.loads(p.read_text()))

if __name__=='__main__':unittest.main()
