import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import swot_core,meta_swot_core

class SWOTProgressTests(unittest.TestCase):
    def test_swot_reports_actual_category_completions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);events=[]
            fixtures={'clusters.json':{'clusters':[{'hauptkategorie':name,'cluster_name':name,'segments':['s1']} for name in ('A','B')]},'texts.json':{'s1':'Artificial example'},'summary.json':{}}
            for name,value in fixtures.items():(p/name).write_text(json.dumps(value))
            params={'num_ctx':32768,'max_tokens':2048,'parallel_workers':1,'partial_checkpoint_dir':str(p/'cache')}
            with patch('swot_core.build_prompt_for_module',return_value=('system','input')),patch('swot_core.llm_swot',return_value=json.dumps({d:[] for d in swot_core.DIMENSIONS})),patch('analysis_work.update_progress',side_effect=lambda **kw:events.append(kw)):
                swot_core.build_swot(str(p/'clusters.json'),str(p/'texts.json'),str(p/'summary.json'),params,{}, {})
            self.assertEqual(events[0]['total'],2)
            self.assertEqual(events[0]['unit'],'categories')
            self.assertEqual([e['completed'] for e in events if 'completed' in e],[0,1,2])

    def test_meta_swot_counts_dimensions_and_leaves_failed_one_unfinished(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'swot.json';p.write_text('{"swot":{}}');events=[]
            with patch('meta_swot_core.update_progress',side_effect=lambda **kw:events.append(kw)):
                meta_swot_core.build_meta_swot(str(p),{}, {}, {})
            self.assertEqual(events[0],{'completed':0,'total':4,'unit':'dimensions'})
            self.assertEqual([e['completed'] for e in events if 'completed' in e],[0,1,2,3,4])
            events.clear()
            with patch('meta_swot_core.update_progress',side_effect=lambda **kw:events.append(kw)),patch('meta_swot_core.build_dimension_meta',side_effect=RuntimeError('failure')):
                with self.assertRaises(RuntimeError):meta_swot_core.build_meta_swot(str(p),{}, {}, {})
            self.assertEqual(len([e for e in events if 'completed' in e]),1)
            self.assertEqual(events[0]['completed'],0)

if __name__=='__main__':unittest.main()
