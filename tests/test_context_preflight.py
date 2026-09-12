import sys, unittest, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from context_preflight import check_context, require_context
from coding_validation_common import CodebookEntry, Segment


class ContextTests(unittest.TestCase):
    def config(self,context=8192):
        return {'llm':{'num_ctx':context,'max_tokens':512},'context':{},
            'coding_agreement':{'label_mode':'unspecified'},
            'prompts':{'code_verification':{'system':'Check','user':'{segment} {codebook} {target_code}'},
                       'blind_coding':{'system':'Code','user':'{segment} {codebook}'},
                       'cluster_analysis':{'system':'Cluster','user':'{segments}'}}}
    def test_whole_cluster_can_block_even_when_individual_rows_fit(self):
        book=[CodebookEntry('A','A','','','','Definition','')]
        rows=[Segment(str(i),'x'*1500,'A','P') for i in range(6)]
        small=check_context(self.config(),rows,book,['blind_coding'])
        require_context(small)
        grouped=check_context(self.config(),rows,book,['clusterer'])
        with self.assertRaisesRegex(ValueError,'Start gesperrt'):
            require_context(grouped)
        self.assertEqual(grouped['blocked'][0]['module'],'clusterer')
        require_context(check_context(self.config(16384),rows,book,['clusterer']))
    def test_full_codebook_rules_count_in_the_bound(self):
        book=[CodebookEntry('A','A','','','','Definition','',einschluss='Regel '*1600)]
        report=check_context(self.config(),[Segment('s','kurz','A','P')],book,['blind_coding'])
        with self.assertRaises(ValueError):require_context(report)
    def test_disabled_module_does_not_block_and_later_outputs_are_uncertain(self):
        book=[CodebookEntry('A','A','','','','Definition','')]
        cfg=self.config();cfg['prompts']['blind_coding']['system']='x'*50000
        report=check_context(cfg,[Segment('s','text','A','P')],book,['summarizer'])
        require_context(report)
        self.assertTrue(any('unbekannt' in w for w in report['warnings']))
        self.assertNotIn('blind_coding',[r['module'] for r in report['checks']])
    def test_small_context_stops_ui_start_before_process_creation(self):
        from local_app import App
        from test_local_app import settings
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetischer Test',True)['id']
            opts=settings(app);opts.update(num_ctx=2048,max_tokens=512,modules=['blind_coding'])
            with patch('local_app.subprocess.Popen') as process:
                with self.assertRaisesRegex(ValueError,'Start gesperrt'):app.save(pid,opts)
                with self.assertRaises(ValueError):app.start(pid)
                process.assert_not_called()
            # Re-check the stored configuration on start, even when a previous
            # save succeeded and the caller bypasses the browser form.
            opts['num_ctx']=65536
            app.save(pid,opts)
            config=next((app.project_dir(pid)/'revisions').glob('*/config.yaml'))
            import yaml
            for config in (app.project_dir(pid)/'revisions').glob('*/config.yaml'):
                cfg=yaml.safe_load(config.read_text(encoding='utf-8'))
                cfg['llm']['num_ctx']=2048
                config.write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf-8')
            with patch('local_app.subprocess.Popen') as process:
                with self.assertRaisesRegex(ValueError,'Start gesperrt'):app.start(pid)
                process.assert_not_called()

if __name__=='__main__':unittest.main()
