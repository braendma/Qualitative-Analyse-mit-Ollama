import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from llm_client import request_chat, ContextBudgetError

class CloudSchemaGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.request={'model':'synthetic','messages':[{'role':'user','content':'Synthetic comparison register'}],
                      'options':{'num_predict':128}}
        self.schema={'type':'object','properties':{'topic_id':{'enum':['TARGET']}},'required':['topic_id']}
        self.settings={'provider':'ollama_cloud','gdpr_relevant':False,'num_ctx':4096,
                       'response_schema':self.schema,'max_attempts':1}
        self.backend=MagicMock(); self.backend.Client.return_value.chat.return_value={'message':{'content':'{}'}}

    def test_cloud_schema_sent_as_guidance_without_mutating_input(self):
        before=copy.deepcopy(self.request)
        request_chat(self.backend,self.request,self.settings,api_key='synthetic')
        wire=self.backend.Client.return_value.chat.call_args.kwargs
        self.assertNotIn('format',wire)
        self.assertEqual(wire['messages'][1:],before['messages'])
        self.assertEqual(json.loads(wire['messages'][0]['content'].split('JSON-Schema:\n')[1]),self.schema)
        self.assertEqual(self.request,before)

    def test_schema_overhead_is_counted_before_transport(self):
        self.settings['response_schema']={'description':'x'*5000}
        with self.assertRaises(ContextBudgetError):request_chat(self.backend,self.request,self.settings,api_key='synthetic')
        self.backend.Client.assert_not_called()

    def test_local_prompt_unchanged_and_enforced_schema_preserved(self):
        self.settings.update(provider='ollama_local',gdpr_relevant=True)
        before=copy.deepcopy(self.request['messages'])
        request_chat(self.backend,self.request,self.settings)
        wire=self.backend.Client.return_value.chat.call_args.kwargs
        self.assertEqual(wire['messages'],before);self.assertEqual(wire['format'],self.schema)

    def test_explicitly_disabled_guidance_is_respected(self):
        self.settings['structured_outputs']=False
        request_chat(self.backend,self.request,self.settings,api_key='synthetic')
        self.assertEqual(self.backend.Client.return_value.chat.call_args.kwargs['messages'],self.request['messages'])

if __name__=='__main__':unittest.main()
