import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_diagnostic_repetitions import Workspace, ROOT
import diagnostic_series as series
from diagnostic_repetitions import prepare_repetitions
from runtime_support import atomic_json, exclusive_file_lock
from stability_series import load_stability_series, _request_profiles
from stability_report import render_stability


class StabilitySeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = Workspace(Path(self.tmp.name))
        self.plan = prepare_repetitions(self.w.path, ['blind_coding'], repetitions=2)
        self.root = self.w.root / 'series'
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('MOCK_', 'WORKFLOW_')) and k != 'QUALITATIVE_MANAGED_OLLAMA_HOST'}
        env.update(MOCK_RUNTIME_EVIDENCE='1', MPLBACKEND='Agg')
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, env, clear=True).start()
        patch.object(series, '_runner_command', return_value=[sys.executable, str(ROOT/'tests/mock_pipeline.py')]).start()

    def test_real_series_reads_without_dispatch_and_rejects_tampering(self):
        self.assertEqual(series.execute_repetitions(self.plan, self.root)['status'], 'success')
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(series, '_execute', side_effect=AssertionError('Must not dispatch')):
            result = load_stability_series(self.root)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(result['processing_status'], 'completed')
        comparison = result['comparisons']['blind_coding']
        self.assertEqual(comparison['provenance_status'], 'series_and_artifact_hashes_verified')
        self.assertTrue(comparison['runtime_comparison']['parameter_profiles_same'])
        self.assertEqual(result['local_digests'], ['a' * 64])
        self.assertEqual(comparison['pairs'][0]['code_set_agreement']['value'], 1)
        rendered=render_stability(result)
        self.assertIn('Exakte Code-Mengenübereinstimmung: 2/2 (100.0%)',rendered)
        self.assertIn('Tatsächlich übertragene Parameter',rendered)
        self.assertIn('num\\_predict',rendered)
        run = self.root / result['conditions'][0]['run_dir']
        manifest = json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
        artifact = next(m for m in self.plan['config']['pipeline']['modules'] if m['id']=='blind_coding')['outputs'][0]
        targets = [self.root/'repetition_config.yaml', self.root/'repetition_plan.json',
                   run/'workflow_manifest.json', run/artifact,
                   run/'_runtime_evidence'/next(iter(manifest['runtime_evidence']['files'])),
                   self.root/'repeat-001.supervision.json', self.w.root/'input.csv']
        for target in targets:
            with self.subTest(target=target.name):
                saved = target.read_bytes()
                try:
                    target.write_bytes(b'{}')
                    with self.assertRaises((ValueError, KeyError)):
                        load_stability_series(self.root)
                finally:
                    target.write_bytes(saved)
        # The convenience index cannot override manifest evidence or inject a run.
        (self.root/'repetition_index.json').write_text('{"samples":[{"run_dir":"../foreign"}]}',encoding='utf-8')
        self.assertEqual(load_stability_series(self.root)['comparisons'], result['comparisons'])
        original_profiles=_request_profiles
        def changed_digest(run,manifest,plan,modules):
            profile=original_profiles(run,manifest,plan,modules)
            if run.parent.name=='repeat-002':profile['local_digests']=['b'*64]
            return profile
        with patch('stability_series._request_profiles',side_effect=changed_digest):
            with self.assertRaisesRegex(ValueError,'Modellgewichte'):
                load_stability_series(self.root)
        with exclusive_file_lock(self.root/'.series.lock'):
            with self.assertRaises((ValueError, OSError, RuntimeError)):
                load_stability_series(self.root)

    def test_failure_and_pending_remain_excluded_and_can_later_resume(self):
        with patch.dict(os.environ, {'MOCK_FAIL_MODULE': 'blind_coding', 'MOCK_FAIL_AFTER': '1'}):
            self.assertEqual(series.execute_repetitions(self.plan,self.root)['status'], 'failed')
        result = load_stability_series(self.root)
        self.assertEqual([c['status'] for c in result['conditions']], ['failed', 'pending'])
        guidance = result['conditions'][0]['failure_guidance']
        self.assertEqual([g['module'] for g in guidance], ['blind_coding'])
        self.assertTrue(all(g['cause'] and g['action'] for g in guidance))
        self.assertIn('Fehlerhilfe:', render_stability(result))
        self.assertNotIn('failure_guidance', result['conditions'][1])
        self.assertTrue(all(r['comparison_status']=='not_computable' for r in result['comparisons'].values()))
        self.assertIn('kein Stabilitätsvergleich möglich',render_stability(result))
        # Even the completed prerequisite of an unsuccessful repetition is excluded.
        self.assertEqual(result['comparisons']['clusterer']['included_samples'], [])
        self.assertEqual(series.execute_repetitions(self.plan,self.root,resume=True)['status'], 'success')
        self.assertEqual(load_stability_series(self.root)['processing_status'], 'completed')

    def test_no_receipts_never_claim_runtime_identity(self):
        with patch.dict(os.environ, {'MOCK_RUNTIME_EVIDENCE': '0'}):
            self.assertEqual(series.execute_repetitions(self.plan,self.root)['status'], 'success')
        result = load_stability_series(self.root)
        self.assertIsNone(result['comparisons']['blind_coding']['runtime_comparison']['parameter_profiles_same'])
        self.assertEqual(result['local_digests'], [])


class RuntimeProfileTests(unittest.TestCase):
    def test_whitelisted_profiles_group_counts_and_keep_repairs_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'_runtime_evidence').mkdir()
            plan={'provider':'ollama_local','config':{'llm':{'model':'mock'}}}
            receipt={'module':'blind_coding','provider':'ollama_local','model':'mock',
                     'status':'accepted','parameter_status':'request_accepted',
                     'model_before':{'digest':'a'*64},'model_after':{'digest':'a'*64},
                     'parameters_sent':{'options':{'num_predict':2048},'think':False},
                     'observed_context_length':16384,
                     'accidental_extra':'Never copy arbitrary receipt fields'}
            files={}
            for i,limit in enumerate((2048,2048,4096)):
                value=copy.deepcopy(receipt); value['parameters_sent']['options']['num_predict']=limit
                name=f'{i:032x}.json'; atomic_json(root/'_runtime_evidence'/name,value);files[name]='already_checked'
            manifest={'runtime_evidence':{'files':files}}
            result=_request_profiles(root,manifest,plan,{'blind_coding':{}})
            self.assertEqual(sorted(p['accepted_requests'] for p in result['profiles']),[1,2])
            self.assertNotIn('Never copy',json.dumps(result))
            target=root/'_runtime_evidence'/next(iter(files))
            for field,value in [('provider','openai'),('model','foreign'),('model_after',{'digest':'b'*64}),
                                ('parameters_sent',{'options':{'prompt':'SECRET'}}),('observed_context_length',True)]:
                altered=copy.deepcopy(receipt);altered[field]=value;atomic_json(target,altered)
                with self.subTest(field=field),self.assertRaises(ValueError):
                    _request_profiles(root,manifest,plan,{'blind_coding':{}})
                atomic_json(target,receipt)


if __name__ == '__main__':
    unittest.main()
