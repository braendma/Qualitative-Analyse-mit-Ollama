"""The prompt viewer must read frozen templates, never interpolate study inputs."""
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from test_local_app import App, settings, make_server
from local_app import RUNNER
from prompt_catalog import catalog
from runtime_support import atomic_json


class PromptViewTests(unittest.TestCase):
    def test_all_modules_rules_placeholders_and_no_interpolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp)
            cfg = copy.deepcopy(app.template)
            cfg['context'] = {'project_description': 'PRIVATE_STUDY_TEXT'}
            cfg['llm']['api_key'] = 'PRIVATE_API_KEY'
            data = catalog(cfg, RUNNER.normalize_modules(cfg))
            self.assertEqual(len(data['modules']), 15)
            deterministic = {'coding_agreement', 'review_queue'}
            for module in data['modules']:
                if module['id'] in deterministic:
                    self.assertEqual(module['templates'], [])
                    self.assertIn('ohne eigenen LLM', module['note'])
                else:
                    self.assertTrue(module['templates'], module['id'])
                    self.assertTrue(all(t['system'] and t['user'] for t in module['templates']))
            text = json.dumps(data)
            self.assertNotIn('PRIVATE_STUDY_TEXT', text)
            self.assertNotIn('PRIVATE_API_KEY', text)
            self.assertIn('{context}', text)
            self.assertTrue(data['rules'])
            cfg['prompts']['cluster_analysis']['user'] = '<script>bad()</script> {segments}'
            row = catalog(cfg, RUNNER.normalize_modules(cfg))['modules'][0]
            # Preserve source exactly; the frontend must render it as text.
            self.assertEqual(row['templates'][0]['user'], '<script>bad()</script> {segments}')

    def test_saved_run_templates_survive_later_changes_and_read_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetic', True)['id']
            self.assertIn('Programmvorlage', app.prompt_templates(pid)['source'])
            app.template['prompts']['cluster_analysis']['system']='ORIGINAL_TEMPLATE'
            opts=settings(app);app.save(pid, opts)
            folder=app.project_dir(pid)
            cfg=folder/'revisions'/app.project(pid)['revision']/'config.yaml'
            jid='a'*20
            atomic_json(folder/'jobs'/jid/'job.json', {'id':jid, 'config':str(cfg)})
            app.template['prompts']['cluster_analysis']['system']='NEW_TEMPLATE'
            app.save(pid, opts)
            before={str(p):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
            frozen=app.prompt_templates(pid, jid)
            current=app.prompt_templates(pid)
            self.assertEqual(frozen['modules'][0]['templates'][0]['system'],'ORIGINAL_TEMPLATE')
            self.assertEqual(current['modules'][0]['templates'][0]['system'],'NEW_TEMPLATE')
            self.assertEqual(before,{str(p):p.read_bytes() for p in folder.rglob('*') if p.is_file()})
            other=app.create('Other', True)['id']
            atomic_json(folder/'jobs'/jid/'job.json', {'config':str(app.project_dir(other)/'config.yaml')})
            with self.assertRaisesRegex(ValueError,'gehört nicht'):app.prompt_templates(pid,jid)

    def test_prompt_endpoint_requires_session_and_returns_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetic',True)['id']
            server=make_server(app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                for token,expected in [('',403),(server.token,200)]:
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    conn.request('GET','/api/prompts?project='+pid,headers={'X-App-Token':token})
                    response=conn.getresponse();body=response.read();conn.close()
                    self.assertEqual(response.status,expected)
                    if expected==200:self.assertEqual(len(json.loads(body)['modules']),15)
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_synthesis_budget_is_validated_and_saved_in_a_new_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetic',True)['id'];opts=settings(app)
            app.save(pid,opts)
            cfg=app.project_dir(pid)/'revisions'/app.project(pid)['revision']/'config.yaml'
            before=cfg.read_bytes()
            for invalid in [0,10001,True,1.5,'256']:
                with self.assertRaisesRegex(ValueError,'Aufrufbudget'):
                    app.save(pid,{**opts,'synthesis_max_calls':invalid})
            app.save(pid,{**opts,'synthesis_max_calls':256})
            import yaml
            new=app.project_dir(pid)/'revisions'/app.project(pid)['revision']/'config.yaml'
            self.assertEqual(yaml.safe_load(new.read_text(encoding='utf-8'))['llm']['hierarchical_synthesis']['max_calls'],256)
            self.assertEqual(cfg.read_bytes(),before)
            self.assertNotEqual(cfg,new)


if __name__=='__main__':unittest.main()
