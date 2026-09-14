import copy
import unittest

from test_stability_core import clusters, swot, samples
from test_codebook_diagnostics import book, single, multi, verify
from coding_validation_common import Segment
from sensitivity_core import analyze_sensitivity


class SensitivityCoreTests(unittest.TestCase):
    def setUp(self):
        self.segments = [Segment('a', '<script>Sehr langer künstlicher Text</script>' * 100, 'A', 'Person Eins')]
        self.book = [book('A'), book('B')]

    def compare(self, groups, mid='blind_coding', **kwargs):
        configs = [{'configuration_id': cid} for cid in groups]
        data = [{**s, 'sample_id': cid + '-' + str(i), 'configuration_id': cid}
                for cid, group in groups.items() for i, s in enumerate(group)]
        return analyze_sensitivity(self.segments, self.book, mid, configs, data, **kwargs)

    def test_within_variation_and_between_variation_have_distinct_denominators(self):
        a, b = single(self.segments, ['A']), single(self.segments, ['B'])
        result = self.compare({'baseline': samples(a, a), 'warm': samples(a, b)})
        row = next(f for f in result['findings'] if f['feature_type'] == 'code_presence' and f['value'] == 'A')
        self.assertEqual(row['any_observed_repeat']['value'], 1)
        self.assertEqual(row['all_observed_repeats']['value'], .5)
        self.assertEqual(row['all_repeats_complete_only']['denominator'], 2)
        self.assertTrue(row['observed_patterns_differ'])
        self.assertEqual(result['within_configurations']['baseline']['pairs'][0]['code_set_agreement']['value'], 1)
        self.assertEqual(result['within_configurations']['warm']['pairs'][0]['code_set_agreement']['value'], 0)
        self.assertTrue(row['text_preview_truncated'])
        self.assertEqual(row['text_characters'], len(self.segments[0].text))

    def test_partial_and_failed_are_never_absence_or_stable_single_repeats(self):
        a = single(self.segments, ['A'])
        fail = {'sample_id': 'x', 'status': 'failed'}
        result = self.compare({'baseline': samples(a, a), 'partial': [samples(a)[0], fail], 'missing': [fail, fail]})
        row = next(f for f in result['findings'] if f['feature_type'] == 'code_presence')
        self.assertEqual(row['any_observed_repeat']['denominator'], 2)
        self.assertEqual(row['all_observed_repeats']['denominator'], 1)
        self.assertEqual(row['any_repeat_complete_only']['denominator'], 1)
        self.assertEqual(row['excluded_configurations'], ['missing'])
        self.assertEqual(row['provisional_configurations'], ['partial'])
        self.assertEqual(row['planned_configurations'], 3)
        self.assertEqual(result['processing_status'], 'incomplete')

    def test_none_abstention_and_technical_failure_do_not_share_code_denominators(self):
        a, none, abstain = (single(self.segments, [v]) for v in ('A', 'keine_zuordnung', 'unklar'))
        broken = copy.deepcopy(a); broken['results'][0]['processing_status'] = 'failed'
        result = self.compare({'baseline': samples(a, none), 'uncertain': samples(abstain, broken)})
        row = next(f for f in result['findings'] if f['feature_type'] == 'code_presence')
        self.assertEqual(row['per_configuration']['uncertain']['evaluated_repetitions'], 0)
        self.assertEqual(row['per_configuration']['uncertain']['technical_failure_repetitions'], 1)
        self.assertEqual(row['per_configuration']['uncertain']['abstention_excluded_repetitions'], 1)
        self.assertEqual(row['any_observed_repeat']['denominator'], 1)
        state = next(f for f in result['findings'] if f['feature_type'] == 'decision_state' and f['value'] == 'abstained')
        self.assertEqual(state['per_configuration']['uncertain']['evaluated_repetitions'], 1)
        self.assertTrue(any(f['feature_type'] == 'code_set' and f['value'] == [] for f in result['findings']))

    def test_cluster_names_not_membership_and_swot_dimensions_not_equivalent(self):
        a, b = clusters(['a']), clusters(['a']); b['clusters'][0]['cluster_name'] = 'Neu'
        result = self.compare({'baseline': samples(a, a), 'other': samples(b, b)}, 'clusterer')
        memberships = [f for f in result['findings'] if f['feature_type'] == 'cluster_membership']
        self.assertEqual(len(memberships), 1)
        self.assertFalse(memberships[0]['observed_patterns_differ'])
        self.assertTrue(all(f['observed_patterns_differ'] for f in result['findings'] if f['feature_type'] == 'exact_projection'))
        result = self.compare({'baseline': samples(swot(), swot()), 'other': samples(swot('Risiken'), swot('Risiken'))}, 'swot')
        self.assertEqual(len([f for f in result['findings'] if f['feature_type'] == 'reference_binding']), 2)

    def test_empty_and_invalid_results_not_maximal_agreement(self):
        result = self.compare({'baseline': samples(clusters(), clusters()), 'other': samples(clusters(), clusters())}, 'clusterer')
        self.assertEqual(result['findings'], [])
        bad = clusters(['foreign'])
        result = self.compare({'baseline': samples(clusters(['a']), clusters(['a'])), 'other': samples(bad, bad)}, 'clusterer')
        self.assertEqual(result['comparison_status'], 'not_computable')
        self.assertEqual(result['findings'][0]['excluded_configurations'], ['other'])

    def test_multi_label_counts_passages_and_verification_remains_alternative(self):
        self.segments = [Segment('a', 'Text', 'A', 'P', unit_id='p'), Segment('b', 'Text', 'B', 'P', unit_id='p')]
        a = multi(self.segments, {'p': (['A', 'B'], 'assigned')})
        result = self.compare({'baseline': samples(a, a), 'other': samples(a, a)}, label_mode='multi_label')
        self.assertEqual(len({f['unit_id'] for f in result['findings']}), 1)
        a = verify(self.segments); a['results'][0]['alternative_codes'] = ['B']
        result = self.compare({'baseline': samples(a, a), 'other': samples(a, a)}, 'code_verification')
        self.assertTrue(all(f['role'] == 'verification_alternative' for f in result['findings']))

    def test_no_flattening_beyond_twenty_and_no_unequal_plan(self):
        a = single(self.segments, ['A'])
        result = self.compare({cid: samples(*([a] * 20)) for cid in ['baseline', 'b', 'c']})
        self.assertEqual(result['findings'][0]['planned_configurations'], 3)
        with self.assertRaises(ValueError):
            self.compare({'baseline': samples(a, a), 'b': samples(a, a, a)})

    def test_distribution_ranges_preserve_persons_levels_and_missingness(self):
        self.segments = [Segment('a', 'Teil eins', 'A > X', 'P', unit_id='passage1'),
                         Segment('b', 'Teil zwei', 'A > Y', 'P', unit_id='passage2'),
                         Segment('c', 'Andere Person', 'B', 'Q', unit_id='passage3')]
        a, b = clusters(['a', 'c']), clusters(['a', 'b', 'c'])
        fail = {'status': 'failed', 'sample_id': 'x'}
        result = self.compare({'baseline': samples(a, b), 'other': samples(a, a), 'failed': [fail, fail]}, 'clusterer')
        row = next(r for r in result['selection_distributions'] if r.get('person') == 'P')
        self.assertEqual(row['per_configuration']['baseline']['selected_range'], [1, 2])
        self.assertEqual(row['per_configuration']['baseline']['share_range'], [.5, 2/3])
        self.assertIsNone(row['per_configuration']['failed']['selected_range'])
        cat = next(r for r in result['selection_distributions'] if r.get('code') == 'A > X')
        self.assertEqual(cat['per_configuration']['baseline']['samples'][0]['share']['denominator'], 1)
        self.assertEqual(cat['per_configuration']['baseline']['samples'][1]['share']['denominator'], 2)


if __name__ == '__main__':
    unittest.main()
