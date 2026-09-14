"""Common patterns use full original scope, including rare counterpositions."""
import copy
import json
import unittest
from unittest.mock import patch

from thematic_execution import execute_perspective, perspective_markdown
from test_thematic_comparison_adapter import comparison_fixture
from test_thematic_execution import SyntheticBackend
from runtime_context import ContextBudgetError


class ComparisonExecutionTests(unittest.TestCase):
    def setUp(self):
        self.params = {'model': 'synthetic', 'num_ctx': 32768, 'max_tokens': 1500,
                       'parallel_workers': 1, 'partial_checkpoints': False}
        for name in ('analysis_work.update_progress', 'runtime_context.update_progress',
                     'thematic_interpretation.begin_phase'):
            handle = patch(name); handle.start(); self.addCleanup(handle.stop)

    def test_both_shares_full_matrix_and_preserves_rare_opposition_outside_selected_people(self):
        material, people, payload = comparison_fixture(12)
        rare = next(uid for uid, unit in material['units'].items() if unit['person'] == 'P12')
        requests = []
        class Backend(SyntheticBackend):
            def __call__(self, messages, params):
                request, _ = json.JSONDecoder().raw_decode(messages[1]['content'])
                response = json.loads(super().__call__(messages, params))
                if 'cells' in request:
                    for cell in response['assignments']:
                        if cell['unit_id'] == rare: cell['status'] = 'opposed'
                else:
                    requests.append(request)
                return json.dumps(response)
        before = copy.deepcopy((material, people, payload))
        results = []
        for mode in ('frequency', 'both'):
            results.append(execute_perspective('person_comparison', mode, material, payload,
                self.params, person_payload=people, llm=Backend()))
        self.assertEqual(results[0]['counting'], results[1]['counting'])
        row = results[1]['counting']['topics'][0]
        self.assertEqual(row['coverage']['expected_cells'], len(material['units']))
        self.assertEqual(row['scope']['person_count'], 12)
        self.assertEqual(row['counts']['opposing']['exact_person_count'], 1)
        self.assertEqual(row['counts']['mentioned']['exact_person_count'], 12)
        self.assertEqual(len(requests), 2)
        self.assertIn(material['units'][rare]['text'], json.dumps(requests, ensure_ascii=False))
        self.assertEqual(results[1]['interpretation_comparison_basis'], 'all_fixed_topics')
        self.assertIn('Typen', perspective_markdown(results[1]))
        self.assertEqual((material, people, payload), before)

    def test_no_common_patterns_do_not_turn_types_into_counting_calls(self):
        material, people, payload = comparison_fixture()
        payload['gemeinsame_muster'] = []
        llm = SyntheticBackend()
        result = execute_perspective('person_comparison', 'both', material, payload,
            self.params, person_payload=people, llm=llm)
        self.assertEqual(result['counting']['topics'], [])
        self.assertEqual(llm.assignment_calls + llm.interpretation_calls, 0)
        self.assertEqual(result['unassigned_context']['typen'], payload['typen'])

    def test_long_original_pattern_fails_before_calls_without_shortening(self):
        material, people, payload = comparison_fixture()
        payload['gemeinsame_muster'][0]['verdichtung'] = 'Vollständige analytische Aussage. ' * 3000
        llm = SyntheticBackend()
        with self.assertRaises(ContextBudgetError):
            execute_perspective('person_comparison', 'both', material, payload,
                self.params, person_payload=people, llm=llm)
        self.assertEqual(llm.assignment_calls + llm.interpretation_calls, 0)


if __name__ == '__main__': unittest.main()
