import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import runtime_evidence as evidence
from llm_client import request_chat, LLMTransportError
from runtime_support import atomic_json
from ollama_capacity import metadata

REQUEST = {'model':'synthetic:latest', 'messages':[{'role':'user','content':'PRIVATE_INTERVIEW_TEXT'}],
           'options':{'num_predict':32,'temperature':.05}, 'think':'low', 'stream':False}
DIGEST = 'a'*64


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.records = self.root/'_runtime_evidence'
        self.env = patch.dict(os.environ, {**{k:v for k,v in os.environ.items() if not k.startswith('WORKFLOW_')},
            evidence.ENV:str(self.records), 'WORKFLOW_RUN_ID':'synthetic-run',
            'WORKFLOW_MODULE':'blind_coding', 'WORKFLOW_FINGERPRINT':'f'*64}, clear=True)
        self.env.start(); self.addCleanup(self.env.stop)
        self.meta = patch('ollama_capacity.metadata', side_effect=self.metadata)
        self.meta.start(); self.addCleanup(self.meta.stop)
        self.backend = MagicMock()
        self.backend.Client.return_value.chat.return_value={'model':'synthetic:latest','message':{'content':'PRIVATE_RESPONSE','thinking':'PRIVATE_REASONING'}}

    @staticmethod
    def metadata(endpoint, **kwargs):
        return {'models':[{'name':'synthetic:latest','digest':DIGEST,'context_length':4096}]}

    def call(self, **kwargs):
        return request_chat(self.backend, copy.deepcopy(REQUEST), {'num_ctx':4096,'max_attempts':2,'retry_delay_seconds':0,**kwargs})

    def data(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(self.records.glob('*.json'))]

    def test_records_wire_parameters_and_observed_digest_without_contents(self):
        self.call()
        record = self.data()[0]
        self.assertEqual(record['parameters_sent']['options']['num_ctx'],4096)
        self.assertEqual(record['parameters_sent']['think'],'low')
        self.assertEqual(record['model_before']['digest'],DIGEST)
        self.assertEqual(record['observed_context_length'],4096)
        self.assertEqual(record['parameter_status'],'request_accepted')
        self.assertEqual(record['server_parameter_enforcement'],'not_verifiable')
        self.assertNotIn('PRIVATE',json.dumps(record))

    def test_diagnostic_thinking_fallback_is_rejected_without_second_request(self):
        self.backend.Client.return_value.chat.side_effect=RuntimeError('does not support thinking PRIVATE_KEY')
        with self.assertRaisesRegex(LLMTransportError,'ohne Wechsel'):
            self.call()
        self.assertEqual(self.backend.Client.return_value.chat.call_count,1)
        self.assertEqual(self.data()[0]['failure_kind'],'thinking_unsupported')
        self.assertNotIn('PRIVATE',json.dumps(self.data()))

    def test_changed_or_unknown_model_is_not_accepted(self):
        before={'name':'synthetic:latest','digest':DIGEST,'status':'local_metadata_observed'}
        with patch.object(evidence,'observe_model',side_effect=[before,{**before,'digest':'b'*64}]):
            with self.assertRaisesRegex(evidence.RuntimeEvidenceError,'während'):
                self.call()
        self.assertEqual(self.data()[0]['status'],'failed')
        self.backend.reset_mock()
        with patch.object(evidence,'observe_model',side_effect=evidence.RuntimeEvidenceError('unknown')):
            with self.assertRaises(evidence.RuntimeEvidenceError):self.call()
        self.backend.Client.return_value.chat.assert_not_called()

    def test_expected_digest_blocks_changed_next_sample_before_inference(self):
        with patch.dict(os.environ,{'WORKFLOW_EXPECTED_MODEL_DIGEST':'b'*64}):
            with self.assertRaisesRegex(evidence.RuntimeEvidenceError,'vorherigen'):
                self.call()
        self.backend.Client.return_value.chat.assert_not_called()

    def test_other_local_response_model_rejected(self):
        self.backend.Client.return_value.chat.return_value={'model':'other:latest','message':{'content':'PRIVATE'}}
        with self.assertRaisesRegex(evidence.RuntimeEvidenceError,'anderes Modell'):self.call()

    def test_cloud_identity_stays_unknown_and_ignored_options_are_not_claimed(self):
        for provider in ('openai','anthropic','huggingface','ollama_cloud'):
            with patch('llm_providers.HTTPChatClient') as http, patch.object(evidence,'observe_model',side_effect=AssertionError('No local metadata for cloud')):
                http.return_value.chat.return_value={'message':{'content':'PRIVATE'}}
                request_chat(self.backend,copy.deepcopy(REQUEST),{'provider':provider,'gdpr_relevant':False,'num_ctx':4096},api_key='PRIVATE_KEY')
        records=self.data()
        self.assertEqual(len(records),4)
        for record in records:
            self.assertEqual(record['model_identity_status'],'cloud_weights_not_verifiable')
            self.assertNotIn('num_ctx',json.dumps(record['parameters_sent']))
            if record['provider']!='ollama_cloud':
                self.assertNotIn('think',record['parameters_sent'])
                self.assertNotIn('temperature',json.dumps(record['parameters_sent']))
        self.assertNotIn('PRIVATE',json.dumps(records))

    def test_retry_receipts_and_failed_diagnostic_writes_never_repeat_good_inference(self):
        self.backend.Client.return_value.chat.side_effect=[RuntimeError('temporary PRIVATE'),{'message':{'content':'PRIVATE'}}]
        self.call()
        self.assertEqual(sorted(r['status'] for r in self.data()),['accepted','failed'])
        self.backend.Client.return_value.chat.side_effect=None
        before=self.backend.Client.return_value.chat.call_count
        with patch.object(evidence,'atomic_json',side_effect=OSError('full disk')):
            with self.assertRaises(OSError):self.call()
        self.assertEqual(self.backend.Client.return_value.chat.call_count,before)

    def test_receipt_inventory_binds_files_and_detects_tampering(self):
        self.call()
        summary=evidence.summarize(self.records,'synthetic-run','f'*64)
        self.assertEqual(summary['accepted'],1)
        manifest={'run_id':'synthetic-run','fingerprint':'f'*64,'status':'success','runtime_evidence':summary}
        self.assertEqual(evidence.verify_inventory(self.root,manifest),summary)
        path=next(self.records.glob('*.json'));original=path.read_bytes();path.write_bytes(original+b' ')
        with self.assertRaisesRegex(evidence.RuntimeEvidenceError,'verändert'):evidence.verify_inventory(self.root,manifest)
        path.write_bytes(original)
        manifest['runtime_evidence']['files']['../outside.json']='x'
        with self.assertRaises(evidence.RuntimeEvidenceError):evidence.verify_inventory(self.root,manifest)

    def test_empty_and_partial_evidence_never_claim_verification(self):
        self.assertEqual(evidence.summarize(self.records,'synthetic-run','f'*64)['parameter_status'],'not_observed')
        evidence.RequestReceipt('ollama_local','http://localhost:11434',REQUEST)
        summary=evidence.summarize(self.records,'synthetic-run','f'*64)
        self.assertEqual(summary['pending'],1)
        self.assertEqual(summary['accepted'],0)
        with self.assertRaises(evidence.RuntimeEvidenceError):evidence.summarize(self.records,'other-run','f'*64)

    def test_parallel_requests_have_separate_atomic_receipts(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _:self.call(),range(12)))
        self.assertEqual(evidence.summarize(self.records,'synthetic-run','f'*64)['accepted'],12)

    def test_invalid_numbers_fail_before_dispatch_and_no_ledger_for_regular_requests(self):
        request=copy.deepcopy(REQUEST);request['options']['temperature']=float('nan')
        with self.assertRaises(evidence.RuntimeEvidenceError):
            request_chat(self.backend,request,{})
        self.backend.Client.return_value.chat.assert_not_called()
        with patch.dict(os.environ,{evidence.ENV:''}),patch.object(evidence,'observe_model',side_effect=AssertionError()):
            self.call()
        self.assertFalse(self.records.exists())

    def test_local_metadata_ambiguous_remote_and_missing_digests_rejected(self):
        base={'name':'synthetic:latest','digest':DIGEST}
        for models in ([],[base,base],[{**base,'remote_host':'private'}],[{**base,'digest':'wrong'}]):
            with self.subTest(models=models),patch('ollama_capacity.metadata',return_value={'models':models}):
                with self.assertRaises(evidence.RuntimeEvidenceError):evidence.observe_model('http://localhost:11434','synthetic')

    def test_metadata_transport_never_uses_external_host_or_redirects(self):
        for host in ('https://example.org','http://localhost.evil','http://secret@localhost','http://localhost/x','http://localhost/?key=secret'):
            with self.assertRaises(ValueError):metadata('tags',host=host)
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"models":[]}'
            self.assertEqual(metadata('tags',host='http://127.0.0.1:12345'),{'models':[]})
            req=build.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url,'http://127.0.0.1:12345/api/tags')
            self.assertIsNone(req.data)
            self.assertTrue(any(type(h).__name__=='NoRedirect' for h in build.call_args.args))


if __name__=='__main__':unittest.main()
