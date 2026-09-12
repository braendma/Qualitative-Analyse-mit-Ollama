import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
import unittest
from unittest.mock import patch
from summary_reduction import reduce_prompt
from coding_validation_common import call_json_with_repair
import json
import tempfile
import os


class RepairTests(unittest.TestCase):
    def test_completed_reductions_resume_and_failed_part_is_retried(self):
        original = 'Synthetischer Befund. ' * 2000
        calls = []
        def compact(system, text, params):
            calls.append(text)
            if len(calls) == 2:
                raise RuntimeError('temporary transport failure')
            return 'Verdichteter Befund.'
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WORKFLOW_CHECKPOINT_DIR': tmp}):
            params = {'num_ctx': 8192, 'max_tokens': 512}
            with self.assertRaises(RuntimeError):
                reduce_prompt('System', original, params, compact)
            first_count = len(calls)
            self.assertTrue(reduce_prompt('System', original, params, compact))
            # The completed first part was reused; the second was retried.
            self.assertEqual(calls[first_count], calls[1])

    def test_nonconvergence_and_impossible_budget_fail_closed(self):
        with self.assertRaises(ValueError):
            reduce_prompt('System', 'x' * 20000, {'num_ctx':8192, 'max_tokens':512},
                          lambda system, text, params: text)
        with self.assertRaises(ValueError):
            reduce_prompt('System' * 1000, 'text', {'num_ctx':4096, 'max_tokens':2048},
                          lambda *args: self.fail('must not call model'))

    def test_empty_summaries_cannot_be_saved_as_success(self):
        from summarizer_core import llm_summary
        from llm_client import LLMResponseError
        with patch('summarizer_core.ollama_chat', return_value=''):
            with self.assertRaises(LLMResponseError):
                llm_summary('system', 'text', {'model':'mock','temperature':0,'max_tokens':512,'num_ctx':8192})

    def test_exhausted_response_splits_without_losing_input(self):
        from summary_reduction import summarize_part
        from llm_client import LLMResponseError
        leaves=[]
        original='ABÄ😀'*1000
        def model(system,text,params):
            if len(text)>1100:raise LLMResponseError('length')
            leaves.append(text)
            return 'Complete short summary.'
        self.assertTrue(summarize_part('system',original,{},model))
        self.assertEqual(''.join(leaves),original)

    def test_truncated_compact_summary_retries_with_safe_budget(self):
        from summarizer_core import llm_summary
        from llm_client import LLMResponseError
        with patch('summarizer_core.ollama_chat', side_effect=[LLMResponseError('length'), 'Complete.']) as call:
            self.assertEqual(llm_summary('system', 'evidence', {'model':'mock','temperature':0.05,'max_tokens':600,'num_ctx':16384}), 'Complete.')
            self.assertEqual([c.kwargs['max_tokens'] for c in call.call_args_list], [600,1200])
            self.assertEqual(call.call_args_list[1].kwargs['settings']['max_tokens'],1200)

    def test_all_input_included_in_reduction(self):
        original = ''.join(str(i)+' Ä😀\n' for i in range(4000))
        calls = []
        def compact(system, user, params):
            self.assertGreaterEqual(params['num_ctx'] - len((system+user).encode('utf-8')) - 1024, 2400)
            calls.append(user.split('\n\n', 1)[1])
            return 'Kurze Zusammenfassung.'
        result = reduce_prompt('System', original, {'num_ctx': 16384, 'max_tokens': 6000}, compact)
        self.assertEqual(''.join(calls), original)
        self.assertGreater(len(calls[0].encode('utf-8')), 11000)
        self.assertTrue(all(len(part.encode('utf-8')) < 12700 for part in calls))
        self.assertLess(len(result.encode()), 9000)

    def test_repair_keeps_codebook_and_evidence(self):
        messages = [{'role':'user','content':'Codebuch: A; Textstelle: Test'}]
        seen=[]
        def llm(msg, params):
            seen.append(msg)
            return json.dumps({'code': 'bad' if len(seen)==1 else 'A'})
        def validate(value):
            if value['code']!='A': raise ValueError('Code fehlt')
            return value
        self.assertEqual(call_json_with_repair(messages, {}, validate, llm)['code'], 'A')
        self.assertEqual(seen[1][0], messages[0])

if __name__=='__main__':unittest.main()
