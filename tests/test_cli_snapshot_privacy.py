"""CLI snapshots reject credential fields before material, output or model access."""
import copy
import importlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from types import SimpleNamespace

from provider_keys import reject_config_secrets
from diagnostic_repetitions import prepare_repetitions
from test_diagnostic_repetitions import Workspace, ROOT

runner = importlib.import_module('00_WORKFLOW_RUNNER')


class SnapshotPrivacyTests(unittest.TestCase):
    def test_cli_cloud_consent_checked_before_new_files_only_for_model_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            for key in ('provider','host','gdpr_relevant'):w.config['llm'].pop(key,None)
            for m in w.config['pipeline']['modules']:m['enabled']=m['id'] in ('clusterer','blind_coding')
            w.save();out=w.root/'out'
            with patch.dict(os.environ,{'OLLAMA_HOST':'https://ollama.com','OLLAMA_API_KEY':'SYNTHETIC_SECRET'}):
                for extra in ([],['--validate-only']):
                    with self.assertRaisesRegex(ValueError,'Cloud gesperrt'):
                        runner.main(['--config',str(w.path),'--output-dir',str(out),*extra])
                    self.assertFalse(out.exists())
                for m in w.config['pipeline']['modules']:m['enabled']=m['id']=='coverage'
                w.config['llm']['parallel_workers']=2
                w.save()
                with redirect_stdout(io.StringIO()):runner.main(['--config',str(w.path),'--validate-only'])

    def test_ordinary_module_process_gets_only_selected_key_and_keeps_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);module={'id':'probe','name':'Synthetic probe','outputs':[]}
            environment={'OPENAI_API_KEY':'SYNTHETIC_OPENAI','ANTHROPIC_API_KEY':'SYNTHETIC_OTHER',
                'SYNTHETIC_CUSTOM_KEY':'SYNTHETIC_SELECTED','WORKFLOW_RUN_ID':'run','PATH':os.environ.get('PATH','')}
            with patch.dict(os.environ,environment,clear=True), patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as execute:
                token=runner.STEP_TRANSPORT.set({'provider':'openai','api_key_env':'SYNTHETIC_CUSTOM_KEY'})
                try:runner.run_step(module,['synthetic'],folder)
                finally:runner.STEP_TRANSPORT.reset(token)
                env=execute.call_args.kwargs['env']
                self.assertEqual(env['SYNTHETIC_CUSTOM_KEY'],'SYNTHETIC_SELECTED')
                self.assertNotIn('OPENAI_API_KEY',env);self.assertNotIn('ANTHROPIC_API_KEY',env)
                self.assertEqual(env['WORKFLOW_RUN_ID'],'run');self.assertEqual(env['PATH'],environment['PATH'])
                self.assertIsNone(runner.STEP_TRANSPORT.get())
            for path in folder.iterdir():self.assertNotIn(b'SYNTHETIC_SELECTED',path.read_bytes())

    def test_cli_rejects_secrets_before_snapshot_or_model_for_validation_and_start(self):
        for mid in ('coverage', 'blind_coding'):
            for validate in (True, False):
                for field in ('api_key', 'nested'):
                    with self.subTest(mid=mid, validate=validate, field=field), tempfile.TemporaryDirectory() as tmp:
                        w=Workspace(Path(tmp))
                        for m in w.config['pipeline']['modules']:m['enabled']=m['id']==mid
                        if field=='api_key':w.config['llm']['api_key']='SYNTHETIC_SECRET_NEVER_WRITE'
                        else:w.config['extra']={'entries':[{'credential':'SYNTHETIC_SECRET_NEVER_WRITE'}]}
                        w.save();before=w.path.read_bytes();output=w.root/'no-run'
                        args=['--config',str(w.path),'--output-dir',str(output)]
                        if validate:args.append('--validate-only')
                        with patch.object(runner,'execution_provenance',side_effect=AssertionError('Provenance reached')), \
                                patch('managed_ollama.ManagedOllama.start',side_effect=AssertionError('Model reached')):
                            with self.assertRaises(ValueError) as caught:runner.main(args)
                        self.assertNotIn('SYNTHETIC_SECRET_NEVER_WRITE',str(caught.exception))
                        self.assertFalse(output.exists());self.assertEqual(before,w.path.read_bytes())

    def test_direct_provenance_and_repetition_plan_cannot_bypass_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));w.config['llm']['authorization']='SYNTHETIC_SECRET';w.save()
            with patch.object(runner,'file_hash',side_effect=AssertionError('Input access reached')):
                with self.assertRaises(ValueError):runner.execution_provenance(w.path,w.root/'input.csv',w.config)
            with self.assertRaises(ValueError):prepare_repetitions(w.path,['blind_coding'],repetitions=2)
            self.assertEqual({p.name for p in w.root.iterdir()},{'base.yaml','input.csv','book.csv'})

    def test_only_exact_environment_name_slot_is_exempt_without_mutation(self):
        cfg={'llm':{'api_key_env':'SYNTHETIC_KEY_SOURCE','max_tokens':2048},'ordinary':[{'tokens':12}]}
        before=copy.deepcopy(cfg);reject_config_secrets(cfg);self.assertEqual(cfg,before)
        for name in (None,{},['ENV'],'','api-key-value','KEY\nNAME','A'*201):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):reject_config_secrets({'llm':{'api_key_env':name}})
        with self.assertRaises(ValueError):reject_config_secrets({'llm':{},'extra':{'api_key_env':'NOT_ALLOWED'}})
        cyclic={'llm':{}};cyclic['self']=cyclic
        with self.assertRaisesRegex(ValueError,'zyklische'):reject_config_secrets(cyclic)
        for malformed in (None,[],{'llm':None}):
            with self.assertRaises(ValueError):reject_config_secrets(malformed)

    def test_environment_value_never_enters_plan_provenance_or_validate_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));w.config['llm']['api_key_env']='SYNTHETIC_KEY_SOURCE'
            for m in w.config['pipeline']['modules']:m['enabled']=m['id'] in ('coverage','clusterer','blind_coding')
            w.save();before=w.path.read_bytes();stream=io.StringIO()
            with patch.dict(os.environ,{'SYNTHETIC_KEY_SOURCE':'SYNTHETIC_SECRET_NEVER_WRITE'}), redirect_stdout(stream):
                runner.main(['--config',str(w.path),'--validate-only','--output-dir',str(w.root/'out')])
                provenance=runner.execution_provenance(w.path,w.root/'input.csv',w.config)
                plan=prepare_repetitions(w.path,['blind_coding'],repetitions=2)
            for data in (provenance,plan):
                self.assertNotIn('SYNTHETIC_SECRET_NEVER_WRITE',json.dumps(data))
            self.assertNotIn('SYNTHETIC_SECRET_NEVER_WRITE',stream.getvalue())
            self.assertEqual(before,w.path.read_bytes());self.assertFalse((w.root/'out').exists())


class SnapshotPrivacyIntegrationTests(unittest.TestCase):
    def test_real_model_free_run_does_not_persist_environment_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));w.config['llm']['api_key_env']='SYNTHETIC_KEY_SOURCE'
            for m in w.config['pipeline']['modules']:m['enabled']=m['id']=='coverage'
            w.save();before=w.path.read_bytes();out=w.root/'output'
            env={**os.environ,'SYNTHETIC_KEY_SOURCE':'SYNTHETIC_SECRET_NEVER_WRITE','PYTHONUTF8':'1'}
            done=subprocess.run([sys.executable,str(ROOT/'src/00_WORKFLOW_RUNNER.py'),'--config',str(w.path),'--output-dir',str(out)],
                env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(done.returncode,0,done.stderr[-2500:])
            self.assertNotIn('SYNTHETIC_SECRET_NEVER_WRITE',done.stdout+done.stderr)
            for path in out.rglob('*'):
                if path.is_file():self.assertNotIn(b'SYNTHETIC_SECRET_NEVER_WRITE',path.read_bytes(),path.name)
            self.assertEqual(before,w.path.read_bytes())
            manifest=json.loads(next(out.glob('*/workflow_manifest.json')).read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'],'success')
            self.assertEqual(manifest['completed_steps'],['coverage'])


if __name__=='__main__':unittest.main()
