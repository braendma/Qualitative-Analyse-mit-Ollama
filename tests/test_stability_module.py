import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_diagnostic_repetitions import Workspace, ROOT
from stability_analysis import configured_plan, planning_summary, main
from owned_workflow_process import run_owned


def enable_stability(w):
    w.config['pipeline']['modules']=[m for m in w.config['pipeline']['modules'] if m['id']!='stability']
    for module in w.config['pipeline']['modules']:
        module['enabled']=module['id'] in {'clusterer','blind_coding'}
    w.config['pipeline']['modules'].append({'id':'stability','name':'Stabilitätsanalyse','enabled':True,
        'script':'stability_analysis.py','requires_model':True,'starts_child_runs':True,
        'depends_on':[],'after_if_enabled':['clusterer','blind_coding'],
        'args':['--config','{config}','--input-csv','{input_csv}'],
        'outputs':['stability.json','stability.md'],
        'report':{'title':'Stabilitätsanalyse','markdown':'stability.md'}})
    w.config['diagnostics']={'stability':{'modules':['blind_coding'],'repetitions':2}}
    w.save()


class StabilityModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.w=Workspace(Path(self.tmp.name));enable_stability(self.w)
        self.output=self.w.root/'output';self.pause=self.w.root/'pause.flag'
        self.env={k:v for k,v in os.environ.items() if not k.startswith(('MOCK_','WORKFLOW_')) and k!='QUALITATIVE_MANAGED_OLLAMA_HOST'}
        self.env.update(MOCK_RUNTIME_EVIDENCE='1',PYTHONUTF8='1',MPLBACKEND='Agg')

    def run_workflow(self,*,resume=None,env=None,validate=False):
        command=[sys.executable,str(ROOT/'tests/mock_pipeline.py'),'--config',str(self.w.path),
                 '--output-dir',str(self.output),'--pause-file',str(self.pause)]
        if resume:command+=['--resume',str(resume)]
        if validate:command+=['--validate-only']
        # Combined stability/sensitivity starts six child workflows. On a cold
        # Windows CI host imports alone can exceed the old 45-second deadline.
        result=run_owned(command,env={**self.env,**(env or {})},directory=self.w.root,timeout=180)
        return result

    def run_dir(self):
        return next(self.output.iterdir())

    def test_nested_module_writes_comparison_and_complete_html(self):
        validation=self.run_workflow(validate=True)
        self.assertEqual(validation.returncode,0,validation.stderr)
        self.assertFalse(self.output.exists())
        summary=json.loads(validation.stdout)['stability_plan']
        self.assertEqual(summary['module_executions'],4)
        self.assertIsNone(summary['model_calls'])
        run=self.run_workflow()
        self.assertEqual(run.returncode,0,run.stderr)
        root=self.run_dir()
        result=json.loads((root/'stability.json').read_text(encoding='utf-8'))
        self.assertEqual(result['series_status'],'success')
        self.assertTrue(result['comparisons']['blind_coding']['runtime_comparison']['parameter_profiles_same'])
        manifest=json.loads((root/'workflow_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['status'],'success')
        self.assertIn('stability',manifest['completed_steps'])
        self.assertIn('Stabilitätsanalyse',(root/'gesamtbericht.html').read_text(encoding='utf-8'))
        self.assertIn('Stabilität bei wiederholter Analyse',(root/'stability.md').read_text(encoding='utf-8'))
        before=(root/'stability.json').read_bytes()
        self.assertEqual(self.run_workflow(resume=root).returncode,0)
        self.assertEqual((root/'stability.json').read_bytes(),before)

    def test_safe_pause_is_not_failure_and_resume_reuses_completed_child(self):
        result=self.run_workflow(env={'MOCK_PAUSE_AFTER_FIRST_REPETITION':'1'})
        self.assertEqual(result.returncode,0,result.stderr)
        root=self.run_dir();manifest=json.loads((root/'workflow_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['status'],'paused')
        self.assertNotIn('stability',manifest['completed_steps'])
        self.assertNotIn('stability.json',manifest['output_hashes'])
        partial=json.loads((root/'stability.json').read_text(encoding='utf-8'))
        self.assertEqual(partial['series_status'],'paused')
        self.assertEqual(partial['processing_status'],'incomplete')
        child=next((root/'_stability_repetitions'/'repeat-001').iterdir())
        child_manifest=(child/'workflow_manifest.json').read_bytes()
        self.assertFalse((root/'_stability_repetitions'/'repeat-002').exists())
        self.pause.unlink()
        result=self.run_workflow(resume=root)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((child/'workflow_manifest.json').read_bytes(),child_manifest)
        self.assertEqual(json.loads((root/'workflow_manifest.json').read_text(encoding='utf-8'))['status'],'success')

    def test_invalid_plan_is_rejected_before_output_or_model_start(self):
        for change in ({'modules':[]},{'modules':['stability']},{'repetitions':True},{'repetitions':21}):
            old=copy.deepcopy(self.w.config)
            self.w.config['diagnostics']['stability'].update(change);self.w.save()
            result=self.run_workflow(validate=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(self.output.exists())
            self.w.config=old;self.w.save()
        self.w.module('stability')['enabled']=False;self.w.config['diagnostics']='ignored when off';self.w.save()
        self.assertIsNone(configured_plan(self.w.path))

    def test_direct_cli_cannot_overwrite_internal_series_files(self):
        root=self.w.root
        (root/'workflow_manifest.json').write_text('{}',encoding='utf-8')
        with patch('stability_analysis._analyze',side_effect=AssertionError('No model calls before validation')):
            with self.assertRaisesRegex(ValueError,'Serienverzeichnisse'):
                main(['--config',str(self.w.path),'--input-csv',str(root/'input.csv'),'--run-dir',str(root),
                      '--out-json',str(root/'_stability_repetitions'/'repetition_plan.json'),'--out-md',str(root/'new.md')])
        self.assertFalse((root/'_stability_repetitions').exists())

    def test_pause_exit_only_valid_for_modules_owning_child_runs(self):
        runner=importlib.import_module('00_WORKFLOW_RUNNER')
        module={'id':'test','name':'Test','outputs':[],'starts_child_runs':True}
        with patch.object(runner.subprocess,'run',return_value=type('Result',(),{'returncode':75})()):
            with self.assertRaises(runner.ModulePaused):runner.run_step(module,['unused'],self.w.root)
            module['starts_child_runs']=False
            with self.assertRaises(Exception) as caught:runner.run_step(module,['unused'],self.w.root)
            self.assertNotIsInstance(caught.exception,runner.ModulePaused)


if __name__=='__main__':unittest.main()
