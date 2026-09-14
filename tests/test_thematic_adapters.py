"""Synthetic adapters preserve sources and never promote chosen quotes to counts."""
import copy
import unittest
from unittest.mock import patch

from thematic_adapters import build_cluster_topics, build_summary_topics, build_swot_topics, DIMENSIONS
from thematic_counts import count_topics
from test_thematic_memberships import fixture


def summary(clusters):
    return {'cluster_summaries': [{**copy.deepcopy(row), 'summary': 'Ungewichtete Aussage über ' + row['definition']}
                                 for row in clusters['clusters']],
            'final_summary': 'Eine freie, ungewichtete Gesamtzusammenfassung.'}


def swot(material, clusters):
    groups = {}
    for code in sorted({row['code_path'] for row in material['segment_index'].values()}):
        sids = sorted(sid for sid, row in material['segment_index'].items() if row['code_path'] == code)
        groups[code] = {'code_path': code, 'segment_count': len(sids), **{d: [] for d in DIMENSIONS}}
        groups[code]['Chancen'] = [{'thema': 'Gleicher Titel', 'analyse': 'Eine analytisch abgeleitete Möglichkeit.',
            'segment_ids': sids[:1], 'zitate': [{'segment_id': sid,
            'text': material['units'][material['segment_index'][sid]['unit_id']]['text']} for sid in sids[:1]]}]
    return {'swot': groups, 'swot_unit_count': len(groups), 'segment_metadata': copy.deepcopy(clusters['segment_metadata'])}


class ThematicAdapterTests(unittest.TestCase):
    def test_swot_uses_whole_code_scope_not_selected_quotes_and_never_returns_assignments(self):
        material, clusters = fixture(); payload = swot(material, clusters)
        before = copy.deepcopy((material, payload))
        result = build_swot_topics(material, payload)
        self.assertIsNone(result['assignments'])
        self.assertEqual(result['assignment_origin'], 'requires_full_thematic_assignment')
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(len(result['topics']), 2)
        for topic in result['topics']:
            link = result['source_links'][topic['topic_id']]
            self.assertEqual(topic['kind'], 'derived')
            self.assertEqual(len(topic['scope_unit_ids']), 2)
            self.assertEqual(len(link['selected_evidence_segment_ids']), 1)
            self.assertTrue(topic['definition'] and topic['inclusion'] and topic['exclusion'])
            self.assertNotIn('assignments', link)
        counts = count_topics(material, result['topics'], [])
        self.assertTrue(all(t['coverage']['status_counts']['not_checked'] == 2 for t in counts['topics']))
        self.assertTrue(all(t['counts']['mentioned']['exact_person_count'] is None for t in counts['topics']))
        self.assertEqual((material, payload), before)
        result['qualitative_source']['swot'].clear()
        self.assertEqual((material, payload), before)

    def test_swot_identity_binds_code_dimension_and_definition_but_not_evidence_sampling_order(self):
        material, clusters = fixture(); payload = swot(material, clusters)
        original = build_swot_topics(material, payload)
        self.assertEqual(len({t['topic_id'] for t in original['topics']}), 2)
        changed = copy.deepcopy(payload)
        row = changed['swot']['A']['Chancen'][0]
        row['segment_ids'] = ['s3']; row['zitate'] = [{'segment_id': 's3', 'text': 'y'}]
        sampled = build_swot_topics(material, changed)
        self.assertEqual(original['topics'], sampled['topics'])
        self.assertNotEqual(original['source_fingerprint'], sampled['source_fingerprint'])
        changed['swot']['A']['Risiken'] = changed['swot']['A'].pop('Chancen')
        changed['swot']['A']['Chancen'] = []
        self.assertNotEqual(original['topics'], build_swot_topics(material, changed)['topics'])
        reordered = copy.deepcopy(payload); reordered['swot'] = dict(reversed(list(reordered['swot'].items())))
        self.assertEqual(original['topics'], build_swot_topics(material, reordered)['topics'])

    def test_all_swot_dimensions_are_conservatively_derived_not_literal_mentions(self):
        material, clusters = fixture(); payload = swot(material, clusters)
        for dimension in DIMENSIONS:
            payload['swot']['A'][dimension] = [copy.deepcopy(payload['swot']['B']['Chancen'][0])]
            payload['swot']['A'][dimension][0].update(segment_ids=['s1'], zitate=[{'segment_id': 's1', 'text': 'x'}], kind='explicit')
        result = build_swot_topics(material, payload)
        self.assertEqual({t['kind'] for t in result['topics']}, {'derived'})
        self.assertEqual(len(result['topics']), 5)

    def test_swot_rejects_partial_foreign_or_crosscode_sources_and_corrupt_quotes(self):
        material, clusters = fixture(); payload = swot(material, clusters)
        for change in ('partial', 'missing_code', 'code_path', 'dimension', 'segment_count', 'unit_count',
                       'foreign', 'crosscode', 'duplicate_sid', 'quote', 'person', 'passage', 'duplicate_topic'):
            broken = copy.deepcopy(payload)
            row = broken['swot']['A']['Chancen'][0]
            if change == 'partial': broken['processing_status'] = 'failed'
            if change == 'missing_code': broken['swot'].pop('B')
            if change == 'code_path': broken['swot']['A']['code_path'] = 'B'
            if change == 'dimension': broken['swot']['A'].pop('Schwächen')
            if change == 'segment_count': broken['swot']['A']['segment_count'] = 1
            if change == 'unit_count': broken['swot_unit_count'] = True
            if change == 'foreign': row['segment_ids'] = ['unknown']
            if change == 'crosscode': row['segment_ids'] = ['s2']
            if change == 'duplicate_sid': row['segment_ids'] = ['s1', 's1']
            if change == 'quote': row['zitate'][0]['text'] = 'Fremder Text'
            if change == 'person': broken['segment_metadata']['s1']['person'] = 'Other'
            if change == 'passage': broken['segment_metadata']['s1']['unit_id'] = 'other'
            if change == 'duplicate_topic': broken['swot']['A']['Chancen'].append(copy.deepcopy(row))
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_swot_topics(material, broken)

    def test_swot_long_definition_is_preserved_and_does_not_allocate_empty_matrix(self):
        material, clusters = fixture(); payload = swot(material, clusters)
        long_text = 'Lange analytische Aussage mit Unicode äöü 😀\n' * 10000
        payload['swot']['A']['Chancen'][0]['analyse'] = long_text
        with patch('thematic_counts._assignments', side_effect=AssertionError('No matrix allocation in topic adapter')):
            result = build_swot_topics(material, payload)
        self.assertTrue(any(t['definition'].endswith(long_text) for t in result['topics']))
        self.assertEqual(payload['swot']['A']['Chancen'][0]['analyse'], long_text)

    def test_empty_swot_dimensions_are_no_topics_not_an_invented_universal_negative(self):
        material, clusters = fixture(); payload = swot(material, clusters)
        for group in payload['swot'].values():
            for dimension in DIMENSIONS: group[dimension] = []
        result = build_swot_topics(material, payload)
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['source_links'], {})
        self.assertIsNone(result['assignments'])

    def test_cluster_reuses_membership_with_unweighted_source_and_safe_links(self):
        material, clusters = fixture(); before = copy.deepcopy(clusters)
        result = build_cluster_topics(material, clusters)
        self.assertEqual(result['assignment_origin'], 'complete_cluster_membership')
        self.assertEqual(len(result['source_links']), 3)
        self.assertEqual({t['kind'] for t in result['topics']}, {'membership'})
        counts = count_topics(material, result['topics'], result['assignments'])
        self.assertTrue(all(t['coverage']['complete'] for t in counts['topics']))
        self.assertEqual(clusters, before)
        result['qualitative_source']['clusters'][0]['definition'] = 'Changed'
        self.assertEqual(clusters, before)

    def test_summary_reuses_exact_clusters_without_claiming_final_summary_membership(self):
        material, clusters = fixture(); payload = summary(clusters)
        before = copy.deepcopy((clusters, payload)); result = build_summary_topics(material, clusters, payload)
        self.assertEqual(result['assignments'], build_cluster_topics(material, clusters)['assignments'])
        self.assertEqual(result['topics'], build_cluster_topics(material, clusters)['topics'])
        self.assertEqual(len(result['source_links']), 3)
        self.assertEqual(result['unassigned_context']['final_summary'], payload['final_summary'])
        self.assertTrue(all(row['qualitative_text'].startswith('Ungewichtete') for row in result['source_links'].values()))
        self.assertEqual((clusters, payload), before)
        reordered = copy.deepcopy(payload); reordered['cluster_summaries'].reverse()
        self.assertEqual(result['source_links'], build_summary_topics(material, clusters, reordered)['source_links'])
        result['qualitative_source']['cluster_summaries'].clear()
        self.assertEqual((clusters, payload), before)

    def test_summary_title_alone_never_matches_or_infers_complete_membership(self):
        material, clusters = fixture(); payload = summary(clusters)
        for change in ('missing', 'duplicate', 'wrong_path', 'wrong_definition', 'wrong_members', 'missing_members',
                       'empty_summary', 'empty_final', 'failed'):
            broken = copy.deepcopy(payload)
            if change == 'missing': broken['cluster_summaries'].pop()
            if change == 'duplicate': broken['cluster_summaries'].append(copy.deepcopy(broken['cluster_summaries'][0]))
            if change == 'wrong_path': broken['cluster_summaries'][0]['code_path'] = 'B'
            if change == 'wrong_definition': broken['cluster_summaries'][0]['definition'] = 'Andere Bedeutung'
            if change == 'wrong_members': broken['cluster_summaries'][0]['segments'] = ['s1', 's3']
            if change == 'missing_members': broken['cluster_summaries'][0].pop('segments')
            if change == 'empty_summary': broken['cluster_summaries'][0]['summary'] = ''
            if change == 'empty_final': broken['final_summary'] = ''
            if change == 'failed': broken['processing_status'] = 'incomplete'
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_summary_topics(material, clusters, broken)

    def test_partial_cluster_source_is_rejected_even_with_plausible_complete_summaries(self):
        material, clusters = fixture(); payload = summary(clusters)
        clusters['clusters'].pop()
        with self.assertRaises(ValueError): build_summary_topics(material, clusters, payload)


if __name__ == '__main__':
    unittest.main()
