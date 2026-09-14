"""Synthetic assignment execution: no network, inference or child processes."""
import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thematic_assignment import execute_assignments, CORRECTION
from thematic_counts import count_topics
from llm_client import ContextBudgetError, LLMTransportError
from runtime_support import fingerprint

PARAMS = {'model': 'synthetic', 'provider': 'ollama_local', 'parallel_workers': 1,
          'num_ctx': 32768, 'max_tokens': 2048, 'partial_checkpoints': False}


def fixture(n=3):
    basis = {'schema_version': 1, 'basis_fingerprint': 'frozen-synthetic',
             'person_basis': 'confirmed', 'persons': ['P'],
             'units': {f'u{i}': {'kind': 'passage', 'person': 'P', 'text': f'Original {i}',
                                'segment_ids': [f's{i}'], 'code_paths': ['A']} for i in range(n)}}
    topics = [{'topic_id': tid, 'kind': 'explicit', 'definition': 'Defined theme ' + tid,
               'inclusion': 'Include a supported statement', 'exclusion': 'Exclude unrelated text',
               'scope_unit_ids': list(basis['units'])} for tid in ('T1', 'T2')]
    return basis, topics


def payload(messages):
    return json.loads(messages[-1]['content'].removesuffix(CORRECTION))


def valid(messages, settings):
    return json.dumps({'assignments': [{**cell, 'status': 'supported'} for cell in payload(messages)['cells']]})


class ThematicAssignmentTests(unittest.TestCase):
    def setUp(self):
        for name in ('analysis_work.update_progress', 'runtime_context.update_progress'):
            handle = patch(name)
            handle.start()
            self.addCleanup(handle.stop)

    def test_full_scoped_matrix_and_no_person_or_frequency_payload(self):
        basis, topics = fixture()
        topics[1]['scope_unit_ids'] = ['u0']
        calls = []
        def llm(messages, settings):
            data = payload(messages)
            calls.append(data)
            self.assertNotIn('person', data['units'][0])
            self.assertEqual(settings['response_schema']['required'], ['assignments'])
            return valid(messages, settings)
        result = execute_assignments(basis, topics, PARAMS, module='swot', llm=llm)
        self.assertEqual(len(result), 4)
        self.assertEqual({(r['topic_id'], r['unit_id']) for r in result},
                         {('T1','u0'),('T1','u1'),('T1','u2'),('T2','u0')})
        self.assertIn('material_content_fingerprint', calls[0]['binding'])
        self.assertEqual(count_topics(basis, topics, result)['topics'][0]['counts']['mentioned']['exact_person_count'], 1)

    def test_serial_parallel_equivalent_and_flat_coordinator(self):
        basis, topics = fixture(4)
        serial = execute_assignments(basis, topics, {**PARAMS, 'batch_items': 1}, module='swot', llm=valid)
        barrier = threading.Barrier(2)
        def llm(messages, settings):
            barrier.wait(timeout=5)
            return valid(messages, settings)
        parallel = execute_assignments(basis, topics, {**PARAMS, 'batch_items': 1, 'parallel_workers': 2}, module='swot', llm=llm)
        self.assertEqual(serial, parallel)

    def test_long_original_preserved_or_fails_before_any_inference(self):
        basis, topics = fixture(2)
        text = 'Ä 😀 full original\n' * 1000
        basis['units']['u1']['text'] = text
        seen = []
        def llm(messages, settings):
            seen.extend(unit['text'] for unit in payload(messages)['units'])
            return valid(messages, settings)
        execute_assignments(basis, topics, {**PARAMS, 'num_ctx': 100000}, module='swot', llm=llm)
        self.assertIn(text, seen)
        seen.clear()
        with self.assertRaises(ContextBudgetError):
            execute_assignments(basis, topics, {**PARAMS, 'num_ctx': 5000}, module='swot', llm=llm)
        self.assertEqual(seen, [])

    def test_inclusion_exclusion_and_themes_are_split_without_truncation(self):
        basis, topics = fixture(1)
        topics[0]['definition'] = 'Definition ' * 100
        calls = []
        def llm(messages, settings):
            calls.append(payload(messages))
            return valid(messages, settings)
        execute_assignments(basis, topics, {**PARAMS, 'batch_items': 1}, module='swot', llm=llm)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]['topics'][0]['definition'], topics[0]['definition'])
        self.assertEqual(calls[0]['topics'][0]['inclusion'], topics[0]['inclusion'])
        self.assertEqual(calls[0]['topics'][0]['exclusion'], topics[0]['exclusion'])

    def test_unknown_duplicate_missing_bad_status_extra_and_json_duplicate_are_rejected(self):
        basis, topics = fixture(1)
        cell = {'topic_id':'T1','unit_id':'u0','status':'supported'}
        bad = [None, {'assignments':[]}, {'assignments':[cell,cell]},
               {'assignments':[{**cell,'unit_id':'unknown'}]},
               {'assignments':[{**cell,'status':'failed'}]},
               {'assignments':[{**cell,'status':'not_checked'}]},
               {'assignments':[{**cell,'quote':'invented'}]},
               {'assignments':[cell], 'counts': 1},
               '{"assignments":[],"assignments":[]}']
        for response in bad:
            with self.subTest(response=response):
                calls = []
                def llm(messages, settings):
                    calls.append(messages)
                    return response if isinstance(response, str) else json.dumps(response)
                with self.assertRaisesRegex(ValueError, 'nach Korrektur'):
                    execute_assignments(basis, topics[:1], PARAMS, module='swot', llm=llm)
                self.assertEqual(len(calls), 2)
                self.assertTrue(calls[1][-1]['content'].endswith(CORRECTION))
                self.assertEqual(len(calls[1]), 2, 'No broken raw output may inflate retry context')

    def test_bounded_correction_accepts_unclear_without_fabricating_negative(self):
        basis, topics = fixture(1)
        calls = []
        def llm(messages, settings):
            calls.append(settings)
            if len(calls) == 1: return 'broken output' * 10000
            return json.dumps({'assignments':[{'topic_id':'T1','unit_id':'u0','status':'unclear'}]})
        rows = execute_assignments(basis, topics[:1], PARAMS, module='swot', llm=llm)
        result = count_topics(basis, topics[:1], rows)['topics'][0]
        self.assertIsNone(result['counts']['mentioned']['exact_person_count'])
        self.assertEqual(result['coverage']['status_counts']['unclear'], 1)
        self.assertEqual(calls[-1]['temperature'], 0.0)

    def test_technical_transport_failure_not_converted_to_unclear_or_repaired(self):
        basis, topics = fixture(1)
        calls = []
        def llm(messages, settings):
            calls.append(1)
            raise LLMTransportError('Synthetic transport failure')
        with self.assertRaises(LLMTransportError):
            execute_assignments(basis, topics, PARAMS, module='swot', llm=llm)
        self.assertEqual(calls, [1])

    def test_every_retry_preflight_precedes_any_inference(self):
        basis, topics = fixture(2)
        calls = []
        with patch('thematic_assignment.require_messages', side_effect=[1, ContextBudgetError('synthetic')]):
            with self.assertRaises(ContextBudgetError):
                execute_assignments(basis, topics, {**PARAMS, 'batch_items':1}, module='swot', llm=lambda *_: calls.append(1))
        self.assertEqual(calls, [])

    def test_small_answer_reserve_splits_and_impossible_single_cell_blocks(self):
        basis, topics = fixture(3)
        calls = []
        def llm(messages, settings):
            calls.append(len(payload(messages)['cells']))
            return valid(messages, settings)
        rows = execute_assignments(basis, topics, {**PARAMS, 'max_tokens':150}, module='swot', llm=llm)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(size == 1 for size in calls))
        calls.clear()
        with self.assertRaises(ContextBudgetError):
            execute_assignments(basis, topics, {**PARAMS, 'max_tokens':32}, module='swot', llm=llm)
        self.assertEqual(calls, [])

    def test_invalid_inputs_and_empty_scopes_do_not_infer_or_mutate(self):
        basis, topics = fixture()
        before = copy.deepcopy((basis, topics, PARAMS))
        execute_assignments(basis, topics, PARAMS, module='swot', llm=valid)
        self.assertEqual((basis, topics, PARAMS), before)
        for name in ('../escape', '', 'a/b'):
            with self.assertRaises(ValueError):
                execute_assignments(basis, topics, PARAMS, module=name, llm=lambda *_: self.fail())
        topics[0]['scope_unit_ids'] = []
        self.assertEqual(execute_assignments(basis, topics[:1], PARAMS, module='swot', llm=lambda *_: self.fail()), [])

    def test_cached_cells_are_revalidated_in_their_own_block(self):
        basis, topics = fixture(1)
        class InvalidCheckpoint:
            def __init__(self, module, params): self.hits = 1
            def run(self, key, inputs, compute): return []
        with patch('analysis_work.PartCheckpoint', InvalidCheckpoint):
            with self.assertRaisesRegex(ValueError, 'unvollständig'):
                execute_assignments(basis, topics, PARAMS, module='swot', llm=lambda *_: self.fail())

    def test_progress_uses_planned_blocks_and_never_copies_material(self):
        basis, topics = fixture(2)
        basis['units']['u0']['text'] = 'SYNTHETIC_PRIVATE_TEXT'
        with patch('analysis_work.update_progress') as update:
            execute_assignments(basis, topics, {**PARAMS, 'batch_items':1}, module='swot', llm=valid)
        initial = update.call_args_list[0].kwargs
        self.assertEqual((initial['total'], initial['unit']), (4, 'batches'))
        self.assertEqual(update.call_args_list[-1].kwargs['completed'], 4)
        self.assertNotIn('SYNTHETIC_PRIVATE_TEXT', str(update.call_args_list))
        self.assertNotIn('topic_id', str(update.call_args_list))

    def test_all_five_model_statuses_are_preserved(self):
        basis, topics = fixture(5)
        statuses = ['supported', 'opposed', 'both', 'no_evidence', 'unclear']
        def llm(messages, settings):
            return json.dumps({'assignments': [{**cell, 'status': statuses[int(cell['unit_id'][1:])]}
                              for cell in payload(messages)['cells']]})
        rows = execute_assignments(basis, topics[:1], PARAMS, module='swot', llm=llm)
        self.assertEqual([row['status'] for row in rows], statuses)

    def test_checkpoint_identity_binds_full_material_and_definitions(self):
        basis, topics = fixture(1)
        identities = []
        class CaptureCheckpoint:
            def __init__(self, module, params): self.hits = 0
            def run(self, key, inputs, compute):
                identities.append(fingerprint({'key':key,'inputs':inputs}))
                return compute()
        with patch('analysis_work.PartCheckpoint', CaptureCheckpoint):
            execute_assignments(basis, topics, PARAMS, module='swot', llm=valid)
            basis['units']['u0']['text'] += ' Changed text with same declared basis ID'
            execute_assignments(basis, topics, PARAMS, module='swot', llm=valid)
            topics[0]['exclusion'] += ' Changed rule'
            execute_assignments(basis, topics, PARAMS, module='swot', llm=valid)
        self.assertEqual(len(set(identities)), 3)

    def test_completed_blocks_reused_after_later_failure(self):
        basis, topics = fixture(2)
        store = {}
        class MemoryCheckpoint:
            def __init__(self, module, params): self.hits = 0
            def run(self, key, inputs, compute):
                identity = fingerprint([key,inputs])
                if identity in store:
                    self.hits += 1
                    return copy.deepcopy(store[identity])
                value = compute()
                store[identity] = copy.deepcopy(value)
                return value
        def fail_later(messages, settings):
            if payload(messages)['cells'][0]['unit_id'] == 'u1': raise LLMTransportError('synthetic')
            return valid(messages, settings)
        params = {**PARAMS, 'batch_items':1}
        with patch('analysis_work.PartCheckpoint', MemoryCheckpoint):
            with self.assertRaises(LLMTransportError):
                execute_assignments(basis, topics, params, module='swot', llm=fail_later)
            calls = []
            def resume(messages, settings):
                calls.extend(payload(messages)['cells'])
                return valid(messages, settings)
            rows = execute_assignments(basis, topics, params, module='swot', llm=resume)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(calls), 3)
        self.assertNotIn({'topic_id':'T1','unit_id':'u0'}, calls)


if __name__ == '__main__': unittest.main()
