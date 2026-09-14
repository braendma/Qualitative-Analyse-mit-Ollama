import copy
import json
import unittest

from thematic_execution import execute_perspective, perspective_markdown
from test_thematic_execution import SyntheticBackend
from test_thematic_synthesis_adapter import synthesis_fixture, PARAMS


class SynthesisBackend(SyntheticBackend):
    def __init__(self, *, force_class=None):
        super().__init__()
        self.selection_calls = 0
        self.force_class = force_class

    def __call__(self, messages, params):
        data, _ = json.JSONDecoder().raw_decode(messages[1]['content'])
        if 'candidate' in data:
            self.selection_calls += 1
            row = data['candidate']
            classification = self.force_class or ('material_assertion' if row['original_record']['thema'] == 'Planbarkeit' else 'group_comparison')
            return json.dumps({'candidate_id': row['candidate_id'], 'classification': classification,
                               'reason': 'Testentscheidung <script>alert(1)</script>.'})
        return super().__call__(messages, params)


class SynthesisExecutionTests(unittest.TestCase):
    def execute(self, args, llm, mode='both'):
        return execute_perspective('overall_synthesis', mode, args[0], args[1], PARAMS,
                                   source_payloads=args[2], source_bindings=args[4], source_upstreams=args[5], llm=llm)

    def test_both_and_frequency_share_selection_and_one_full_matrix(self):
        args = synthesis_fixture(); before = copy.deepcopy(args)
        results = []
        for mode in ('both', 'frequency'):
            llm = SynthesisBackend()
            result = self.execute(args, llm, mode)
            self.assertEqual(llm.selection_calls, 2)
            self.assertEqual(len(llm.seen_cells), 3)
            self.assertEqual(llm.interpretation_calls, 1)
            self.assertEqual(result['counting']['topics'][0]['counts']['mentioned']['exact_person_count'], 2)
            self.assertEqual(result['synthesis_selection']['human_review_status'], 'not_reviewed')
            results.append(result)
        self.assertEqual(results[0]['counting'], results[1]['counting'])
        self.assertEqual(results[0]['synthesis_selection'], results[1]['synthesis_selection'])
        self.assertEqual(args, before)

    def test_corrupt_source_or_old_provenance_fails_before_classification(self):
        for change in ('source', 'old', 'missing', 'binding'):
            with self.subTest(change=change):
                args = synthesis_fixture(); llm = SynthesisBackend()
                if change == 'source': args[2]['First alias']['final_summary'] = 'Changed original'
                elif change == 'old': del args[1]['source_projection_fingerprints']
                elif change == 'missing': del args[5]['clusterer']
                else: args[4]['Second alias']['module_id'] = 'foreign'
                with self.assertRaises(ValueError): self.execute(args, llm)
                self.assertEqual(llm.selection_calls + llm.assignment_calls + llm.interpretation_calls, 0)

    def test_all_context_means_no_matrix_or_frequency_calls_and_visible_reasons(self):
        llm = SynthesisBackend(force_class='mixed_or_unclear')
        result = self.execute(synthesis_fixture(), llm)
        self.assertEqual(llm.selection_calls, 2)
        self.assertEqual(llm.assignment_calls + llm.interpretation_calls, 0)
        self.assertEqual(result['counting']['topics'], [])
        rendered = perspective_markdown(result)
        self.assertIn('Nicht thematisch gezählte Synthesebefunde', rendered)
        self.assertIn('Gruppe A spricht häufiger', rendered)
        self.assertIn('nicht menschlich bestätigt', rendered)
        self.assertNotIn('<script>', rendered)

    def test_model_misclassification_is_visible_without_claiming_human_truth(self):
        result = self.execute(synthesis_fixture(), SynthesisBackend(force_class='material_assertion'))
        self.assertEqual(len(result['counting']['topics']), 2)
        rendered = perspective_markdown(result)
        self.assertIn('Modellvorschlag, nicht menschlich bestätigt', rendered)
        self.assertIn('Gruppe A spricht häufiger', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertIn('First alias', rendered)


if __name__ == '__main__':
    unittest.main()
