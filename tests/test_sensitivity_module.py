import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_stability_module as stability
from test_diagnostic_repetitions import Workspace
from sensitivity_analysis import configured_plan, main


def enable_sensitivity(w):
    stability.enable_stability(w)
    w.config['pipeline']['modules']=[m for m in w.config['pipeline']['modules'] if m['id']!='sensitivity']
    module=w.module('stability')
    module.update(id='sensitivity',name='Sensitivitätsanalyse',script='sensitivity_analysis.py',
                  outputs=['sensitivity.json','sensitivity.md'],report={'title':'Sensitivitätsanalyse','markdown':'sensitivity.md'})
    w.config['diagnostics']={'sensitivity':{'modules':['blind_coding'],'repetitions':2,
        'variants':[{'id':'warm','llm':{'temperature':0.2}}]}}
    w.save()


class SensitivityModuleTests(unittest.TestCase):
    run_workflow=stability.StabilityModuleTests.run_workflow
    run_dir=stability.StabilityModuleTests.run_dir

    def setUp(self):
        stability.StabilityModuleTests.setUp(self)
        enable_sensitivity(self.w)

    def test_nested_module_preflight_complete_report_and_resume(self):
        validation=self.run_workflow(validate=True)
        self.assertEqual(validation.returncode,0,validation.stderr)
        summary=json.loads(validation.stdout)['sensitivity_plan']
        self.assertEqual(summary['configuration_count'],2)
        self.assertEqual(summary['total_repetitions'],4)
        self.assertEqual(summary['module_executions'],8)
        self.assertFalse(self.output.exists())
        run=self.run_workflow()
        self.assertEqual(run.returncode,0,run.stderr)
        root=self.run_dir()
        result=json.loads((root/'sensitivity.json').read_text(encoding='utf-8'))
        self.assertEqual(result['series_status'],'success')
        self.assertEqual(result['processing_status'],'completed')
        self.assertEqual(len(result['conditions']),4)
        self.assertIn('Schwankungen innerhalb jeder Einstellung',(root/'gesamtbericht.html').read_text(encoding='utf-8'))
        self.assertIn('sensitivity',json.loads((root/'workflow_manifest.json').read_text())['completed_steps'])
        before=(root/'sensitivity.json').read_bytes()
        resumed=self.run_workflow(resume=root)
        self.assertEqual(resumed.returncode,0,resumed.stderr)
        self.assertEqual((root/'sensitivity.json').read_bytes(),before)

    def test_pause_preserves_completed_baseline_and_resumes(self):
        run=self.run_workflow(env={'MOCK_PAUSE_AFTER_FIRST_REPETITION':'1'})
        self.assertEqual(run.returncode,0,run.stderr)
        root=self.run_dir();manifest=json.loads((root/'workflow_manifest.json').read_text())
        self.assertEqual(manifest['status'],'paused')
        self.assertNotIn('sensitivity.json',manifest['output_hashes'])
        partial=json.loads((root/'sensitivity.json').read_text(encoding='utf-8'))
        self.assertEqual(partial['series_status'],'paused')
        child=next((root/'_sensitivity_repetitions'/'baseline-repeat-001').iterdir())
        before=(child/'workflow_manifest.json').read_bytes()
        self.pause.unlink()
        resumed=self.run_workflow(resume=root)
        self.assertEqual(resumed.returncode,0,resumed.stderr)
        self.assertEqual((child/'workflow_manifest.json').read_bytes(),before)

    def test_invalid_changes_fail_before_output_or_dispatch_and_off_is_ignored(self):
        for variants in ([],[{'id':'same','llm':{'temperature':0.05}}],
                         [{'id':'secret','llm':{'api_key':'not-a-real-key'}}]):
            self.w.config['diagnostics']['sensitivity']['variants']=variants;self.w.save()
            result=self.run_workflow(validate=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(self.output.exists())
        self.w.module('sensitivity')['enabled']=False
        self.w.config['diagnostics']='ignored when off';self.w.save()
        self.assertIsNone(configured_plan(self.w.path))

    def test_direct_cli_cannot_replace_internal_series_receipt(self):
        root=self.w.root;(root/'workflow_manifest.json').write_text('{}')
        with patch('stability_analysis._analyze',side_effect=AssertionError('No dispatch')):
            with self.assertRaisesRegex(ValueError,'Serienverzeichnisse'):
                main(['--config',str(self.w.path),'--input-csv',str(root/'input.csv'),'--run-dir',str(root),
                      '--out-json',str(root/'_sensitivity_repetitions'/'repetition_plan.json'),'--out-md',str(root/'report.md')])
        self.assertFalse((root/'_sensitivity_repetitions').exists())

    def test_stability_and_sensitivity_together_keep_separate_series(self):
        module=copy.deepcopy(self.w.module('sensitivity'))
        module.update(id='stability',name='Stabilitätsanalyse',script='stability_analysis.py',
            outputs=['stability.json','stability.md'],report={'title':'Stabilitätsanalyse','markdown':'stability.md'})
        self.w.config['pipeline']['modules'].append(module)
        self.w.module('sensitivity')['after_if_enabled'].append('stability')
        self.w.config['diagnostics']['stability']={'modules':['blind_coding'],'repetitions':2};self.w.save()
        run=self.run_workflow()
        self.assertEqual(run.returncode,0,run.stderr)
        root=self.run_dir()
        stable=json.loads((root/'stability.json').read_text(encoding='utf-8'))
        sensitive=json.loads((root/'sensitivity.json').read_text(encoding='utf-8'))
        self.assertEqual(len(stable['conditions']),2)
        self.assertEqual(len(sensitive['conditions']),4)
        self.assertTrue((root/'_stability_repetitions').is_dir())
        self.assertTrue((root/'_sensitivity_repetitions').is_dir())
        manifests=list(root.glob('_*repetitions/*/*/workflow_manifest.json'))
        self.assertEqual(len({json.loads(p.read_text())['run_id'] for p in manifests}),6)


if __name__=='__main__':unittest.main()
