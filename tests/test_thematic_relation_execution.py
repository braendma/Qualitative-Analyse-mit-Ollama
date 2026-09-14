"""Relation assertion assignment and independent code counts share original inputs."""
import copy
import json
import unittest
from unittest.mock import patch

from thematic_execution import execute_perspective, perspective_markdown
from relation_cooccurrence import count_code_path_cooccurrences
from test_thematic_execution import SyntheticBackend
from test_thematic_relation_adapter import relation_fixture


class RelationBackend(SyntheticBackend):
    def __init__(self, status='supported'):
        super().__init__()
        self.status = status
        self.interpretation_inputs = []

    def __call__(self, messages, params):
        payload, _ = json.JSONDecoder().raw_decode(messages[1]['content'])
        if 'cells' in payload:
            self.assignment_calls += 1
            self.seen_cells.extend(payload['cells'])
            return json.dumps({'assignments': [{**cell, 'status': self.status} for cell in payload['cells']]})
        self.interpretation_inputs.append(payload)
        return super().__call__(messages, params)


class ThematicRelationExecutionTests(unittest.TestCase):
    def setUp(self):
        self.params = {'model': 'synthetic', 'num_ctx': 32000, 'max_tokens': 1500,
                       'parallel_workers': 1, 'partial_checkpoints': False}
        for name in ('analysis_work.update_progress', 'runtime_context.update_progress', 'thematic_interpretation.begin_phase'):
            handle = patch(name); handle.start(); self.addCleanup(handle.stop)

    def run_fixture(self, values, mode='both', llm=None):
        material, clusters, summaries, payload = values
        return execute_perspective('relation_analysis', mode, material, payload, self.params,
            cluster_payload=clusters, summary_payload=summaries, llm=llm or RelationBackend())

    def test_complete_original_matrix_not_selected_code_examples(self):
        values = relation_fixture(); material = values[0]; before = copy.deepcopy(values)
        llm = RelationBackend(); result = self.run_fixture(values, llm=llm)
        self.assertEqual(values, before)
        self.assertTrue(result['counting']['topics'])
        expected = {(topic['topic_id'], uid) for topic in result['counting']['definitions'] for uid in material['units']}
        self.assertEqual({(cell['topic_id'], cell['unit_id']) for cell in llm.seen_cells}, expected)
        self.assertEqual(len(llm.seen_cells), len(expected))
        for row in result['counting']['topics']:
            self.assertEqual(row['scope']['person_count'], len(material['persons']))
            self.assertEqual(row['counts']['mentioned']['exact_person_count'], len(material['persons']))
        for payload in llm.interpretation_inputs:
            self.assertEqual(payload['comparison_basis'], 'all_fixed_topics')
            self.assertEqual(payload['comparison_topic_count'], len(result['counting']['topics']))
            self.assertTrue(all(row['definition'] for row in payload['comparison_register']))
            self.assertNotIn('code_cooccurrence', payload)
        self.assertEqual(result['code_cooccurrence'], count_code_path_cooccurrences(material))
        self.assertEqual(llm.interpretation_calls, len(result['counting']['topics']))

    def test_different_semantic_assignments_never_change_existing_code_counts(self):
        values = relation_fixture()
        supported = self.run_fixture(values, llm=RelationBackend('supported'))
        absent = self.run_fixture(values, llm=RelationBackend('no_evidence'))
        self.assertNotEqual(supported['counting'], absent['counting'])
        self.assertEqual(supported['code_cooccurrence'], absent['code_cooccurrence'])
        self.assertEqual(absent['counting']['topics'][0]['counts']['mentioned']['exact_person_count'], 0)
        self.assertTrue(any(row['persons']['intersection']['count'] > 0 for row in absent['code_cooccurrence']['pairs']))

    def test_both_reuses_same_number_of_calls_and_identical_counts(self):
        values = relation_fixture(); a = RelationBackend(); b = RelationBackend()
        both = self.run_fixture(values, llm=a)
        frequency = self.run_fixture(values, 'frequency', b)
        self.assertEqual((a.assignment_calls, a.interpretation_calls), (b.assignment_calls, b.interpretation_calls))
        self.assertEqual(both['counting'], frequency['counting'])
        self.assertEqual(both['code_cooccurrence'], frequency['code_cooccurrence'])
        self.assertEqual(set(frequency['interpretations']), {'frequency'})
        self.assertEqual(set(both['interpretations']), {'qualitative', 'frequency'})

    def test_no_semantic_findings_still_yields_complete_model_free_code_counts(self):
        values = relation_fixture(); payload = values[-1]
        payload['beziehungen'] = []
        payload['candidate_pair_count_with_relation'] = 0
        payload['candidate_pair_count_without_validated_relation'] = payload['candidate_pair_count_submitted']
        llm = RelationBackend(); result = self.run_fixture(values, llm=llm)
        self.assertEqual(result['counting']['topics'], [])
        self.assertTrue(result['code_cooccurrence']['pairs'])
        self.assertEqual(llm.assignment_calls + llm.interpretation_calls, 0)
        self.assertIn('Gemeinsames Auftreten vorhandener Codepfade', perspective_markdown(result))

    def test_invalid_original_summary_fails_before_any_assignment(self):
        values = relation_fixture(); values[2]['cluster_summaries'][0]['summary'] = 'Changed source'
        llm = RelationBackend()
        with self.assertRaises(ValueError): self.run_fixture(values, llm=llm)
        self.assertEqual(llm.assignment_calls + llm.interpretation_calls, 0)

    def test_cross_person_context_is_visible_and_not_semantically_counted(self):
        from test_relation_selection import _payload
        material, clusters, summaries, _ = relation_fixture()
        payload = _payload(material, clusters, summaries, across=True)
        result = self.run_fixture((material, clusters, summaries, payload))
        self.assertEqual(result['counting']['topics'], [])
        self.assertEqual(result['unassigned_context']['records'][0]['reason'], 'cross_person_evidence')
        text = perspective_markdown(result)
        self.assertIn('Nicht thematisch gezählte Befunde', text)
        self.assertIn('Gemeinsames Auftreten vorhandener Codepfade', text)
        self.assertTrue(result['code_cooccurrence']['pairs'])


if __name__ == '__main__':
    unittest.main()
