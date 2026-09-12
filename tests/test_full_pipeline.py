import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]

class FullPipelineTests(unittest.TestCase):
    def test_all_modules_resume_and_input_mismatch(self):
        self._run_pipeline(False)

    def test_multi_label_review_and_hierarchical_pipeline(self):
        self._run_pipeline(True)

    def test_partial_modules_resume_without_repeating_successful_requests(self):
        for module in ('cluster_analysis','cluster_summary','swot_analysis','meta_swot','person_analysis','ambiguity_analysis','hierarchical_reduction'):
            with self.subTest(module=module):
                self._run_pipeline(module=='hierarchical_reduction',module)

    def _run_pipeline(self,multi,partial_module=None):
        with tempfile.TemporaryDirectory() as tmp:
            temp=Path(tmp)
            cfg=yaml.safe_load((ROOT/'config/config_v2.yaml').read_text(encoding='utf-8'))
            cfg['llm']['model']='mock'
            cfg['coding_agreement']['label_mode']='multi_label' if multi else 'unspecified'
            if multi: cfg['llm']['hierarchical_synthesis']={'enabled':True,'force':True,'batch_items':12,'summary_chars':1200}
            cfg['context']={}
            cfg['columns']['segment_id']='ID'
            cfg['columns'].pop('unit_id',None)
            if multi: cfg['columns']['unit_id']='PassageID'
            cfg['paths']['input_csv']=str(temp/'input.csv')
            cfg['paths']['category_system_csv']=str(temp/'book.csv')
            (temp/'input.csv').write_text('ID;Dokumentname;Code;Segment\nx;P1;A > B > C > positiv;gut\ny;P1;A > B > C > negativ;schlecht\nz;P2;A > B > C > positiv;gut\nw;P2;A > B > C > negativ;schlecht\n',encoding='utf-8')
            if multi:
                (temp/'input.csv').write_text('ID;PassageID;Dokumentname;Code;Segment\nx;U1;P1;A > B > C > positiv;gut\ny;U2;P1;A > B > C > negativ;schlecht\nz;U3;P2;A > B > C > positiv;gut und schlecht\nw;U3;P2;A > B > C > negativ;gut und schlecht\n',encoding='utf-8')
            (temp/'book.csv').write_text('Kategorie;Unterkategorie;Ausprägung;Facette;Definition;Ankerbeispiel\nA;B;C;positiv;gut;gut\nA;B;C;negativ;schlecht;schlecht\n',encoding='utf-8')
            placeholders={'cluster_analysis':'{segments}','cluster_summary':'{clusters}','category_summary':'{subcats}',
                'swot_analysis':'{clusters}','meta_swot':'{clusters}','person_analysis':'{persons}',
                'person_comparison':'{persons}','contrast_analysis':'{data}','relation_analysis':'{data}',
                'ambiguity_analysis':'{data}','evidence_audit':'{data}','overall_synthesis':'{data}',
                'code_verification':'{"segment_id":"{segment_id}","human_code":"{human_code}"}',
                'blind_coding':'{"segment_id":"{segment_id}","segment":"{segment}"}'}
            for key,user in placeholders.items(): cfg['prompts'][key]={'system':key,'user':user}
            config=temp/'config.yaml'
            config.write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf-8')
            base=[sys.executable,str(ROOT/'tests/mock_pipeline.py'),'--config',str(config)]
            env={**os.environ,'PYTHONUTF8':'1','MPLBACKEND':'Agg','MOCK_FAIL_MODULE':partial_module or 'person_comparison'}
            if partial_module:
                env.update(MOCK_FAIL_AFTER='1',MOCK_TRACE_PATH=str(temp/'requests.jsonl'))
            first=subprocess.run(base+['--output-dir',str(temp/'runs')],capture_output=True,text=True,encoding='utf-8',env=env)
            self.assertNotEqual(first.returncode,0)
            run=next((temp/'runs').iterdir())
            manifest=json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
            if not partial_module:self.assertIn('person_analysis',manifest['completed_steps'],first.stderr[-6000:])
            self.assertEqual(manifest['status'],'failed')
            self.assertEqual(manifest['module_status'][manifest['current_module']], 'failed')
            if not partial_module:
                self.assertIn('relation_analysis',manifest['completed_steps'])
                self.assertIn('ambiguity_analysis',manifest['completed_steps'])
                self.assertEqual(manifest['module_status']['contrast_analysis'],'blocked')
                self.assertTrue(manifest['module_errors']['person_comparison']['action'])
            if partial_module:
                trace=[json.loads(line) for line in (temp/'requests.jsonl').read_text().splitlines()]
                first_success=next(x for x in trace if x['module']==partial_module)
                self.assertTrue(list((run/'_checkpoints').rglob('*.json')))
            env.pop('MOCK_FAIL_MODULE')
            resumed=subprocess.run(base+['--resume',str(run)],capture_output=True,text=True,encoding='utf-8',env=env)
            self.assertEqual(resumed.returncode,0,resumed.stderr[-6000:])
            manifest=json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(set(manifest['completed_steps']),{m['id'] for m in cfg['pipeline']['modules'] if m.get('enabled',True)})
            self.assertEqual(manifest['status'],'success')
            self.assertTrue(all(value=='success' for value in manifest['module_status'].values()))
            self.assertNotIn('error',manifest)
            self.assertTrue(manifest['failure_history'])
            if partial_module:
                trace=[json.loads(line) for line in (temp/'requests.jsonl').read_text().splitlines()]
                self.assertEqual(sum(x==first_success for x in trace),1,'Successful part was requested again')
            clusters=json.loads((run/'clusters_output.json').read_text(encoding='utf-8'))
            self.assertEqual({c['code_path'] for c in clusters['clusters']},{'A > B > C > positiv','A > B > C > negativ'})
            audit=json.loads((run/'evidence_audit_v1.json').read_text(encoding='utf-8'))
            self.assertTrue(audit['befunde'])
            self.assertGreater(audit['befunde'][0]['gegenbeleg_count'],0)
            swot=json.loads((run/'swot_v1.json').read_text(encoding='utf-8'))
            self.assertEqual(len(swot['swot']),2)
            people=json.loads((run/'person_analysis_v1.json').read_text(encoding='utf-8'))
            self.assertEqual(set(people['persons']),{'P1','P2'})
            self.assertTrue((run/'gesamtbericht.md').is_file())
            self.assertTrue((run/'gesamtbericht.html').is_file())
            self.assertIn('gesamtbericht.html',manifest['output_hashes'])
            self.assertTrue((run/'review_queue.html').is_file())
            if multi:
                agreement=json.loads((run/'coding_agreement_v1.json').read_text(encoding='utf-8'))
                self.assertEqual(agreement['n_units'],3)
                self.assertEqual(agreement['exact_agreement']['rate'],1)
                synthesis=json.loads((run/'overall_synthesis_v1.json').read_text(encoding='utf-8'))
                self.assertTrue(synthesis['hierarchical_reduction']['used'])
                self.assertTrue(synthesis['kernergebnisse'])
            (temp/'input.csv').write_text((temp/'input.csv').read_text(encoding='utf-8')+'\n',encoding='utf-8')
            bad=subprocess.run(base+['--resume',str(run)],capture_output=True,text=True,encoding='utf-8',env=env)
            self.assertNotEqual(bad.returncode,0)
            self.assertIn('Wiederaufnahme abgelehnt',bad.stderr)

if __name__=='__main__': unittest.main()
