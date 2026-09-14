"""Optional diagnostics do not activate generative stages or require a model."""
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

from test_local_app import App, settings
from local_app import RUNNER


class OptionalDiagnosticsTests(unittest.TestCase):
    def test_defaults_keep_diagnostics_off_and_explicit_choice_adds_no_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp)
            pid = app.create('Synthetic', True)['id']
            opts = settings(app)
            opts.pop('modules')
            result = app.save(pid, opts)
            self.assertNotIn('coverage', [m['id'] for m in result['modules']])
            self.assertNotIn('information_loss', [m['id'] for m in result['modules']])
            self.assertNotIn('codebook_diagnostics', [m['id'] for m in result['modules']])
            result = app.save(pid, {**opts, 'modules': ['coverage']})
            self.assertEqual(result['modules'], [{'id':'coverage','name':'Coverage und Blind Spots','requires_model':False}])
            result = app.save(pid, {**opts, 'modules': ['information_loss']})
            self.assertEqual(result['modules'], [{'id':'information_loss','name':'Information-Loss-Audit','requires_model':False}])
            result = app.save(pid, {**opts, 'modules': ['codebook_diagnostics']})
            self.assertEqual(result['modules'], [{'id':'codebook_diagnostics','name':'Codebook-Diagnostik','requires_model':False}])

    def test_optional_order_waits_only_for_enabled_modules_without_requiring_success(self):
        raw = [{'id':'coverage','script':'coverage_analysis.py','after_if_enabled':['source','absent']},
               {'id':'source','script':'source.py'}]
        modules = RUNNER.normalize_modules({'pipeline':{'modules':raw}})
        self.assertEqual([m['id'] for m in RUNNER.topological_order(modules)], ['source','coverage'])
        self.assertEqual(modules[0]['depends_on'], [])
        modules[1]['enabled'] = False
        self.assertEqual([m['id'] for m in RUNNER.topological_order(modules)], ['coverage'])
        modules[0]['after_if_enabled'] = ['coverage']
        with self.assertRaisesRegex(ValueError,'Zyklische'):
            RUNNER.topological_order(modules)

    def test_actual_app_run_without_ollama_or_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetic coverage',True)['id']
            app.save(pid,{**settings(app),'modules':['coverage','information_loss','codebook_diagnostics'],'parallel_workers':8})
            # Starting a pure diagnostic must not even call provider/capacity checks.
            with patch.object(app,'authorize_llm',side_effect=AssertionError('No model needed')), \
                 patch('managed_ollama.preflight',side_effect=AssertionError('No GPU needed')):
                job=app.start(pid)
            deadline=time.monotonic()+20
            while app.active is not None and time.monotonic()<deadline:
                time.sleep(.05)
            self.assertIsNone(app.active, 'Diagnostic did not finish')
            jobs=app.jobs(pid)
            self.assertEqual(jobs[0]['status'],'success',jobs)
            path=app.artifact(pid,job['id'],'coverage.json')
            result=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(result['model_calls'],0)
            self.assertEqual(result['material']['material_units'],43)
            html=app.artifact(pid,job['id'],'gesamtbericht.html').read_text(encoding='utf-8')
            self.assertIn('Coverage und Blind Spots',html)
            self.assertIn('Information-Loss-Audit',html)
            loss=json.loads(app.artifact(pid,job['id'],'information_loss.json').read_text(encoding='utf-8'))
            self.assertEqual(loss['model_calls'],0)
            self.assertEqual(loss['material']['material_units'],43)
            self.assertEqual(loss['transitions'],[])
            self.assertIn('Keine analytischen Quellübergänge ausgewählt',html)
            self.assertIn('Codebook-Diagnostik',html)
            book=json.loads(app.artifact(pid,job['id'],'codebook_diagnostics.json').read_text(encoding='utf-8'))
            self.assertEqual(book['model_calls'],0)
            self.assertEqual(book['n_rows'],50)
            self.assertEqual(book['n_units'],43)
            self.assertIsNone(book['blind_unit_states'])


if __name__ == '__main__':
    unittest.main()
