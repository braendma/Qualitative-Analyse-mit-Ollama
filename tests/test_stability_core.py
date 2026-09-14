import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from coding_validation_common import Segment
from stability_core import analyze_stage_repetitions, analyze_coding_repetitions
from test_codebook_diagnostics import book, single, multi, verify


def samples(*payloads):
    return [{'sample_id': f'repeat-{i}', 'status': 'success', 'payload': p}
            for i, p in enumerate(payloads)]


def clusters(*groups):
    return {'clusters': [{'cluster_name': f'Name{i}', 'segments': group} for i, group in enumerate(groups)]}


def swot(dimension='Stärken', text='Ein Thema', ids=None):
    return {'swot': {'Code/1': {d: [{'thema': text, 'segment_ids': ids or ['a']}] if d == dimension else []
                              for d in ('Stärken', 'Schwächen', 'Chancen', 'Risiken')}}}


class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.segments = [Segment(s, 'Künstlicher Text', 'A', 'P') for s in ('a', 'b', 'c')]
        self.book = [book('A'), book('B')]

    def stage(self, mid, *payloads):
        return analyze_stage_repetitions(self.segments, mid, samples(*payloads))

    def coding(self, *payloads, mid='blind_coding', **kwargs):
        return analyze_coding_repetitions(self.segments, self.book, mid, samples(*payloads), **kwargs)

    def test_cluster_renaming_order_and_overlapping_memberships(self):
        a = clusters(['a', 'b'], ['b', 'c'])
        b = clusters(['c', 'b'], ['b', 'a'])
        b['clusters'][0]['cluster_name'] = 'Ganz anders'
        result = self.stage('clusterer', a, b)
        pair = result['pairs'][0]
        self.assertEqual(pair['cluster_membership_overlap']['value'], 1)
        self.assertEqual(pair['coassignment_overlap']['value'], 1)
        self.assertLess(pair['projected_record_overlap']['value'], 1)

    def test_cluster_changes_not_hidden_by_same_segment_inventory(self):
        pair = self.stage('clusterer', clusters(['a', 'b'], ['c']), clusters(['a'], ['b', 'c']))['pairs'][0]
        self.assertEqual(pair['reference_comparisons'][0]['segment_overlap']['value'], 1)
        self.assertEqual(pair['cluster_membership_overlap']['value'], 0)
        self.assertEqual(pair['coassignment_overlap']['value'], 0)

    def test_empty_results_not_maximal_stability(self):
        pair = self.stage('clusterer', clusters(), clusters())['pairs'][0]
        self.assertIsNone(pair['projected_record_overlap']['value'])
        self.assertIsNone(pair['coassignment_overlap']['value'])
        self.assertEqual(pair['reference_comparisons'], [])

    def test_dimension_change_is_not_same_finding(self):
        result = self.stage('swot', swot(), swot('Risiken'))
        self.assertEqual(result['pairs'][0]['projected_record_overlap']['value'], 0)
        self.assertEqual(len(result['pairs'][0]['reference_comparisons']), 2)
        self.assertTrue(all(r['repeat_status'] == 'variable' for r in result['record_occurrences']))

    def test_identical_projection_order_and_multiplicity(self):
        a = swot()
        a['swot']['Code/1']['Stärken'].append({'thema': 'Anderer Befund', 'segment_ids': ['b']})
        b = copy.deepcopy(a)
        b['swot']['Code/1']['Stärken'].reverse()
        self.assertEqual(self.stage('swot', a, b)['pairs'][0]['projected_record_overlap']['value'], 1)
        b['swot']['Code/1']['Stärken'].append(copy.deepcopy(b['swot']['Code/1']['Stärken'][0]))
        self.assertAlmostEqual(self.stage('swot', a, b)['pairs'][0]['projected_record_overlap']['value'], 2 / 3)

    def test_long_unicode_text_compared_fully_preview_explicit(self):
        text = 'Äußerung 😀 ' * 5000
        a, b = swot(text=text), swot(text=text + ' nicht')
        before = copy.deepcopy(a)
        result = self.stage('swot', a, b)
        self.assertEqual(result['pairs'][0]['projected_record_overlap']['value'], 0)
        self.assertTrue(result['record_occurrences'][0]['text_preview_truncated'])
        self.assertEqual(result['pairs'][0]['projected_reference_binding_overlap']['value'], 1)
        self.assertEqual(a, before)
        equivalent = self.stage('swot', swot(text='Äußerung\n gut'), swot(text='A\u0308ußerung   gut'))
        self.assertEqual(equivalent['pairs'][0]['projected_record_overlap']['value'], 1)

    def test_failures_invalid_ids_and_unresolved_refs_excluded(self):
        data = samples(swot(), swot(ids=['foreign']), swot())
        data[2]['status'] = 'failed'
        result = analyze_stage_repetitions(self.segments, 'swot', data)
        self.assertEqual(result['included_samples'], ['repeat-0'])
        self.assertEqual(result['pairs'], [])
        self.assertEqual(result['comparison_status'], 'not_computable')
        self.assertEqual(result['record_occurrences'][0]['repeat_status'], 'not_computable')
        meta = {'finding_registry': {}, 'meta_swot': {'Stärken': {
            'uebergreifende_muster': [{'finding_ids': ['missing']}], 'einzelbefunde': []}}}
        self.assertEqual(self.stage('meta_swot', meta, meta)['included_samples'], [])

    def test_negative_cases_have_people_not_invented_segment_evidence(self):
        payload = {'dominante_muster': [], 'negativfaelle': [{'person': 'P', 'abweichung': 'Selten'}],
                   'spannungen_zwischen_typen': [], 'relativierungen': []}
        result = self.stage('contrast_analysis', payload, payload)
        ref = result['pairs'][0]['reference_comparisons'][0]
        self.assertEqual(ref['scope'], 'person_reference')
        self.assertIsNone(ref['segment_overlap']['value'])
        self.assertEqual(ref['person_overlap']['value'], 1)
        bad = copy.deepcopy(payload)
        bad['negativfaelle'][0]['person'] = 'Foreign'
        self.assertEqual(len(self.stage('contrast_analysis', bad, payload)['excluded_samples']), 1)

    def test_group_context_never_becomes_direct_evidence(self):
        payload = {'kernergebnisse': [{'thema': 'Befund', 'quellen': ['N1']}],
            'uebergreifende_muster': [], 'spannungen_und_relativierungen': [],
            'hierarchical_reduction': {'nodes': {'N1': {'input_ids': ['L1']}},
                'leaves': {'L1': {'source': 'SWOT', 'content': {'segment_ids': ['a']}}}}}
        result = self.stage('overall_synthesis', payload, payload)
        self.assertEqual(result['pairs'][0]['reference_comparisons'][0]['scope'], 'source_group')
        self.assertTrue(result['sample_details'][0]['warnings'])

    def test_pair_limit_avoids_quadratic_allocation(self):
        segments = [Segment(str(i), 'Text', 'A', 'P') for i in range(500)]
        payload = clusters([s.segment_id for s in segments])
        result = analyze_stage_repetitions(segments, 'clusterer', samples(payload, payload))
        self.assertEqual(result['sample_details'][0]['coassignment']['status'], 'not_calculated')
        self.assertIsNone(result['pairs'][0]['coassignment_overlap'])
        self.assertEqual(result['pairs'][0]['cluster_membership_overlap']['value'], 1)

    def test_coding_abstention_none_and_failure_denominators(self):
        a = single(self.segments, ['A', 'unklar', 'keine_zuordnung'])
        b = single(self.segments, ['B', 'unklar', 'keine_zuordnung'])
        result = self.coding(a, b)
        pair = result['pairs'][0]
        self.assertEqual(pair['state_agreement']['value'], 1)
        self.assertEqual(pair['code_set_agreement'], {'numerator': 1, 'denominator': 2, 'value': .5})
        a['results'][0]['processing_status'] = 'failed'
        result = self.coding(a, b)
        self.assertEqual(result['pairs'][0]['technical_excluded_units'], 1)
        self.assertEqual(result['pairs'][0]['code_set_agreement']['denominator'], 1)
        self.assertEqual(result['processing_status'], 'incomplete')
        self.assertEqual(result['code_occurrences'][0]['per_sample'][0]['units'], 0)

    def test_no_decisive_coding_is_not_perfect_code_agreement(self):
        a = single(self.segments, ['unklar'] * 3)
        pair = self.coding(a, a)['pairs'][0]
        self.assertIsNone(pair['code_set_agreement']['value'])
        self.assertEqual(pair['state_agreement']['value'], 1)

    def test_verification_alternatives_separate_from_actual_assignments(self):
        a, b = verify(self.segments), verify(self.segments)
        b['results'][0]['verification'] = 'unklar'
        b['results'][0]['alternative_codes'] = ['B']
        result = self.coding(a, b, mid='code_verification')
        self.assertAlmostEqual(result['pairs'][0]['state_agreement']['value'], 2/3)
        self.assertNotIn('code_set_agreement', result['pairs'][0])
        self.assertEqual(result['code_occurrences'][1]['role'], 'verification_alternative')

    def test_multi_passages_count_once_and_sets_ignore_order(self):
        self.segments = [Segment('a', 'Same', 'A', 'P', 'u'), Segment('b', 'Same', 'B', 'P', 'u'),
                         Segment('c', 'Else', 'A', 'P', 'v')]
        a = multi(self.segments, {'u': (['A','B'], 'assigned'), 'v': ([], 'none')})
        b = multi(self.segments, {'u': (['B','A'], 'assigned'), 'v': ([], 'none')})
        result = self.coding(a, b, label_mode='multi_label')
        self.assertEqual(result['n_units'], 2)
        self.assertEqual(result['pairs'][0]['code_set_agreement']['value'], 1)
        self.assertEqual(result['code_occurrences'][0]['per_sample'][0]['units'], 1)
        b['results'][0]['predicted_codes'] = ['A']
        self.assertEqual(len(self.coding(a, b, label_mode='multi_label')['excluded_samples']), 1)

    def test_rejects_unknown_status_duplicate_ids_and_original_ids(self):
        data = samples(clusters(), clusters())
        data[1]['sample_id'] = data[0]['sample_id']
        with self.assertRaises(ValueError):
            analyze_stage_repetitions(self.segments, 'clusterer', data)
        data = samples(clusters(), clusters()); data[0]['status'] = 'typo'
        with self.assertRaises(ValueError):
            analyze_stage_repetitions(self.segments, 'clusterer', data)
        with self.assertRaises(ValueError):
            analyze_stage_repetitions(self.segments * 2, 'clusterer', samples(clusters(), clusters()))

    def test_missing_or_fabricated_coding_rows_exclude_sample(self):
        a = single(self.segments, ['A'] * 3)
        b = copy.deepcopy(a); b['results'].pop()
        self.assertEqual(self.coding(a, b)['comparison_status'], 'not_computable')
        b = copy.deepcopy(a); b['results'][0]['predicted_code'] = 'Fabricated'
        self.assertEqual(self.coding(a, b)['excluded_samples'][0]['reason'], 'invalid_artifact')


if __name__ == '__main__':
    unittest.main()
