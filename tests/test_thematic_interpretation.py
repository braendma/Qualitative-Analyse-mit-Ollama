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
    def test_shared_register_fields_preserve_every_typed_value_and_row(self):
        from thematic_interpretation import _register_table, _share_table_fields
        rows = [{'topic_id': str(i), 'rules': {'inclusion': 'Gleiche Regel', 'exclusion': None},
                 'mixed': [False, 0, 0.0, None][i], 'empty': {}, 'list': [],
                 'scope': {'fingerprint': 'scope-' + str(i % 2)}} for i in range(4)]
        before = copy.deepcopy(rows)
        table = _share_table_fields(_register_table(rows))
        rebuilt = []
        for values in table['rows']:
            row = {}
            pairs = [(field['path'], field['value']) for field in table['shared_fields']]
            pairs += list(zip(table['columns'], values))
            for path, value in pairs:
                cursor = row
                for name in path[:-1]:
                    cursor = cursor.setdefault(name, {})
                cursor[path[-1]] = value
            rebuilt.append(row)
        self.assertEqual(json.dumps(rebuilt, sort_keys=True), json.dumps(before, sort_keys=True))
        self.assertIn(['mixed'], table['columns'])
        self.assertEqual(rows, before)

    def test_repeated_long_rules_fit_without_removing_comparison_topics(self):
        from thematic_interpretation import _interpretation_prompt, SHARED_GUIDANCE, SYSTEM, CORRECTION
        from runtime_context import require_messages
        rows = [{'topic_id': 'T'+str(i), 'definition': 'Befund '+str(i),
                 'inclusion': 'Vollständige Einschlussregel ä ' * 25,
                 'exclusion': 'Vollständige Ausschlussregel 🧪 ' * 25,
                 'scope_fingerprint': 'scope-'+str(i % 12),
                 'counts': {'supported': i, 'unclear': None}} for i in range(55)]
        payload = {'comparison_register': rows, 'comparison_topic_count': 55}
        params = {'num_ctx': 18000, 'max_tokens': 2048}
        system, user = _interpretation_prompt(payload, params)
        compact = json.loads(user)
        self.assertEqual(system, SYSTEM + SHARED_GUIDANCE)
        self.assertEqual(compact['comparison_register']['encoding'], 'shared_fields_rows_v1')
        self.assertEqual(len(compact['comparison_register']['rows']), 55)
        self.assertEqual(compact['comparison_topic_count'], 55)
        self.assertIn(rows[0]['inclusion'], user)
        require_messages([{'content': system}, {'content': user}, {'content': CORRECTION}], params)

    def test_large_register_fits_losslessly_without_changing_topics_counts_or_scope(self):
        basis = material(['P1', 'P1', 'P2'])
        topics = [topic('T'+str(i), ['u0', 'u1'] if i % 2 else list(basis['units']),
                        definition='Unverändertes Thema ä 🧪 '+str(i)) for i in range(30)]
        assignments = [assignment(t['topic_id'], uid, 'unclear' if uid == 'u1' else 'supported')
                       for t in topics for uid in t['scope_unit_ids']]
        counted = count_topics(basis, topics, assignments)
        findings = {t['topic_id']: 'Vollständiger Befund '+t['topic_id'] for t in topics}
        params = {'max_tokens': 512, 'partial_checkpoints': False}
        ordered = sorted(topics, key=lambda t: t['topic_id'])
        wide, small = MockLLM([response(t['topic_id']) for t in ordered]), MockLLM([response(t['topic_id']) for t in ordered])
        expected = interpret_counts(basis, counted, findings, {**params, 'num_ctx': 200000}, module='swot', llm=wide)
        actual = interpret_counts(basis, counted, findings, {**params, 'num_ctx': 24000}, module='swot', llm=small)
        self.assertEqual(actual, expected)
        from runtime_context import message_bound
        for original, compact in zip(wide.calls, small.calls):
            self.assertGreater(message_bound(original, params), 24000)
            self.assertLess(message_bound(compact, params), 24000)
            original_payload, payload = json.loads(original[1]['content']), json.loads(compact[1]['content'])
            table = payload['comparison_register']
            self.assertEqual(table['encoding'], 'field_paths_rows_v1')
            rebuilt = []
            for values in table['rows']:
                row = {}
                self.assertEqual(len(table['columns']), len(values))
                for path, value in zip(table['columns'], values):
                    cursor = row
                    for name in path[:-1]:
                        cursor = cursor.setdefault(name, {})
                    cursor[path[-1]] = value
                rebuilt.append(row)
            payload['comparison_register'] = rebuilt
            self.assertEqual(payload, original_payload)
            self.assertEqual(payload['comparison_topic_count'], 30)
            self.assertIn('null bleibt nicht bestimmbar', compact[0]['content'])

    def test_register_encoding_preserves_empty_and_null_values_without_padding_missing_fields(self):
        from thematic_interpretation import _register_table
        rows = [{'id': 'ä', 'nested': {'empty': {}, 'unknown': None, 'zero': 0, 'flag': False}, 'values': []}]
        before = copy.deepcopy(rows)
        table = _register_table(rows)
        self.assertEqual(rows, before)
        self.assertEqual(table['rows'][0], ['ä', {}, False, None, 0, []])
        self.assertIsNone(_register_table([{'id': 'A'}, {'id': 'B', 'extra': None}]))

    def test_equal_labels_keep_full_distinct_definitions_and_rules_in_every_register(self):
        basis = material(['P1'])
        topics = [{**topic(tid, ['u0'], definition=definition), 'label': 'Sicherheit',
                   'inclusion': 'Einschluss ' + tid, 'exclusion': 'Ausschluss ' + tid}
                  for tid, definition in [('A', 'Sicherheit des Arbeitsplatzes'),
                                          ('B', 'Sicherheit im fachlichen Handeln')]]
        counted = count_topics(basis, topics, [])
        for module in ('clusterer', 'summarizer', 'swot', 'meta_swot', 'person_analysis',
                       'person_comparison', 'ambiguity_analysis', 'relation_analysis'):
            with self.subTest(module=module):
                llm = MockLLM([response('A'), response('B')])
                interpret_counts(basis, counted, {'A': 'Befund A', 'B': 'Befund B'},
                                 {'num_ctx': 32000, 'max_tokens': 512, 'partial_checkpoints': False},
                                 module=module, llm=llm)
                for call in llm.calls:
                    register = json.loads(call[1]['content'])['comparison_register']
                    self.assertEqual([(r['definition'], r['inclusion'], r['exclusion']) for r in register],
                                     [(t['definition'], t['inclusion'], t['exclusion']) for t in topics])

    def test_long_other_definition_is_never_silently_cut_from_register(self):
        basis = material(['P1'])
        topics = [topic('A', ['u0']), topic('Z', ['u0'], definition='Vollständige Definition 🧪 ' * 5000)]
        llm = MockLLM([])
        with self.assertRaises(ContextBudgetError):
            interpret_counts(basis, count_topics(basis, topics, []), {'A': 'Kurz', 'Z': 'Auch kurz'},
                             {'num_ctx': 32000, 'max_tokens': 512, 'partial_checkpoints': False},
                             module='swot', llm=llm)
        self.assertEqual(llm.calls, [])

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
