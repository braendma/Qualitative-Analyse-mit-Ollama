"""Execute additional adapters through the shared pipeline with synthetic models."""
import copy
import json
import tempfile
import unittest

from thematic_execution import execute_perspective, perspective_markdown
from thematic_pipeline import capability, modes
from test_thematic_execution import SyntheticBackend
from test_thematic_meta_adapter import meta_fixture
from test_thematic_person_adapters import fixture as person_fixture
from llm_client import ContextBudgetError


class ThematicCaseExecutionTests(unittest.TestCase):
    def setUp(self):
        self.params = {'model': 'synthetic', 'max_tokens': 1500, 'num_ctx': 32000,
                       'partial_checkpoints': False, 'parallel_workers': 1}

    def test_meta_uses_original_material_matrix_and_preserves_candidates(self):
        material, source, payload = meta_fixture()
        before = copy.deepcopy((material, source, payload))
        llm = SyntheticBackend()
        result = execute_perspective('meta_swot', 'both', material, payload,
                                     self.params, swot_payload=source, llm=llm)
        self.assertEqual(before, (material, source, payload))
        self.assertEqual(result['assignment_origin'], 'full_scoped_model_assignment')
        self.assertEqual(len(llm.seen_cells), 3)
        topic = result['counting']['topics'][0]
        self.assertEqual(topic['scope']['person_count'], 2)
        self.assertEqual(topic['counts']['mentioned']['exact_person_count'], 2)
        self.assertEqual(topic['counts']['mentioned']['exact_passage_count'], 3)
        self.assertEqual(set(result['interpretations']), {'qualitative', 'frequency'})
        self.assertIn('Neue Meta-Befunde', perspective_markdown(result))
        self.assertIn('keine Addition', perspective_markdown(result))

    def test_meta_both_does_not_duplicate_matrix_work_or_use_upstream_weighted_prose(self):
        material, source, payload = meta_fixture()
        first, second = SyntheticBackend(), SyntheticBackend()
        a = execute_perspective('meta_swot', 'frequency', material, payload,
                                self.params, swot_payload=source, llm=first)
        source['analysis_perspective'] = {'interpretation': 'Must not replace original findings.'}
        b = execute_perspective('meta_swot', 'both', material, payload,
                                self.params, swot_payload=source, llm=second)
        self.assertEqual(a['counting'], b['counting'])
        self.assertEqual(a['candidate_source_fingerprint'], b['candidate_source_fingerprint'])
        self.assertEqual(a['interpretations']['frequency'], b['interpretations']['frequency'])
        self.assertEqual((first.assignment_calls, first.interpretation_calls),
                         (second.assignment_calls, second.interpretation_calls))

    def test_meta_mismatched_or_missing_source_fails_before_any_model_call(self):
        material, source, payload = meta_fixture()
        changed = copy.deepcopy(source)
        changed['swot']['A']['Chancen'][0]['analyse'] = 'Changed original candidate'
        for upstream in (None, changed):
            with self.subTest(upstream=upstream is None):
                llm = SyntheticBackend()
                with self.assertRaises(ValueError):
                    execute_perspective('meta_swot', 'frequency', material, payload,
                                        self.params, swot_payload=upstream, llm=llm)
                self.assertEqual(llm.assignment_calls + llm.interpretation_calls, 0)

    def test_interrupted_meta_matrix_resumes_real_checkpoints(self):
        material, source, payload = meta_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            params = {**self.params, 'partial_checkpoints': True,
                      'partial_checkpoint_dir': tmp, 'batch_items': 1}
            llm = SyntheticBackend()
            llm.fail_on_assignment_call = 2
            with self.assertRaises(RuntimeError):
                execute_perspective('meta_swot', 'both', material, payload, params,
                                    swot_payload=source, llm=llm)
            result = execute_perspective('meta_swot', 'both', material, payload, params,
                                         swot_payload=source, llm=llm)
            self.assertEqual(len(llm.seen_cells), len(result['counting']['assignments']))
            calls = (llm.assignment_calls, llm.interpretation_calls)
            repeated = execute_perspective('meta_swot', 'both', material, payload, params,
                                           swot_payload=source, llm=llm)
            self.assertEqual(calls, (llm.assignment_calls, llm.interpretation_calls))
            self.assertEqual(result, repeated)

    def test_internal_adapters_do_not_bypass_application_release_gate(self):
        for module in ('meta_swot', 'person_analysis', 'ambiguity_analysis'):
            with self.subTest(module=module):
                cap = capability({'id': module, 'script': module + '.py'})
                self.assertFalse(cap['implemented'])
                with self.assertRaises(ValueError):
                    modes({'analysis_perspectives': {module: 'both'}})

    def test_person_execution_counts_each_full_case_without_merging_matching_titles(self):
        material, persons, _ = person_fixture()
        before = copy.deepcopy(persons)
        llm = SyntheticBackend()
        result = execute_perspective('person_analysis', 'both', material, persons,
                                     self.params, llm=llm)
        self.assertEqual(persons, before)
        self.assertEqual(len(result['counting']['topics']), 8)
        self.assertEqual(len(llm.seen_cells), 16)
        for topic in result['counting']['topics']:
            self.assertEqual(topic['scope']['person_count'], 1)
            self.assertEqual(topic['scope']['unit_count'], 2)
            self.assertEqual(topic['counts']['mentioned']['exact_person_count'], 1)
            self.assertEqual(topic['counts']['mentioned']['exact_passage_count'], 2)
        rendered = perspective_markdown(result)
        self.assertIn('innerhalb dieses Falles', rendered)
        self.assertIn('keine Mehrheit', rendered)

    def test_ambiguity_sides_can_both_be_supported_without_becoming_opposites(self):
        material, persons, ambiguity = person_fixture()
        llm = SyntheticBackend()
        result = execute_perspective('ambiguity_analysis', 'both', material, ambiguity,
                                     self.params, person_payload=persons, llm=llm)
        self.assertEqual(len(result['counting']['topics']), 4)
        self.assertEqual(len(llm.seen_cells), 8)
        pairs = {}
        for topic in result['counting']['topics']:
            tid = topic['topic_id']; link = result['source_links'][tid]
            pairs.setdefault(link['pair_id'], {})[link['side']] = topic
            self.assertEqual(topic['counts']['supporting']['exact_person_count'], 1)
            self.assertEqual(topic['counts']['opposing']['exact_person_count'], 0)
            self.assertEqual(topic['counts']['both']['exact_person_count'], 0)
        self.assertEqual(len(pairs), 2)
        for sides in pairs.values():
            self.assertEqual(set(sides), {'A', 'B'})
            self.assertEqual(sides['A']['counts']['supporting']['unit_ids'],
                             sides['B']['counts']['supporting']['unit_ids'])
        rendered = perspective_markdown(result)
        self.assertIn('nicht die gemeinsame Nennung von A und B', rendered)
        self.assertIn('nicht automatisch ihre Negation', rendered)

    def test_unclear_side_blocks_only_its_exact_metrics_and_is_visible_to_interpreter(self):
        material, persons, ambiguity = person_fixture(1)
        registers = []
        class UnclearSide(SyntheticBackend):
            def __call__(self, messages, params):
                request, _ = json.JSONDecoder().raw_decode(messages[1]['content'])
                response = json.loads(super().__call__(messages, params))
                if 'cells' in request:
                    for cell in response['assignments']:
                        if cell['topic_id'].endswith('_A'):
                            cell['status'] = 'unclear'
                else:
                    registers.append(request['comparison_register'])
                return json.dumps(response)
        result = execute_perspective('ambiguity_analysis', 'frequency', material, ambiguity,
                                     self.params, person_payload=persons, llm=UnclearSide())
        by_side = {t['topic_id'][-1]: t for t in result['counting']['topics']}
        self.assertIsNone(by_side['A']['counts']['mentioned']['exact_person_count'])
        self.assertEqual(by_side['B']['counts']['mentioned']['exact_person_count'], 1)
        self.assertEqual(len(registers), 2)
        self.assertEqual(registers[0], registers[1])
        self.assertTrue(any(t['counts']['mentioned']['exact_person_count'] is None for t in registers[0]))
        self.assertIn('nicht bestimmbar', perspective_markdown(result))

    def test_long_ambiguity_positions_fail_without_shortening_or_model_calls(self):
        material, persons, ambiguity = person_fixture(1)
        ambiguity['persons']['P01']['ambivalenzen'][0]['position_a'] = 'Langer unveränderter Originalbefund. ' * 3000
        llm = SyntheticBackend()
        with self.assertRaises(ContextBudgetError):
            execute_perspective('ambiguity_analysis', 'both', material, ambiguity,
                                self.params, person_payload=persons, llm=llm)
        self.assertEqual(llm.assignment_calls + llm.interpretation_calls, 0)


if __name__ == '__main__':
    unittest.main()
