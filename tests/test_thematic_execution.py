"""Actual adapter -> matrix -> count -> interpretation, using artificial models."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from thematic_execution import execute_perspective, perspective_markdown
from thematic_material import load_counting_material
from test_thematic_material import workspace
from test_thematic_memberships import fixture
from test_thematic_adapters import summary, swot


class SyntheticBackend:
    def __init__(self):
        self.assignment_calls = 0
        self.interpretation_calls = 0
        self.fail_on_assignment_call = None
        self.seen_cells = []

    def __call__(self, messages, params):
        # Fixed correction suffix may follow the original JSON in assignment calls.
        payload, _ = json.JSONDecoder().raw_decode(messages[1]['content'])
        if 'cells' in payload:
            self.assignment_calls += 1
            if self.assignment_calls == self.fail_on_assignment_call:
                self.fail_on_assignment_call = None
                raise RuntimeError('Synthetic temporary backend interruption')
            self.seen_cells.extend(payload['cells'])
            return json.dumps({'assignments': [{**cell, 'status': 'supported'} for cell in payload['cells']]})
        self.interpretation_calls += 1
        tid = payload['topic']['topic_id']
        count = next(r for r in payload['comparison_register'] if r['topic_id'] == tid)
        # Artificial response intentionally depends on computed data. This verifies
        # the wiring, not the accuracy of any real language model.
        return json.dumps({'topic_id': tid,
            'interpretation': 'Berechnete Personenbreite berücksichtigen: ' + str(count['counts']['mentioned']['exact_person_count']),
            'counterpositions': 'Seltene Gegenpositionen bleiben relevant.',
            'limitations': 'Kein Beweis menschlich validierter Themenhäufigkeit.'})


class ThematicExecutionTests(unittest.TestCase):
    def setUp(self):
        self.material, self.clusters = fixture()
        self.params = {'model': 'synthetic', 'max_tokens': 1500, 'num_ctx': 32000,
                       'partial_checkpoints': False, 'parallel_workers': 1}

    def test_qualitative_default_needs_no_new_material_or_calls(self):
        llm = SyntheticBackend()
        for module in ('clusterer', 'summarizer', 'swot'):
            self.assertIsNone(execute_perspective(module, 'qualitative', None, {}, self.params, llm=llm))
        self.assertEqual(llm.assignment_calls + llm.interpretation_calls, 0)
        self.assertEqual(perspective_markdown(None), '')

    def test_cluster_and_summary_both_reuse_memberships_without_classification(self):
        for module in ('clusterer', 'summarizer'):
            with self.subTest(module=module):
                payload = self.clusters if module == 'clusterer' else summary(self.clusters)
                before = copy.deepcopy((self.material, self.clusters, payload))
                llm = SyntheticBackend()
                result = execute_perspective(module, 'both', self.material, payload, self.params,
                                             cluster_payload=self.clusters, llm=llm)
                self.assertEqual(llm.assignment_calls, 0)
                self.assertEqual(llm.interpretation_calls, len(self.clusters['clusters']))
                self.assertEqual(set(result['interpretations']), {'qualitative', 'frequency'})
                self.assertEqual(result['candidate_basis'], 'original_unweighted_findings')
                self.assertEqual(before, (self.material, self.clusters, payload))
                self.assertTrue(all(r['coverage']['complete'] for r in result['counting']['topics']))
                if module == 'summarizer':
                    self.assertEqual(result['unassigned_context']['final_summary'], payload['final_summary'])

    def test_swot_matrix_covers_all_original_units_not_only_selected_quotes(self):
        payload = swot(self.material, self.clusters)
        before = copy.deepcopy(payload); llm = SyntheticBackend()
        result = execute_perspective('swot', 'both', self.material, payload, self.params, llm=llm)
        counts = result['counting']
        self.assertEqual(len(llm.seen_cells), len(counts['assignments']))
        self.assertEqual(len({(r['topic_id'], r['unit_id']) for r in llm.seen_cells}), len(llm.seen_cells))
        self.assertEqual(payload, before)
        self.assertEqual(result['assignment_origin'], 'full_scoped_model_assignment')
        self.assertTrue(all(t['count_meaning'] == 'material_support_for_inference' for t in counts['topics']))
        self.assertTrue(any(t['counts']['mentioned']['exact_unit_count'] > 1 for t in counts['topics']))
        self.assertEqual(len(result['interpretations']['frequency']), len(result['interpretations']['qualitative']))

    def test_frequency_and_both_share_same_matrix_and_workload(self):
        payload = swot(self.material, self.clusters)
        a, b = SyntheticBackend(), SyntheticBackend()
        first = execute_perspective('swot', 'frequency', self.material, payload, self.params, llm=a)
        second = execute_perspective('swot', 'both', self.material, payload, self.params, llm=b)
        self.assertEqual(first['counting'], second['counting'])
        self.assertEqual(first['interpretations']['frequency'], second['interpretations']['frequency'])
        self.assertEqual((a.assignment_calls, a.interpretation_calls), (b.assignment_calls, b.interpretation_calls))
        self.assertEqual(set(first['interpretations']), {'frequency'})

    def test_markdown_exposes_counts_limits_separate_perspectives_and_escapes_html(self):
        result = execute_perspective('clusterer', 'both', self.material, self.clusters, self.params, llm=SyntheticBackend())
        result['interpretations']['frequency'][0]['interpretation'] = '<script>bad()</script>'
        result['counting']['definitions'][0]['label'] = 'Title\n# heading | [link](url)'
        rendered = perspective_markdown(result)
        self.assertIn('Qualitative Perspektive', rendered)
        self.assertIn('Häufigkeitsinformierte Perspektive', rendered)
        self.assertIn('Beobachtete Personen', rendered)
        self.assertIn('keine menschliche Bestätigung', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('Title \\# heading \\| \\[link\\]\\(url\\)', rendered)

    def test_verified_twelve_people_twentyfour_parts_stay_twelve_in_executed_swot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = workspace(Path(tmp))
            material = load_counting_material(path)
            metadata = {sid: {'person': material['units'][row['unit_id']]['person'],
                             'unit_id': row['unit_id'][len('passage:'):]}
                        for sid, row in material['segment_index'].items()}
            payload = swot(material, {'segment_metadata': metadata})
            llm = SyntheticBackend()
            result = execute_perspective('swot', 'both', material, payload, self.params, llm=llm)
            topic = result['counting']['topics'][0]
            self.assertEqual(topic['scope']['person_count'], 12)
            self.assertEqual(topic['scope']['unit_count'], 24)
            self.assertEqual(topic['counts']['mentioned']['exact_person_count'], 12)
            self.assertEqual(topic['counts']['mentioned']['exact_passage_count'], 24)
            self.assertEqual(len(llm.seen_cells), 24)
            self.assertEqual(len(next(iter(result['source_links'].values()))['selected_evidence_segment_ids']), 1)

    def test_actual_checkpoint_resume_finishes_failed_matrix_without_repeating_successful_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = {**self.params, 'partial_checkpoints': True, 'partial_checkpoint_dir': tmp, 'batch_items': 1}
            llm = SyntheticBackend(); llm.fail_on_assignment_call = 2
            payload = swot(self.material, self.clusters)
            with self.assertRaises(RuntimeError):
                execute_perspective('swot', 'both', self.material, payload, settings, llm=llm)
            successful_before = len(llm.seen_cells)
            self.assertGreater(successful_before, 0)
            result = execute_perspective('swot', 'both', self.material, payload, settings, llm=llm)
            self.assertEqual(len(llm.seen_cells), len(result['counting']['assignments']))
            before = (llm.assignment_calls, llm.interpretation_calls)
            again = execute_perspective('swot', 'both', self.material, payload, settings, llm=llm)
            self.assertEqual(before, (llm.assignment_calls, llm.interpretation_calls))
            self.assertEqual(result, again)
            changed = copy.deepcopy(payload)
            changed['swot']['A']['Chancen'][0]['analyse'] += ' Changed finding.'
            # New fixed topic ID creates new classification checkpoints; existing
            # unchanged topics can still be bound to a changed global registry.
            with self.assertRaises(ValueError):
                execute_perspective('swot', 'both', self.material, changed, settings, llm=llm)


if __name__ == '__main__':
    unittest.main()
