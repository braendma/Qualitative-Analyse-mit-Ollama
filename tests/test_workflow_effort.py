import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_diagnostic_repetitions import Workspace, ROOT
from test_local_app import settings
from local_app import App, read_json
from stability_analysis import configured_plan, planning_summary
from workflow_effort import effort_summary

runner = importlib.import_module('00_WORKFLOW_RUNNER')
DIAGNOSTICS = ['coverage', 'information_loss', 'codebook_diagnostics', 'stability', 'sensitivity']


class WorkflowEffortTests(unittest.TestCase):
    def test_actual_plans_count_shared_prerequisites_once_per_run_and_keep_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Workspace(Path(tmp))
            for m in w.config['pipeline']['modules']:
                m['enabled'] = m['id'] in DIAGNOSTICS + ['clusterer', 'blind_coding']
            w.config['diagnostics'] = {'stability': {'modules': ['blind_coding'], 'repetitions': 3},
                'sensitivity': {'modules': ['blind_coding'], 'repetitions': 2,
                    'variants': [{'id': 'warm', 'llm': {'temperature': .2}}]}}
            w.save()
            before = w.path.read_bytes()
            modules = runner.topological_order(runner.normalize_modules(w.config))
            result = effort_summary(modules, **{kind: planning_summary(configured_plan(w.path, kind=kind))
                                    for kind in ('stability', 'sensitivity')})
            self.assertEqual(result['main_module_executions'], 7)
            self.assertEqual(result['additional_module_executions'], 14)
            self.assertEqual(result['total_module_executions'], 21)
            self.assertIsNone(result['model_calls_estimate'])
            for mid in ('clusterer', 'blind_coding'):
                row = next(r for r in result['modules'] if r['id'] == mid)
                self.assertEqual((row['main'], row['stability'], row['sensitivity'], row['total']), (1, 3, 4, 8))
            self.assertEqual(w.path.read_bytes(), before)
            self.assertFalse((w.root / 'output').exists())

    def test_app_and_cli_validation_produce_the_same_counts_without_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp)
            project = app.create('Künstlicher Aufwandtest', demo=True)
            options = settings(app)
            options.update(modules=DIAGNOSTICS + ['blind_coding'],
                stability={'modules': ['blind_coding'], 'repetitions': 3},
                sensitivity={'modules': ['blind_coding'], 'repetitions': 2,
                    'variants': [{'id': 'warm', 'llm': {'temperature': .2}}]})
            result = app.save(project['id'], options)
            directory = app.project_dir(project['id'])
            revision = read_json(directory / 'project.json')['revision']
            config = directory / 'revisions' / revision / 'config.yaml'
            cmd = [sys.executable, str(ROOT / 'src/00_WORKFLOW_RUNNER.py'), '--config', str(config), '--validate-only']
            done = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                  env={**os.environ, 'PYTHONUTF8': '1'}, timeout=40)
            self.assertEqual(done.returncode, 0, done.stderr)
            cli = json.loads(done.stdout)
            self.assertEqual(cli['effort'], result['effort'])
            self.assertEqual(cli['effort']['total_module_executions'], 21)
            self.assertEqual(cli['model_calls'], 0)
            self.assertEqual(app.jobs(project['id']), [])
            self.assertEqual(read_json(directory / 'settings.json')['sensitivity'], options['sensitivity'])

    def test_model_free_selection_does_not_plan_repetitions_or_need_valid_disabled_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(tmp); project = app.create('Künstliche Bestandsprüfung', demo=True)
            options = settings(app)
            options.update(modules=DIAGNOSTICS[:3], stability='disabled invalid draft', sensitivity=None)
            result = app.save(project['id'], options)['effort']
            self.assertEqual(result['total_module_executions'], 3)
            self.assertEqual(result['model_calls_estimate'], 0)
            self.assertEqual(result['series'], [])
            self.assertFalse(any(m['enabled'] for m in app.template['pipeline']['modules'] if m['id'] in DIAGNOSTICS))

    def test_unknown_child_extension_prevents_a_false_exact_total(self):
        modules = [{'id': 'custom', 'name': 'Eigene Erweiterung', 'starts_child_runs': True, 'requires_model': True}]
        result = effort_summary(modules)
        self.assertEqual(result['known_module_executions'], 1)
        self.assertIsNone(result['total_module_executions'])
        self.assertEqual(result['unplanned_child_modules'], ['custom'])
        self.assertIsNone(result['modules'][0]['cost_profile'])

    def test_inconsistent_internal_plan_cannot_claim_a_valid_execution_count(self):
        modules = [{'id': 'clusterer', 'name': 'Cluster'}, {'id': 'stability', 'name': 'Stabilität'}]
        plan = {'repetitions': 3, 'effective_modules': ['clusterer'], 'module_executions': 3}
        for change in ({'module_executions': 6}, {'repetitions': '3'}, {'configuration_count': True},
                       {'effective_modules': ['clusterer', 'clusterer']}, {'effective_modules': ['stability']}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                effort_summary(modules, stability={**plan, **change})


if __name__ == '__main__':
    unittest.main()
