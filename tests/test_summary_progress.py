import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from summarizer_core import summarize_clusters
from progress_events import update_progress

class SummaryProgressTests(unittest.TestCase):
    def test_failed_final_synthesis_is_not_counted_and_resume_reuses_clusters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'clusters.json').write_text(json.dumps({'clusters':[{'cluster_name':'Example A','segments':['s1']},{'cluster_name':'Example B','segments':['s2']}]}))
            (root/'texts.json').write_text(json.dumps({'s1':'Artificial text A','s2':'Artificial text B'}))
            events=[]
            with patch.dict(os.environ,{'WORKFLOW_CHECKPOINT_DIR':str(root/'checkpoints')}),patch('summarizer_core.build_prompt_for_module',return_value=('system','input')),patch('summarizer_core.update_progress',side_effect=lambda **kw:events.append(kw)),patch('summarizer_core.llm_summary',side_effect=['A','B',RuntimeError('temporary failure'),'overall']) as model:
                args=(str(root/'clusters.json'),str(root/'texts.json'),{}, {}, {})
                with self.assertRaises(RuntimeError):summarize_clusters(*args)
                self.assertEqual([e['completed'] for e in events if 'completed' in e],[0,1,2])
                self.assertEqual(events[0]['total'],3)
                events.clear()
                _,result=summarize_clusters(*args)
                self.assertEqual(result['final_summary'],'overall')
                self.assertEqual(model.call_count,4) # 2 cluster calls + failed/retried final call.
                self.assertEqual([e['completed'] for e in events if 'completed' in e],[0,1,2,3])
                self.assertIn({'phase':'overall_summary'},events)

    def test_phase_is_written_alongside_numeric_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'progress.json'
            with patch.dict(os.environ,{'WORKFLOW_PROGRESS_FILE':str(path),'WORKFLOW_MODULE':'summarizer'}):
                update_progress(completed=1,total=2,unit='summaries',phase='overall_summary')
                saved=json.loads(path.read_text())
                self.assertEqual(saved['phase'],'overall_summary')
                self.assertEqual(saved['completed'],1)

if __name__=='__main__':unittest.main()
