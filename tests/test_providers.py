import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import yaml

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from llm_providers import selection, transport_selection, HTTPChatClient, ProviderHTTPError, KEY_ENVS
from llm_client import request_chat, LLMTransportError
from provider_keys import ProviderKeys
from local_app import App, reject_secret_settings
from test_local_app import settings
from runtime_support import atomic_json

REQUEST={'model':'sample-model','messages':[{'role':'system','content':'Return text.'},{'role':'user','content':'Example.'}],
         'options':{'num_predict':256,'temperature':0},'think':False}


class ProvidersTests(unittest.TestCase):
    def test_private_default_and_transport_boundary(self):
        self.assertTrue(selection({'model':'granite4.1:8b'})['gdpr_relevant'])
        for provider in ('openai','anthropic','ollama_cloud','huggingface'):
            with self.assertRaisesRegex(ValueError,'Cloud gesperrt'):selection({'provider':provider,'model':'test'})
            with self.assertRaises(ValueError):selection({'provider':provider,'model':'test','gdpr_relevant':'false'})
        for host in ('https://evil.example','http://localhost.evil.example','http://user:secret@localhost:11434'):
            with self.assertRaises(ValueError):transport_selection({'host':host},'test')
        with patch.dict(os.environ,{'QUALITATIVE_CLOUD_TEST_ONLY':'1'}):
            with self.assertRaises(ValueError):transport_selection({},'test')

    def test_provider_wire_formats_and_normalization(self):
        payloads={
            'openai':{'status':'completed','output':[{'type':'reasoning','content':[]},{'type':'message','content':[{'type':'output_text','text':'OK'}]}]},
            'anthropic':{'stop_reason':'end_turn','content':[{'type':'thinking','thinking':'hidden'},{'type':'text','text':'OK'}]},
            'huggingface':{'choices':[{'finish_reason':'stop','message':{'content':'OK'}}]},
        }
        for provider,payload in payloads.items():
            with self.subTest(provider=provider),patch('urllib.request.build_opener') as build:
                response=MagicMock();response.read.return_value=json.dumps(payload).encode()
                build.return_value.open.return_value.__enter__.return_value=response
                result=HTTPChatClient(provider,'secret-value',10).chat(**copy.deepcopy(REQUEST))
                self.assertEqual(result,{'message':{'content':'OK'}})
                request=build.return_value.open.call_args.args[0];body=json.loads(request.data)
                self.assertNotIn('secret-value',request.full_url);self.assertNotIn('secret-value',request.data.decode())
                self.assertNotIn('think',body);self.assertNotIn('temperature',body)
                if provider=='openai':self.assertFalse(body['store']);self.assertEqual(body['input'],REQUEST['messages'])
                if provider=='anthropic':self.assertEqual(body['system'],'Return text.');self.assertEqual(len(body['messages']),1)

    def test_truncated_refused_and_empty_answers_rejected(self):
        cases=[('openai',{'status':'incomplete','output':[]}),('openai',{'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]}),
               ('anthropic',{'stop_reason':'max_tokens','content':[{'type':'text','text':'partial'}]}),
               ('huggingface',{'choices':[{'finish_reason':'length','message':{'content':'partial'}}]}),
               ('huggingface',{'choices':[{'finish_reason':'stop','message':{'content':''}}]})]
        for provider,payload in cases:
            with self.subTest(provider=provider),patch('urllib.request.build_opener') as build:
                response=MagicMock();response.read.return_value=json.dumps(payload).encode();build.return_value.open.return_value.__enter__.return_value=response
                with self.assertRaises(ValueError):HTTPChatClient(provider,'private-key',10).chat(**copy.deepcopy(REQUEST))

    def test_errors_redact_keys_and_retries_are_bounded(self):
        cfg={'provider':'openai','gdpr_relevant':False,'num_ctx':4096,'max_attempts':2,'retry_delay_seconds':0}
        for status,calls in ((401,1),(429,2),(503,2)):
            with self.subTest(status=status),patch('llm_providers.HTTPChatClient.chat',side_effect=ProviderHTTPError(status)) as chat:
                with self.assertRaises(LLMTransportError) as err:request_chat(None,copy.deepcopy(REQUEST),cfg,api_key='private-key')
                self.assertNotIn('private-key',str(err.exception));self.assertEqual(chat.call_count,calls)
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.side_effect=urllib.error.HTTPError('https://host/secret-value',401,'secret-value',{},io.BytesIO(b'secret-value'))
            with self.assertRaises(ProviderHTTPError) as err:HTTPChatClient('openai','private-key',10).chat(**REQUEST)
            self.assertNotIn('secret-value',str(err.exception))

    def test_keys_not_in_projects_and_current_privacy_blocks_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Demo',True)['id'];opts={**settings(app),'provider':'openai','gdpr_relevant':False}
            with self.assertRaises(ValueError):app.save_provider_key(pid,{'provider':'openai','key':'private-key'})
            app.privacy(pid,False);app.save_provider_key(pid,{'provider':'openai','key':'private-key'})
            app.save(pid,opts)
            self.assertNotIn('private-key',app.provider_keys.path.read_text())
            self.assertNotIn('private-key',json.dumps(app.project(pid)))
            cfg=app.project_dir(pid)/'revisions'/app.project(pid)['revision']/'config.yaml'
            folder=app.project_dir(pid)/'jobs'/('a'*20);run=folder/'runs'/'paused';run.mkdir(parents=True)
            atomic_json(run/'workflow_manifest.json',{'status':'paused','completed_steps':[]})
            atomic_json(folder/'job.json',{'id':'a'*20,'status':'paused','created':1,'config':str(cfg),'modules':[]})
            app.privacy(pid,True)
            with patch('local_app.subprocess.Popen') as spawn:
                with self.assertRaisesRegex(ValueError,'Cloud-Lauf gesperrt'):app.start(pid,resume='a'*20)
                spawn.assert_not_called()
            self.assertFalse(ProviderKeys(tmp).public()['providers']['openai']['has_key'])

    def test_child_gets_only_selected_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Demo',True)['id'];app.privacy(pid,False)
            app.provider_keys.save('openai','chosen-private-key')
            app.save(pid,{**settings(app),'provider':'openai','gdpr_relevant':False})
            with patch.dict(os.environ,{k:'unrelated-key' for k in KEY_ENVS}),patch('local_app.subprocess.Popen') as spawn,patch.object(app,'monitor'):
                spawn.return_value.pid=12345
                app.start(pid)
                env=spawn.call_args.kwargs['env'];self.assertEqual(env['OPENAI_API_KEY'],'chosen-private-key')
                for k in KEY_ENVS-{'OPENAI_API_KEY'}:self.assertNotIn(k,env)
                self.assertNotIn('chosen-private-key',' '.join(spawn.call_args.args[0]))

    def test_settings_reject_credentials_recursively(self):
        reject_secret_settings({'max_tokens':256})
        for data in ({'api_key':'secret'},{'context':{'authorization':'secret'}},{'provider_token':'secret'}):
            with self.assertRaises(ValueError):reject_secret_settings(data)

    def test_key_rotation_and_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=ProviderKeys(tmp);vault.save('openai','first-key');vault.save('anthropic','second-key')
            vault.save('openai','replacement');self.assertEqual(vault.keys['anthropic'],'second-key')
            vault.save('openai',remove=True);self.assertFalse(vault.public()['providers']['openai']['has_key'])
            self.assertNotIn('replacement',vault.path.read_text())

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_windows_key_storage_reload_rotate_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=ProviderKeys(tmp);vault.save('openai','first-private-key',persist=True)
            self.assertNotIn('first-private-key',vault.path.read_text())
            restored=ProviderKeys(tmp);self.assertEqual(restored.keys['openai'],'first-private-key')
            restored.save('openai','replacement-private-key',persist=True)
            self.assertEqual(ProviderKeys(tmp).keys['openai'],'replacement-private-key')
            restored.save('openai',remove=True)
            self.assertNotIn('openai',ProviderKeys(tmp).keys)
