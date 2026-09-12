import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from evidence_audit_core import audit_blocks, map_audit_blocks, normalize_mappings, audit_response_schema, _llm, _repair
from response_schemas import schema_for
from llm_client import ContextBudgetError


class EvidenceBlocksTests(unittest.TestCase):
    def prompt(self, audits, counters):
        return 'system', json.dumps({'audits': audits, 'counters': counters})

    def test_every_pair_once_with_original_content_and_budget(self):
        audits = [{'audit_id': str(i), 'text': 'original audit ' * 40} for i in range(11)]
        counters = [{'counter_id': str(i), 'text': 'original counter ' * 45} for i in range(17)]
        params = {'num_ctx': 4000, 'max_tokens': 400}
        blocks = list(audit_blocks(audits, counters, self.prompt, params))
        pairs = []
        for a, c, s, u in blocks:
            self.assertLessEqual(len((s + u).encode()) + 720, 4000)
            for item in a: self.assertIn(item, audits)
            for item in c: self.assertIn(item, counters)
            pairs.extend((x['audit_id'], y['counter_id']) for x in a for y in c)
        expected = {(x['audit_id'], y['counter_id']) for x in audits for y in counters}
        self.assertEqual(set(pairs), expected)
        self.assertEqual(len(pairs), len(expected))

    def test_union_retains_counter_matches_and_separate_explanations(self):
        audits = [{'audit_id': 'A'}]
        counters = [{'counter_id': str(i), 'text': 'x' * 1000} for i in range(5)]
        def model(system, user, params):
            part = json.loads(user)
            return json.dumps({'zuordnungen': [{'audit_id': 'A', 'gegenbeleg_ids': [x['counter_id'] for x in part['counters']], 'einordnung': 'Teilbegründung'}]})
        with patch('evidence_audit_core._llm', side_effect=model):
            mappings, count = map_audit_blocks(audits, counters, self.prompt, {'num_ctx': 3000, 'max_tokens': 400, 'parallel_workers': 3, 'partial_checkpoints': False})
        self.assertEqual(mappings['A']['gegenbeleg_ids'], [str(i) for i in range(5)])
        self.assertEqual(mappings['A']['einordnung'].count('Teilbegründung'), count)
        self.assertGreater(count, 1)

    def test_atomic_overflow_fails_without_truncation(self):
        with self.assertRaises(ContextBudgetError):
            list(audit_blocks([{'audit_id': 'A', 'text': 'x' * 8000}], [{'counter_id': 'C'}], self.prompt, {'num_ctx': 4000}))

    def test_small_payload_stays_single(self):
        self.assertEqual(len(list(audit_blocks([{'audit_id': 'A'}], [{'counter_id': 'C'}], self.prompt, {'num_ctx': 10000}))), 1)

    def test_cross_block_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_mappings({'zuordnungen': [{'audit_id': 'A', 'gegenbeleg_ids': ['other_block']}]}, {'A'}, {'this_block': {}})

    def test_dynamic_schema_does_not_mutate_other_parallel_blocks(self):
        import copy
        original = copy.deepcopy(schema_for('evidence_audit'))
        first = audit_response_schema({'A'}, {'C'})
        second = audit_response_schema({'B'}, {'D'})
        fields = first['properties']['zuordnungen']['items']['properties']
        self.assertEqual(fields['audit_id']['enum'], ['A'])
        self.assertEqual(fields['gegenbeleg_ids']['items']['enum'], ['C'])
        self.assertEqual(second['properties']['zuordnungen']['items']['properties']['audit_id']['enum'], ['B'])
        self.assertEqual(schema_for('evidence_audit'), original)

    def test_schema_reaches_primary_and_repair_transport(self):
        schema = audit_response_schema({'A'}, {'C'})
        params = {'model': 'synthetic', 'temperature': 0, 'max_tokens': 100, 'evidence_response_schema': schema}
        with patch('evidence_audit_core.ollama_chat', return_value='{}') as transport:
            _llm('system', 'source', params)
            _repair('{}', params, 'source')
        for call in transport.call_args_list:
            self.assertEqual(call.kwargs['settings']['response_schema'], schema)

    def test_invalid_ids_retry_fresh_without_silently_discarding(self):
        bad = json.dumps({'zuordnungen': [{'audit_id': 'A', 'gegenbeleg_ids': ['foreign'], 'einordnung': 'bad'}]})
        good = json.dumps({'zuordnungen': [{'audit_id': 'A', 'gegenbeleg_ids': ['C'], 'einordnung': 'valid'}]})
        params = {'num_ctx': 10000, 'max_tokens': 400, 'partial_checkpoints': False}
        with patch('evidence_audit_core._llm', side_effect=[bad, good]) as model, patch('evidence_audit_core._repair', return_value=bad):
            result, count = map_audit_blocks([{'audit_id': 'A'}], [{'counter_id': 'C'}], self.prompt, params)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(result['A']['gegenbeleg_ids'], ['C'])
        with patch('evidence_audit_core._llm', return_value=bad), patch('evidence_audit_core._repair', return_value=bad):
            with self.assertRaises(ValueError):
                map_audit_blocks([{'audit_id': 'A'}], [{'counter_id': 'C'}], self.prompt, params)


if __name__ == '__main__': unittest.main()
