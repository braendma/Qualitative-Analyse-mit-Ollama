"""Synthetic interpretation calls; original material and metrics remain authoritative."""
import copy
import json
import unittest

from coding_validation_common import MockLLM
from runtime_context import ContextBudgetError
from thematic_counts import count_topics
from thematic_interpretation import interpret_counts
from test_thematic_counts import material, topic, assignment


def response(tid='T'):
    return {'topic_id': tid, 'interpretation': 'Breite berücksichtigen.',
            'counterpositions': 'Seltene Gegenposition erhalten.',
            'limitations': 'Modellzuordnung ist nicht menschlich bestätigt.'}


class ThematicInterpretationTests(unittest.TestCase):
    def test_case_register_contains_every_same_person_topic_and_no_other_case(self):
        basis = material(['P1','P1','P2'])
        topics = [topic('A',['u0','u1']),topic('B',['u0','u1']),topic('C',['u2'])]
        counted = count_topics(basis,topics,[])
        llm=MockLLM([response('A'),response('B'),response('C')])
        interpret_counts(basis,counted,{'A':'First case side A','B':'First case side B','C':'Other case'},
                         {'model':'synthetic','num_ctx':16000,'max_tokens':512,'partial_checkpoints':False},
                         module='ambiguity_analysis',llm=llm)
        payloads=[json.loads(call[1]['content']) for call in llm.calls]
        self.assertEqual([len(p['comparison_register']) for p in payloads],[2,2,1])
        self.assertEqual(payloads[0]['comparison_register'],payloads[1]['comparison_register'])
        self.assertEqual({r['topic_id'] for r in payloads[2]['comparison_register']},{'C'})
        for payload in payloads:
            self.assertEqual(payload['comparison_basis'],'same_person_scope')
            self.assertEqual(payload['module_topic_count'],3)
            self.assertEqual(payload['comparison_topic_count'],len(payload['comparison_register']))

    def test_case_comparison_cannot_use_subset_or_multiple_people_as_full_case(self):
        basis=material(['P1','P1','P2'])
        for scope in (['u0'],['u0','u1','u2']):
            counted=count_topics(basis,[topic('T',scope)],[])
            llm=MockLLM([])
            with self.assertRaises(ValueError):
                interpret_counts(basis,counted,{'T':'Synthetic'},
                                 {'model':'synthetic','num_ctx':16000,'max_tokens':512,'partial_checkpoints':False},
                                 module='person_analysis',llm=llm)
            self.assertEqual(llm.calls,[])

    def setUp(self):
        self.material = material(['P1', 'P1', 'P2'])
        self.topics = [topic('T', self.material['units'], kind='derived')]
        self.rows = [assignment('T', 'u0'), assignment('T', 'u1', 'opposed'), assignment('T', 'u2', 'unclear')]
        self.counted = count_topics(self.material, self.topics, self.rows)
        self.params = {'model': 'synthetic', 'num_ctx': 32000, 'max_tokens': 512, 'partial_checkpoints': False}

    def run_model(self, llm, **kwargs):
        return interpret_counts(self.material, self.counted, {'T': 'Vollständiger Ausgangsbefund.'},
                                kwargs.get('params', self.params), module='swot', llm=llm)

    def test_prompt_uses_deterministic_counts_and_keeps_uncertainty_and_sources(self):
        before = copy.deepcopy((self.material, self.counted))
        llm = MockLLM([response()])
        self.assertEqual(self.run_model(llm), [response()])
        self.assertEqual(before, (self.material, self.counted))
        payload = json.loads(llm.calls[0][1]['content'])
        row = payload['comparison_register'][0]
        self.assertEqual(row['scope']['person_count'], 2)
        self.assertEqual(row['scope']['passage_count'], 3)
        self.assertEqual(row['counts']['both']['observed_person_count'], 1)
        self.assertIsNone(row['counts']['mentioned']['exact_person_count'])
        self.assertFalse(row['coverage']['complete'])
        self.assertEqual(row['count_meaning'], 'material_support_for_inference')
        self.assertEqual(payload['count_result_fingerprint'], self.counted['result_fingerprint'])
        self.assertNotIn('person_ids', row['scope'])
        self.assertNotIn('unit_ids', row['counts']['supporting'])
        self.assertEqual(payload['counterposition_material'],
                         [{'unit_id': 'u1', 'text': self.material['units']['u1']['text']}])
        self.assertNotIn('scope_unit_ids', payload['topic'])

    def test_invalid_id_numeric_fields_and_empty_limits_are_not_accepted(self):
        for bad in ({**response(), 'topic_id': 'invented'}, {**response(), 'count': 999},
                    {**response(), 'limitations': ''}, {**response(), 'interpretation': 7}):
            with self.subTest(bad=bad):
                llm = MockLLM([bad, response()])
                self.assertEqual(self.run_model(llm), [response()])
                self.assertEqual(len(llm.calls), 2)

    def test_repeated_malformed_output_fails_and_does_not_echo_raw_text(self):
        llm = MockLLM(['broken-private-output', '{}'])
        with self.assertRaises(ValueError):
            self.run_model(llm)
        self.assertNotIn('broken-private-output', json.dumps(llm.calls[-1]))

    def test_changed_counts_or_material_fail_before_any_call(self):
        for change in ('count', 'material'):
            with self.subTest(change=change):
                basis, counted = copy.deepcopy(self.material), copy.deepcopy(self.counted)
                if change == 'count':
                    counted['topics'][0]['counts']['supporting']['observed_person_count'] = 999
                else:
                    basis['units']['u0']['text'] = 'Different input despite stale declared identity'
                llm = MockLLM([])
                with self.assertRaises(ValueError):
                    interpret_counts(basis, counted, {'T': 'original'}, self.params, module='swot', llm=llm)
                self.assertEqual(llm.calls, [])

    def test_all_prompts_preflight_before_first_inference_no_truncation(self):
        topics = [*self.topics, topic('Z', self.material['units'])]
        counted = count_topics(self.material, topics, self.rows)
        llm = MockLLM([])
        with self.assertRaises(ContextBudgetError):
            interpret_counts(self.material, counted, {'T': 'short', 'Z': 'Sehr lang ü🧪' * 5000},
                             self.params, module='swot', llm=llm)
        self.assertEqual(llm.calls, [])

    def test_every_topic_gets_same_complete_comparison_register_with_scope_ids(self):
        topics = [*self.topics, topic('Z', ['u0'])]
        counted = count_topics(self.material, topics, self.rows + [assignment('Z', 'u0')])
        llm = MockLLM([response('T'), response('Z')])
        interpret_counts(self.material, counted, {'T': 'One', 'Z': 'Two'}, self.params, module='swot', llm=llm)
        registers = [json.loads(call[1]['content'])['comparison_register'] for call in llm.calls]
        self.assertEqual(registers[0], registers[1])
        self.assertNotEqual(registers[0][0]['scope_fingerprint'], registers[0][1]['scope_fingerprint'])

    def test_missing_or_unmatched_qualitative_finding_fails(self):
        for findings in ({}, {'T': ''}, {'T': 'valid', 'extra': 'invented'}):
            with self.assertRaises(ValueError):
                interpret_counts(self.material, self.counted, findings, self.params, module='swot', llm=MockLLM([]))

    def test_empty_topic_register_has_no_model_work(self):
        llm = MockLLM([])
        counted = count_topics(self.material, [], [])
        self.assertEqual(interpret_counts(self.material, counted, {}, self.params, module='swot', llm=llm), [])
        self.assertEqual(llm.calls, [])

    def test_duplicate_json_fields_are_repaired_instead_of_silently_overwritten(self):
        bad = json.dumps(response()).replace('"topic_id": "T"', '"topic_id": "invented", "topic_id": "T"')
        llm = MockLLM([bad, response()])
        self.assertEqual(self.run_model(llm), [response()])
        self.assertEqual(len(llm.calls), 2)

    def test_default_answer_budget_matches_actual_transport_and_path_is_validated(self):
        captured = []
        def backend(messages, params):
            captured.append(params['max_tokens'])
            return json.dumps(response())
        self.run_model(backend, params={'model': 'synthetic', 'num_ctx': 32000, 'partial_checkpoints': False})
        self.assertEqual(captured, [4000])
        with self.assertRaises(ValueError):
            interpret_counts(self.material, self.counted, {'T': 'text'}, self.params, module='../escape', llm=MockLLM([]))


if __name__ == '__main__':
    unittest.main()
