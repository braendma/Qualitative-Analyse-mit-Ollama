import copy
import tempfile
import unittest

from test_local_app import settings
from local_app import App
from prompt_catalog import catalog
from failure_help import failure_help


class StabilityAppTests(unittest.TestCase):
    def test_app_saves_explicit_cost_plan_and_rejects_missing_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);project=app.create('Künstlicher Stabilitätstest',demo=True)
            options=settings(app)
            options.update(modules=['blind_coding','stability'],stability={'modules':['blind_coding'],'repetitions':2})
            saved=app.save(project['id'],options)
            self.assertEqual(saved['stability_plan']['module_executions'],4)
            self.assertIsNone(saved['stability_plan']['model_calls'])
            self.assertEqual(saved['stability_plan']['added_prerequisites'],['clusterer'])
            invalid=copy.deepcopy(options);invalid['stability']['modules']=[]
            with self.assertRaises(ValueError):app.save(project['id'],invalid)
            disabled=copy.deepcopy(options);disabled['modules']=['coverage'];disabled['stability']='ignored when off'
            self.assertNotIn('stability_plan',app.save(project['id'],disabled))

    def test_prompt_catalog_shows_target_and_prerequisite_templates(self):
        config={'diagnostics':{'stability':{'modules':['blind_coding']}},'prompts':{
            'blind_coding':{'system':'Blind','user':'{segment}'},'cluster_analysis':{'system':'Cluster','user':'{segments}'}}}
        modules=[{'id':'clusterer','name':'Cluster','depends_on':[]},
                 {'id':'blind_coding','name':'Blind','depends_on':['clusterer']},
                 {'id':'stability','name':'Stabilität','depends_on':[]}]
        row=next(m for m in catalog(config,modules)['modules'] if m['id']=='stability')
        self.assertEqual({t['key'] for t in row['templates']},{'blind_coding','cluster_analysis'})
        self.assertIn('zusätzliche Modellaufrufe',row['note'])

    def test_failure_help_distinguishes_incomplete_series_from_changed_identity(self):
        self.assertEqual(failure_help('Stabilitätsanalyse unvollständig')['kind'],'stability')
        self.assertEqual(failure_help('Lokale Modellgewichte verschieden')['kind'],'stability_integrity')

    def test_prompt_preview_tolerates_missing_or_invalid_optional_settings(self):
        modules=[{'id':'stability','name':'Stabilität','depends_on':[]}]
        for diagnostics in (None, [], {'stability':None}, {'stability':[]}):
            with self.subTest(diagnostics=diagnostics):
                result=catalog({'diagnostics':diagnostics},modules)
                self.assertEqual(result['modules'][0]['templates'],[])


if __name__=='__main__':unittest.main()
