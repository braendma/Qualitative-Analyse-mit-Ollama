"""Synthetic exact-row co-occurrence checks; no model, file or subprocess I/O."""
import copy
import unittest

from coding_validation_common import Segment
from thematic_material import build_material
from thematic_counts import count_topics
from relation_cooccurrence import count_code_path_cooccurrences, code_path_cooccurrences_markdown


def fixture():
    rows = [Segment('doc01_part1_a', 'Synthetische gemeinsame Passage.', 'A > a', 'P01', 'p01'),
            Segment('doc01_part1_b', 'Synthetische gemeinsame Passage.', 'B', 'P01', 'p01'),
            Segment('doc01_part1_a2', 'Synthetische gemeinsame Passage.', 'A > a', 'P01', 'p01'),
            Segment('doc02_part1', 'Identischer künstlicher Text.', 'A > a', 'P02', 'p02a'),
            Segment('doc02_part2', 'Identischer künstlicher Text.', 'B', 'P02', 'p02b')]
    rows.extend(Segment('doc' + str(i), 'Künstlicher Fall ' + str(i), 'C', 'P' + str(i).zfill(2), 'p' + str(i))
                for i in range(3, 13))
    return build_material(rows, person_basis='confirmed')


def pair(result, a='A > a', b='B'):
    return next(row for row in result['pairs'] if (row['code_a'], row['code_b']) == (a, b))


class RelationCooccurrenceTests(unittest.TestCase):
    def test_twelve_people_more_documents_and_deduplicated_passages(self):
        material = fixture(); result = count_code_path_cooccurrences(material); row = pair(result)
        self.assertEqual(result['scope']['person_count'], 12)
        self.assertEqual(row['persons']['a']['count'], 2)
        self.assertEqual(row['persons']['b']['count'], 2)
        self.assertEqual(row['persons']['intersection']['person_ids'], ['P01', 'P02'])
        self.assertEqual(row['persons']['intersection']['share_in_export'], 2 / 12)
        self.assertEqual(row['passages']['intersection']['exact_passage_count'], 1)
        self.assertEqual(row['passages']['a']['exact_passage_count'], 2)
        self.assertEqual(row['passages']['b']['exact_passage_count'], 2)
        self.assertEqual(result['code_paths'][0]['coding_row_count'], 3)
        self.assertEqual(result['code_paths'][0]['material_unit_count'], 2)
        self.assertEqual(result['model_calls'], 0)

    def test_zero_intersection_pairs_are_included(self):
        result = count_code_path_cooccurrences(fixture())
        self.assertEqual(len(result['pairs']), 3)
        row = pair(result, 'A > a', 'C')
        self.assertEqual(row['persons']['intersection']['count'], 0)
        self.assertEqual(row['passages']['intersection']['exact_passage_count'], 0)
        self.assertEqual(row['persons']['intersection']['share_in_export'], 0)

    def test_same_person_two_different_passages_not_same_passage(self):
        rows = [Segment('s1', 'Gleicher Text', 'A', 'P1', 'p1'), Segment('s2', 'Gleicher Text', 'B', 'P1', 'p2')]
        row = pair(count_code_path_cooccurrences(build_material(rows, person_basis='confirmed')), 'A', 'B')
        self.assertEqual(row['persons']['intersection']['count'], 1)
        self.assertEqual(row['passages']['intersection']['exact_passage_count'], 0)

    def test_mixed_passage_ids_keep_known_intersections_not_false_exact_zero(self):
        material = fixture()
        unit = material['units'].pop('passage:p3'); unit['kind'] = 'coding_row'
        material['units']['coding_row:doc3'] = unit
        material['segment_index']['doc3']['unit_id'] = 'coding_row:doc3'
        result = count_code_path_cooccurrences(material)
        self.assertIsNone(result['scope']['exact_passage_count'])
        self.assertFalse(result['scope']['passage_basis_complete'])
        row = pair(result)
        self.assertEqual(row['passages']['intersection']['observed_known_passage_count'], 1)
        self.assertIsNone(row['passages']['intersection']['exact_passage_count'])
        self.assertIsNone(row['passages']['intersection']['share_in_export'])
        self.assertIsNone(pair(result, 'A > a', 'C')['passages']['intersection']['exact_passage_count'])

    def test_all_missing_passage_ids_do_not_merge_equal_text(self):
        rows = [Segment('s1', 'Gleicher Text', 'A', 'P1'), Segment('s2', 'Gleicher Text', 'B', 'P1')]
        result = count_code_path_cooccurrences(build_material(rows, person_basis='confirmed'))
        row = pair(result, 'A', 'B')
        self.assertEqual(row['persons']['intersection']['count'], 1)
        self.assertEqual(row['passages']['intersection']['observed_known_passage_count'], 0)
        self.assertIsNone(row['passages']['intersection']['exact_passage_count'])
        self.assertEqual(result['scope']['material_unit_count'], 2)

    def test_empty_and_one_code_material(self):
        for rows, people in (([], 0), ([Segment('s', 'Künstlicher Text', 'A', 'P1', 'p')], 1)):
            result = count_code_path_cooccurrences(build_material(rows, person_basis='confirmed'))
            self.assertEqual(result['pairs'], [])
            self.assertEqual(result['scope']['person_count'], people)
            self.assertIn('keine Codepaare', code_path_cooccurrences_markdown(result))

    def test_exact_paths_no_ancestor_or_prefix_expansion(self):
        rows = [Segment('a', 'Text a', 'A', 'P1', 'pa'), Segment('b', 'Text b', 'A > B', 'P2', 'pb')]
        result = count_code_path_cooccurrences(build_material(rows, person_basis='confirmed'))
        self.assertEqual(pair(result, 'A', 'A > B')['persons']['intersection']['count'], 0)
        self.assertEqual(len(result['code_paths']), 2)

    def test_unconfirmed_people_fail(self):
        material = fixture(); material['person_basis'] = 'unconfirmed'
        with self.assertRaisesRegex(ValueError, 'bestätigte'):
            count_code_path_cooccurrences(material)

    def test_index_must_match_every_exact_original_row(self):
        def missing(m): m['segment_index'].pop('doc01_part1_a')
        def extra(m): m['segment_index']['ghost'] = {'unit_id': 'passage:p01', 'code_path': 'B'}
        def wrong_unit(m): m['segment_index']['doc01_part1_a']['unit_id'] = 'passage:p02a'
        def wrong_code(m): m['segment_index']['doc01_part1_b']['code_path'] = 'unknown'
        def no_code(m): m['segment_index']['doc01_part1_a'].pop('code_path')
        def invented_path(m): m['units']['passage:p01']['code_paths'].append('Invented')
        for change in (missing, extra, wrong_unit, wrong_code, no_code, invented_path):
            with self.subTest(change=change.__name__):
                material = fixture(); change(material)
                with self.assertRaises(ValueError): count_code_path_cooccurrences(material)

    def test_stable_keys_order_fingerprints_and_no_mutation(self):
        material = fixture(); before = copy.deepcopy(material)
        first = count_code_path_cooccurrences(material)
        self.assertEqual(material, before)
        reordered = copy.deepcopy(material)
        reordered['units'] = dict(reversed(list(reordered['units'].items())))
        reordered['segment_index'] = dict(reversed(list(reordered['segment_index'].items())))
        self.assertEqual(first, count_code_path_cooccurrences(reordered))
        self.assertEqual(first['material_content_fingerprint'], count_topics(material, [], [])['material_content_fingerprint'])
        changed = copy.deepcopy(material)
        changed['segment_index']['doc01_part1_a']['code_path'] = 'B'
        # Another A-row preserves the same unit code set; the exact row index still changes the basis.
        second = count_code_path_cooccurrences(changed)
        self.assertNotEqual(first['cooccurrence_basis_fingerprint'], second['cooccurrence_basis_fingerprint'])
        self.assertEqual([r['pair_key'] for r in first['pairs']], [r['pair_key'] for r in second['pairs']])
        self.assertNotEqual(first['result_fingerprint'], second['result_fingerprint'])

    def test_markdown_escapes_code_labels_and_does_not_include_original_text(self):
        rows = [Segment('s1', 'PRIVATE_SYNTHETIC_TEXT', '<img src=x>|[Link](https://example.test)', 'P1', 'p'),
                Segment('s2', 'PRIVATE_SYNTHETIC_TEXT', 'B', 'P1', 'p')]
        result = count_code_path_cooccurrences(build_material(rows, person_basis='confirmed'))
        text = code_path_cooccurrences_markdown(result)
        self.assertNotIn('<img', text)
        self.assertNotIn('[Link](', text)
        self.assertNotIn('PRIVATE_SYNTHETIC_TEXT', str(result))
        self.assertIn('&lt;img', text)
        self.assertIn('\\|', text)
        result['pairs'][0]['persons']['intersection']['count'] = 42
        with self.assertRaises(ValueError): code_path_cooccurrences_markdown(result)


if __name__ == '__main__':
    unittest.main()
