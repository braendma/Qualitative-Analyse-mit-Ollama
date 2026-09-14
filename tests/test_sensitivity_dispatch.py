import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_diagnostic_repetitions import Workspace, ROOT
from diagnostic_sensitivity import prepare_sensitivity
import diagnostic_series as series


class SensitivityDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.w=Workspace(Path(self.tmp.name));self.root=self.w.root/'series'
        self.trace=self.w.root/'trace.jsonl'
        self.plan=prepare_sensitivity(self.w.path,['blind_coding'],[{'id':'warm','llm':{'temperature':0.2}}])
        env={k:v for k,v in os.environ.items() if not k.startswith(('MOCK_','WORKFLOW_')) and k!='QUALITATIVE_MANAGED_OLLAMA_HOST'}
        env.update(MOCK_TRACE_PATH=str(self.trace),MOCK_RUNTIME_EVIDENCE='1',MPLBACKEND='Agg')
        self.env=patch.dict(os.environ,env,clear=True);self.env.start();self.addCleanup(self.env.stop)
        self.cmd=patch.object(series,'_runner_command',return_value=[sys.executable,str(ROOT/'tests/mock_pipeline.py')])
        self.cmd.start();self.addCleanup(self.cmd.stop)

    def execute(self,**kwargs):
        return series.execute_repetitions(self.plan,self.root,**kwargs)

    def manifest(self,sid):
        run=next((self.root/sid).iterdir())
        return run,json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))

    def test_real_children_isolate_conditions_and_resume_without_new_requests(self):
        result=self.execute()
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['completed_samples'],4)
        manifests=[self.manifest(s['sample_id'])[1] for s in self.plan['samples']]
        self.assertEqual(len({m['run_id'] for m in manifests}),4)
        self.assertEqual(manifests[0]['fingerprint'],manifests[1]['fingerprint'])
        self.assertNotEqual(manifests[1]['fingerprint'],manifests[2]['fingerprint'])
        self.assertEqual(manifests[2]['fingerprint'],manifests[3]['fingerprint'])
        for sample in result['samples']:
            self.assertGreater(sample['runtime_evidence']['accepted'],0)
            run,manifest=self.manifest(sample['sample_id'])
            expected=0.05 if sample['configuration_id']=='baseline' else 0.2
            receipts=[json.loads((run/'_runtime_evidence'/name).read_text(encoding='utf-8'))
                      for name in manifest['runtime_evidence']['files']]
            self.assertTrue(any(r['parameters_sent']['options']['temperature']==expected for r in receipts))
        before=self.trace.read_bytes()
        with patch.object(series,'_execute',side_effect=AssertionError('Unexpected dispatch')):
            self.assertEqual(self.execute(resume=True)['status'],'success')
        self.assertEqual(self.trace.read_bytes(),before)

    def test_new_model_may_change_digest_but_same_model_may_not(self):
        self.plan=prepare_sensitivity(self.w.path,['blind_coding'],[{'id':'other','llm':{'model':'other-model'}}])
        original=series._execute
        def different_model(command,directory,log,env):
            if 'configuration-other.yaml' in command[command.index('--config')+1]:
                env={**env,'MOCK_MODEL_DIGEST':'b'*64,'MOCK_MODEL_NAME':'other-model:latest'}
            return original(command,directory,log,env)
        with patch.object(series,'_execute',side_effect=different_model):
            result=self.execute()
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['samples'][0]['runtime_evidence']['local_digests'],['a'*64])
        self.assertEqual(result['samples'][2]['runtime_evidence']['local_digests'],['b'*64])

    def test_same_model_digest_cannot_drift_when_temperature_changes(self):
        original=series._execute
        def drift(command,directory,log,env):
            if 'configuration-warm.yaml' in command[command.index('--config')+1]:
                env={**env,'MOCK_MODEL_DIGEST':'b'*64}
            return original(command,directory,log,env)
        with patch.object(series,'_execute',side_effect=drift):
            result=self.execute()
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['completed_samples'],2)
        self.assertFalse((self.root/'warm-repeat-002').exists())

    def test_failed_variant_preserves_successful_baseline_and_resumes_same_child(self):
        original=series._execute
        def fail_variant(command,directory,log,env):
            if 'configuration-warm.yaml' in command[command.index('--config')+1]:
                env={**env,'MOCK_FAIL_MODULE':'blind_coding'}
            return original(command,directory,log,env)
        with patch.object(series,'_execute',side_effect=fail_variant):
            failed=self.execute()
        self.assertEqual(failed['status'],'failed')
        self.assertEqual(failed['completed_samples'],2)
        baseline_run,baseline=self.manifest('baseline-repeat-001')
        unchanged=(baseline_run/'workflow_manifest.json').read_bytes()
        _,before=self.manifest('warm-repeat-001')
        self.assertFalse((self.root/'warm-repeat-002').exists())
        self.assertEqual(self.execute(resume=True)['status'],'success')
        self.assertEqual(self.manifest('warm-repeat-001')[1]['run_id'],before['run_id'])
        self.assertEqual((baseline_run/'workflow_manifest.json').read_bytes(),unchanged)

    def test_pause_and_tampered_variant_rejected_before_dispatch(self):
        pause=self.w.root/'pause';pause.touch()
        with patch.object(series,'_execute',side_effect=AssertionError('Unexpected dispatch')):
            self.assertEqual(self.execute(pause_file=pause)['status'],'paused')
            path=self.root/'configuration-warm.yaml'
            path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'verändert'):
                self.execute(resume=True)


if __name__=='__main__':unittest.main()
