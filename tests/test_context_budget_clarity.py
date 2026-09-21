"""Program-bound diagnostics do not claim tokenizer or cloud-window control."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from llm_client import request_chat,ContextBudgetError
from runtime_context import message_bound,require_messages
from failure_help import failure_help
from context_preflight import require_context

class ContextBudgetClarityTests(unittest.TestCase):
    def test_budget_boundary_and_cloud_wire_remain_unchanged(self):
        request={'model':'synthetic','messages':[{'role':'user','content':'Größe 🧪'}],'options':{'num_predict':123},'stream':False}
        original=copy.deepcopy(request)
        settings={'provider':'ollama_cloud','gdpr_relevant':False,'max_tokens':123,'max_attempts':1}
        need=message_bound(request['messages'],settings)
        backend=MagicMock();backend.Client.return_value.chat.return_value={'message':{'content':'test'}}
        with self.assertRaises(ContextBudgetError) as error:
            request_chat(backend,copy.deepcopy(request),{**settings,'num_ctx':need-1},api_key='synthetic')
        backend.Client.assert_not_called()
        self.assertIn(f'Bedarf {need}, davon Antwortreserve 123',str(error.exception))
        self.assertIn('keine gemessene Tokenzahl',str(error.exception))
        self.assertIn('Kontextfenster des Anbieters nicht',str(error.exception))
        request_chat(backend,request,{**settings,'num_ctx':need},api_key='synthetic')
        self.assertEqual(backend.Client.return_value.chat.call_args.kwargs,original)

    def test_sanitized_help_retains_only_numeric_budget_diagnostics(self):
        detail='ContextBudgetError: Kontextbudget im Programm überschritten: konservativer Bedarf 193154, davon Antwortreserve 2048; eingestellt sind 131072. SECRET /private/study'
        result=failure_help(detail)
        self.assertEqual(result['kind'],'context')
        for value in ('193154','2048','131072'):self.assertIn(value,result['cause'])
        self.assertNotIn('SECRET',str(result));self.assertNotIn('/private',str(result))
        self.assertIn('nicht das Kontextfenster des Anbieters',result['action'])

    def test_start_check_explains_answer_reserve_without_changing_rejection(self):
        report={'context':500,'answer_limit':128,'blocked':[{'module':'swot','required_bound':501}]}
        with self.assertRaisesRegex(ValueError,'Antwortreserve 128') as error:require_context(report)
        self.assertIn('keine gemessene Tokenzahl',str(error.exception))
        self.assertIn('nicht automatisch gekürzt',str(error.exception))

if __name__=='__main__':unittest.main()
