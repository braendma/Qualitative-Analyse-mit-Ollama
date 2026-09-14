import copy
import tempfile
import unittest

from test_local_app import settings
from local_app import App
from prompt_catalog import catalog
from failure_help import failure_help


class SensitivityAppTests(unittest.TestCase):
    def test_app_explicit_variants_and_cost_with_disabled_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);project=app.create('Künstlicher Sensitivitätstest',demo=True)
            options=settings(app)
            options.update(modules=['blind_coding','sensitivity'],sensitivity={'modules':['blind_coding'],
                'repetitions':2,'variants':[{'id':'warm','llm':{'temperature':0.2}}]})
            saved=app.save(project['id'],options)
            self.assertEqual(saved['sensitivity_plan']['module_executions'],8)
            self.assertEqual(saved['sensitivity_plan']['configuration_count'],2)
            self.assertEqual(saved['sensitivity_plan']['added_prerequisites'],['clusterer'])
            invalid=copy.deepcopy(options);invalid['sensitivity']['variants']=[]
            with self.assertRaises(ValueError):app.save(project['id'],invalid)
            options['modules']=['coverage'];options['sensitivity']='ignored when off'
            self.assertNotIn('sensitivity_plan',app.save(project['id'],options))

    def test_prompt_catalog_preserves_base_and_overlays_only_changed_fields(self):
        config={'diagnostics':{'sensitivity':{'modules':['blind_coding'],'variants':[
            {'id':'precise','prompts':{'blind_coding':{'system':'Genauer prüfen'}}}]}},
            'prompts':{'blind_coding':{'system':'Basis','user':'{segment}'}}}
        modules=[{'id':'blind_coding','name':'Blind','depends_on':[]},
                 {'id':'sensitivity','name':'Sensitivität','depends_on':[]}]
        row=catalog(config,modules)['modules'][-1]
        self.assertEqual(len(row['templates']),2)
        self.assertEqual(row['templates'][1]['system'],'Genauer prüfen')
        self.assertEqual(row['templates'][1]['user'],'{segment}')
        self.assertIn('zusätzliche Modellaufrufe',row['note'])
        for value in (None,[],{'sensitivity':None},{'sensitivity':{'variants':None}}):
            self.assertIsInstance(catalog({'diagnostics':value},modules),dict)

    def test_explicit_settings_work_with_empty_optional_template_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);project=app.create('Leerer Diagnoseabschnitt',demo=True)
            options=settings(app)
            options.update(modules=['blind_coding','sensitivity'],sensitivity={'modules':['blind_coding'],
                'repetitions':2,'variants':[{'id':'warm','llm':{'temperature':0.2}}]})
            app.template['diagnostics']=None
            result=app.save(project['id'],options)
            self.assertEqual(result['sensitivity_plan']['configuration_count'],2)
            self.assertIsNone(app.template['diagnostics'])
            import threading
            import http.client
            import json
            from local_app import make_server
            server=make_server(app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                conn.request('GET','/api/state',headers={'X-App-Token':server.token})
                response=conn.getresponse();body=response.read();conn.close()
                self.assertEqual(response.status,200)
                self.assertEqual(json.loads(body)['defaults']['sensitivity']['variants'],[])
            finally:
                server.shutdown();server.server_close();thread.join(timeout=5)

    def test_error_help_names_resume_and_variant_rules(self):
        self.assertEqual(failure_help('Sensitivitätsanalyse unvollständig')['kind'],'sensitivity')
        self.assertIn('_sensitivity_repetitions',failure_help('diagnostics.sensitivity ungültig')['action'])


if __name__=='__main__':unittest.main()
