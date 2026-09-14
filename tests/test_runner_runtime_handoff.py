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
from diagnostic_repetitions import prepare_repetitions

runner=importlib.import_module('00_WORKFLOW_RUNNER')


class HandoffTests(unittest.TestCase):
    def test_actual_nested_repetitions_receive_released_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));trace=w.root/'runtime.log'
            for m in w.config['pipeline']['modules']:m['enabled']=m['id'] in ('clusterer','blind_coding')
            w.config['pipeline']['modules'].append({'id':'child_probe','script':'../tests/child_series_probe.py',
                'enabled':True,'requires_model':True,'starts_child_runs':True,'depends_on':['blind_coding'],
                'args':['--config','{config}'],'outputs':['child_series_result.json']})
            w.save()
            env={**{k:v for k,v in os.environ.items() if not k.startswith('MOCK_')},
                 'MOCK_RUNTIME_TRACE':str(trace),'PYTHONUTF8':'1','MPLBACKEND':'Agg'}
            result=subprocess.run([sys.executable,str(ROOT/'tests/mock_pipeline.py'),'--config',str(w.path),
                '--output-dir',str(w.root/'runs')],env=env,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr[-3500:])
            run=next((w.root/'runs').iterdir());nested=json.loads((run/'child_series_result.json').read_text())
            self.assertEqual(nested['completed_samples'],2)
            events=trace.read_text().splitlines()
            self.assertEqual(events.count('start'),3)
            self.assertEqual(events.count('close'),3)
            self.assertIn('child_series_probe:False',events)

    def test_release_before_child_module_and_lazy_restart_afterward(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));trace=w.root/'runtime.log'
            for m in w.config['pipeline']['modules']:m['enabled']=m['id'] in ('clusterer','summarizer')
            probe=copy.deepcopy(w.module('clusterer'))
            probe.update(id='child_probe',name='Synthetic child dispatch',starts_child_runs=True,
                         requires_model=True,depends_on=['clusterer'],after_if_enabled=[])
            replacements={name:'child_'+name for name in probe['outputs']}
            replacements['plots']='child_plots'
            probe['outputs']=[replacements[name] for name in probe['outputs']]
            probe['args']=[replacements.get(arg,arg) for arg in probe['args']]
            w.config['pipeline']['modules'].append(probe)
            w.module('summarizer')['depends_on']=['child_probe']
            w.config['prompts']['cluster_summary']={'system':'cluster_summary','user':'{clusters}'}
            w.config['prompts']['category_summary']={'system':'category_summary','user':'{subcats}'}
            w.save()
            env={**os.environ,'MOCK_RUNTIME_TRACE':str(trace),'PYTHONUTF8':'1','MPLBACKEND':'Agg'}
            for key in ('MOCK_BLOCK_SIGNAL','MOCK_FAIL_MODULE','MOCK_RUNTIME_EVIDENCE'):env.pop(key,None)
            command=[sys.executable,str(ROOT/'tests/mock_pipeline.py'),'--config',str(w.path),'--output-dir',str(w.root/'runs')]
            result=subprocess.run(command,env=env,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr[-3000:])
            self.assertEqual(trace.read_text().splitlines(),['start','clusterer:True','close','clusterer:False','start','summarizer:True','close'])
            run=next((w.root/'runs').iterdir())
            manifest=json.loads((run/'workflow_manifest.json').read_text())
            self.assertEqual(len(manifest['ollama_runtime_sessions']),2)
            before=trace.read_bytes()
            result=subprocess.run(command+['--resume',str(run)],env=env,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr[-3000:])
            self.assertEqual(trace.read_bytes(),before,'Completed resume must not start a model runtime')

    def test_child_run_contract_and_recursion_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));original=copy.deepcopy(w.config)
            for flag,needs_model in (('true',True),(True,False)):
                w.config=copy.deepcopy(original);w.module('clusterer').update(starts_child_runs=flag,requires_model=needs_model)
                with self.assertRaises(ValueError):runner.normalize_modules(w.config)
            w.config=original;w.module('clusterer')['starts_child_runs']=True;w.save()
            with self.assertRaisesRegex(ValueError,'Unterläufen'):prepare_repetitions(w.path,['clusterer'])


if __name__=='__main__':unittest.main()
