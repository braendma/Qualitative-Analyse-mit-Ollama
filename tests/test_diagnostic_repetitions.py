import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from diagnostic_repetitions import prepare_repetitions
from runtime_support import file_hash


class Workspace:
    def __init__(self, directory):
        self.root=directory;self.path=directory/'base.yaml'
        self.config=yaml.safe_load((ROOT/'config/config_v2.yaml').read_text(encoding='utf-8'))
        self.config['paths'].update(input_csv='input.csv',category_system_csv='book.csv')
        self.config['columns']={'segment_id':'ID','person':'Person','code':'Code','segment':'Text'}
        self.config['coding_agreement']['label_mode']='unspecified'
        self.config['context']={};self.config['llm']['model']='mock'
        self.config['prompts']['cluster_analysis']={'system':'cluster_analysis','user':'{segments}'}
        self.config['prompts']['blind_coding']={'system':'blind_coding','user':'{"segment_id":"{segment_id}","segment":"{segment}"}'}
        (directory/'input.csv').write_text('ID;Person;Code;Text\ns1;P1;A > B > C > positiv;gut\ns2;P1;A > B > C > negativ;schlecht\n',encoding='utf-8')
        (directory/'book.csv').write_text('Code;Definition;Ankerbeispiel\nA > B > C > positiv;gut;gut\nA > B > C > negativ;schlecht;schlecht\n',encoding='utf-8')
        self.save()

    def save(self):
        self.path.write_text(yaml.safe_dump(self.config,allow_unicode=True),encoding='utf-8')

    def module(self, mid):
        return next(m for m in self.config['pipeline']['modules'] if m['id']==mid)


class RepetitionPlanTests(unittest.TestCase):
    def test_plan_keeps_inputs_parameters_and_identity_but_exposes_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));before={p:p.read_bytes() for p in w.root.iterdir()}
            plan=prepare_repetitions(w.path,['blind_coding'])
            self.assertEqual(plan['effective_modules'],['clusterer','blind_coding'])
            self.assertEqual(plan['added_prerequisites'],['clusterer'])
            self.assertEqual(plan['module_executions'],6)
            self.assertIsNone(plan['model_calls'])
            self.assertEqual(plan['config']['llm'],w.config['llm'])
            self.assertEqual(plan['config']['columns'],w.config['columns'])
            self.assertEqual(len({s['configuration_fingerprint'] for s in plan['samples']}),1)
            self.assertEqual(len({s['sample_id'] for s in plan['samples']}),3)
            self.assertEqual(plan['source_provenance']['input_sha256'],file_hash(w.root/'input.csv'))
            self.assertTrue(Path(plan['config']['paths']['input_csv']).is_absolute())
            self.assertEqual(plan['parameter_status'],'configured_not_runtime_verified')
            self.assertEqual(prepare_repetitions(w.path,['blind_coding']),plan)
            self.assertEqual({p:p.read_bytes() for p in w.root.iterdir()},before)

    def test_repetition_count_and_targets_fail_before_any_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            for value in (True,1,21,2.0,'3',None):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    prepare_repetitions(w.path,['blind_coding'],repetitions=value)
            for targets in ([],['blind_coding','blind_coding'],['coverage'],['stability'],['missing'],[None],'blind_coding'):
                with self.subTest(targets=targets),self.assertRaises(ValueError):
                    prepare_repetitions(w.path,targets)

    def test_no_hidden_activation_or_recursive_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));w.module('blind_coding')['enabled']=False;w.save()
            with self.assertRaisesRegex(ValueError,'aktiviert'):
                prepare_repetitions(w.path,['blind_coding'])
            w.module('blind_coding')['enabled']=True
            w.module('coverage')['enabled']=True;w.save()
            plan=prepare_repetitions(w.path,['blind_coding'])
            self.assertFalse(next(m for m in plan['config']['pipeline']['modules'] if m['id']=='coverage')['enabled'])
            w.config=plan['config'];w.save()
            with self.assertRaisesRegex(ValueError,'Verschachtelte'):
                prepare_repetitions(w.path,['blind_coding'])

    def test_shared_cache_or_external_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));baseline=copy.deepcopy(w.config)
            w.config['llm']['partial_checkpoint_dir']='shared';w.save()
            with self.assertRaisesRegex(ValueError,'partial_checkpoint_dir'):
                prepare_repetitions(w.path,['blind_coding'])
            for outside in ('../old.json',r'C:\old.json',r'\\server\share\old.json','/old.json','{output_dir}/old.json','workflow_manifest.json','file:stream','NUL.json'):
                w.config=copy.deepcopy(baseline);w.module('blind_coding')['outputs']=[outside];w.save()
                with self.subTest(path=outside),self.assertRaises(ValueError):
                    prepare_repetitions(w.path,['blind_coding'])
            for args in (['--checkpoint','../shared.json'],['--checkpoint=C:\\shared.json'],['--out-json'],['--out-json','--out-md','ok.md'],['--mock-responses-json','saved.json']):
                w.config=copy.deepcopy(baseline);w.module('blind_coding')['args']+=args;w.save()
                with self.subTest(args=args),self.assertRaises(ValueError):
                    prepare_repetitions(w.path,['blind_coding'])

    def test_fixed_relative_custom_outputs_remain_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));m=w.module('blind_coding')
            m['outputs']=['nested/blind.json'];m['args']=['--out-json','nested/blind.json','--checkpoint','own.json'];w.save()
            plan=prepare_repetitions(w.path,['blind_coding'])
            self.assertEqual(next(x for x in plan['config']['pipeline']['modules'] if x['id']=='blind_coding')['outputs'],['nested/blind.json'])

    def test_malformed_mapping_and_argument_types_have_validation_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));original=copy.deepcopy(w.config)
            for key in ('llm','paths','pipeline'):
                for value in (None,[],True,'wrong'):
                    w.config=copy.deepcopy(original);w.config[key]=value;w.save()
                    with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                        prepare_repetitions(w.path,['blind_coding'])
            for key,value in [('args','--out-json x.json'),('outputs','x.json'),('args',[None])]:
                w.config=copy.deepcopy(original);w.module('blind_coding')[key]=value;w.save()
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    prepare_repetitions(w.path,['blind_coding'])

    def test_keys_are_not_copied_and_provider_privacy_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));w.config['llm']['api_key']='SYNTHETIC_SECRET';w.save()
            with self.assertRaisesRegex(ValueError,'Schlüsselfeld'):
                prepare_repetitions(w.path,['blind_coding'])
            del w.config['llm']['api_key'];w.config['llm']['provider']='ollama_cloud';w.save()
            with self.assertRaisesRegex(ValueError,'Cloud gesperrt'):
                prepare_repetitions(w.path,['blind_coding'])
            w.config['llm']['gdpr_relevant']=False;w.save()
            plan=prepare_repetitions(w.path,['blind_coding'])
            self.assertEqual(plan['provider'],'ollama_cloud')
            self.assertFalse(plan['config']['llm']['gdpr_relevant'])

    def test_missing_inputs_invalid_dependency_or_custom_script_is_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));w.config['paths']['input_csv']='missing.csv';w.save()
            with self.assertRaisesRegex(ValueError,'nicht gefunden'):
                prepare_repetitions(w.path,['blind_coding'])
            w.config['paths']['input_csv']='input.csv';w.module('clusterer')['enabled']=False;w.save()
            with self.assertRaisesRegex(ValueError,'deaktiviert'):
                prepare_repetitions(w.path,['blind_coding'])
            w.module('clusterer')['enabled']=True;w.module('blind_coding')['script']='custom.py';w.save()
            with self.assertRaisesRegex(ValueError,'Modulskripte'):
                prepare_repetitions(w.path,['blind_coding'])

    def test_existing_runner_recomputes_independent_samples_but_reuses_own_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));plan=prepare_repetitions(w.path,['blind_coding'],repetitions=2)
            child=w.root/'child.yaml';child.write_text(yaml.safe_dump(plan['config']),encoding='utf-8')
            trace=w.root/'calls.jsonl'
            command=[sys.executable,str(ROOT/'tests/mock_pipeline.py'),'--config',str(child)]
            env={**os.environ,'PYTHONUTF8':'1','MPLBACKEND':'Agg','MOCK_TRACE_PATH':str(trace)}
            env.pop('MOCK_FAIL_MODULE',None);env.pop('MOCK_FAIL_AFTER',None)
            runs=[];counts=[]
            for sample in plan['samples']:
                parent=w.root/sample['sample_id']
                result=subprocess.run(command+['--output-dir',str(parent)],env=env,capture_output=True,text=True,encoding='utf-8')
                self.assertEqual(result.returncode,0,result.stderr[-2500:])
                runs.append(next(parent.iterdir()));counts.append(len(trace.read_text().splitlines()))
            self.assertEqual(counts[1],2*counts[0]);self.assertGreater(counts[0],0)
            manifests=[json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8')) for run in runs]
            self.assertNotEqual(manifests[0]['run_id'],manifests[1]['run_id'])
            self.assertEqual(manifests[0]['fingerprint'],manifests[1]['fingerprint'])
            self.assertTrue(all((run/'blind_coding_checkpoint.json').is_file() for run in runs))
            result=subprocess.run(command+['--resume',str(runs[1])],env=env,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr[-2500:])
            self.assertEqual(len(trace.read_text().splitlines()),counts[1])


if __name__=='__main__':unittest.main()
