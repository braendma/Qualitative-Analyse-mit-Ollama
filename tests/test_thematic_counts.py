"""Synthetic scoped assignments; deterministic tests without file or model I/O."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from thematic_counts import count_topics, union_topics


def material(people, *, kinds=None, confirmed=True):
    return {'schema_version': 1, 'basis_fingerprint': 'synthetic-frozen-basis',
            'person_basis': 'confirmed' if confirmed else 'unconfirmed',
            'persons': sorted(set(people)),
            'units': {'u' + str(i): {'kind': kinds[i] if kinds else 'passage', 'person': person,
                       'text': 'Original synthetic statement', 'segment_ids': ['s' + str(i)],
                       'code_paths': ['A > B']} for i, person in enumerate(people)}}


def topic(tid, scope, *, kind='explicit', definition='A defined synthetic theme'):
    return {'topic_id': tid, 'definition': definition, 'inclusion': '', 'exclusion': '',
            'kind': kind, 'scope_unit_ids': list(scope)}


def assignment(tid, uid, status='supported'):
    return {'topic_id': tid, 'unit_id': uid, 'status': status}


def first(value):
    return value['topics'][0]


class ThematicCountsTests(unittest.TestCase):
    def test_ten_passages_one_person_versus_ten_persons(self):
        for people, expected in ((['P1'] * 10, 1), (['P' + str(i) for i in range(10)], 10)):
            with self.subTest(expected_people=expected):
                basis = material(people)
                result = first(count_topics(basis, [topic('T1', basis['units'])],
                    [assignment('T1', uid) for uid in basis['units']]))
                count = result['counts']['supporting']
                self.assertEqual(count['exact_passage_count'], 10)
                self.assertEqual(count['exact_person_count'], expected)
                self.assertEqual(result['scope']['person_count'], expected)
                self.assertEqual(count['person_share_in_scope'], 1)

    def test_same_person_opposes_and_supports_in_different_passages(self):
        basis = material(['P1', 'P1', 'P2', 'P3'])
        rows = [assignment('T', 'u0', 'supported'), assignment('T', 'u1', 'opposed'),
                assignment('T', 'u2', 'both'), assignment('T', 'u3', 'no_evidence')]
        counts = first(count_topics(basis, [topic('T', basis['units'])], rows))['counts']
        self.assertEqual(counts['supporting']['exact_person_count'], 2)
        self.assertEqual(counts['opposing']['exact_person_count'], 2)
        self.assertEqual(counts['both']['exact_person_count'], 2)
        self.assertEqual(counts['both']['exact_passage_count'], 1)
        self.assertEqual(counts['mentioned']['exact_person_count'], 2)
        self.assertEqual(counts['mentioned']['exact_passage_count'], 3)

    def test_missing_unclear_and_failed_cells_are_not_negative_evidence(self):
        basis = material(['P1', 'P2', 'P3', 'P4'])
        rows = [assignment('T', 'u0'), assignment('T', 'u1', 'unclear'), assignment('T', 'u2', 'failed')]
        result = count_topics(basis, [topic('T', basis['units'])], rows)
        measured = first(result)
        self.assertEqual(result['assignments'][-1], assignment('T', 'u3', 'not_checked'))
        self.assertEqual(measured['coverage']['decided_cells'], 1)
        self.assertEqual(measured['coverage']['status_counts']['not_checked'], 1)
        self.assertEqual(measured['coverage']['status_counts']['no_evidence'], 0)
        self.assertEqual(measured['counts']['mentioned']['observed_person_count'], 1)
        for count in measured['counts'].values():
            self.assertIsNone(count['exact_person_count'])
            self.assertIsNone(count['exact_unit_count'])
            self.assertIsNone(count['person_share_in_scope'])
            self.assertIsNone(count['unit_share_in_scope'])

    def test_fully_decided_no_evidence_is_zero_with_named_nonempty_denominator(self):
        basis = material(['P1', 'P2'])
        result = first(count_topics(basis, [topic('T', basis['units'])],
            [assignment('T', uid, 'no_evidence') for uid in basis['units']]))
        self.assertTrue(result['coverage']['complete'])
        self.assertEqual(result['counts']['mentioned']['exact_person_count'], 0)
        self.assertEqual(result['scope']['person_count'], 2)
        self.assertEqual(result['counts']['mentioned']['person_share_in_scope'], 0)

    def test_scope_excludes_other_export_people_without_hiding_full_export_basis(self):
        basis = material(['P1', 'P2', 'P3'])
        result = first(count_topics(basis, [topic('T', ['u0'])], [assignment('T', 'u0')]))
        self.assertEqual(result['scope']['person_count'], 1)
        self.assertEqual(result['scope']['export_person_count'], 3)
        self.assertEqual(result['counts']['mentioned']['person_share_in_scope'], 1)
        self.assertEqual(result['scope']['unit_count'], 1)
        self.assertEqual(result['scope']['export_unit_count'], 3)

    def test_empty_scope_never_returns_a_percentage(self):
        result = first(count_topics(material(['P1']), [topic('T', [])], []))
        self.assertEqual(result['scope']['unit_basis'], 'empty')
        self.assertEqual(result['scope']['person_count'], 0)
        self.assertEqual(result['counts']['mentioned']['exact_unit_count'], 0)
        self.assertIsNone(result['counts']['mentioned']['unit_share_in_scope'])
        self.assertIsNone(result['counts']['mentioned']['person_share_in_scope'])
        self.assertIsNone(result['counts']['mentioned']['exact_passage_count'])

    def test_unconfirmed_persons_never_produce_person_counts_or_identified_sets(self):
        basis = material(['P1', 'P1'], confirmed=False)
        result = first(count_topics(basis, [topic('T', basis['units'])],
            [assignment('T', uid) for uid in basis['units']]))
        self.assertIsNone(result['scope']['person_ids'])
        self.assertIsNone(result['scope']['person_count'])
        self.assertIsNone(result['scope']['export_person_count'])
        for count in result['counts'].values():
            self.assertIsNone(count['observed_person_count'])
            self.assertIsNone(count['exact_person_count'])
            self.assertIsNone(count['person_ids'])
        self.assertEqual(result['counts']['mentioned']['exact_passage_count'], 2)

    def test_coding_rows_and_mixed_units_do_not_claim_passage_counts(self):
        for kinds in (['coding_row', 'coding_row'], ['passage', 'coding_row']):
            basis = material(['P1', 'P2'], kinds=kinds)
            result = first(count_topics(basis, [topic('T', basis['units'])],
                [assignment('T', uid) for uid in basis['units']]))
            self.assertIn(result['scope']['unit_basis'], ('coding_rows', 'mixed_units'))
            self.assertIsNone(result['scope']['passage_count'])
            self.assertEqual(result['counts']['mentioned']['exact_unit_count'], 2)
            self.assertIsNone(result['counts']['mentioned']['exact_passage_count'])
            self.assertIsNone(result['counts']['mentioned']['observed_passage_count'])

    def test_multiple_coding_rows_within_passage_and_identical_text_do_not_inflate_counts(self):
        basis = material(['P1', 'P2'])
        basis['units']['u0']['segment_ids'].append('s-extra')
        basis['units']['u0']['code_paths'].append('A > C')
        result = first(count_topics(basis, [topic('T', basis['units'])],
            [assignment('T', uid) for uid in basis['units']]))
        self.assertEqual(result['scope']['coding_row_count'], 3)
        self.assertEqual(result['scope']['passage_count'], 2)
        self.assertEqual(result['counts']['mentioned']['exact_person_count'], 2)

    def test_long_unicode_material_stays_untouched_and_is_not_embedded_in_count_results(self):
        basis = material(['P1'])
        text = 'äöü 😀 Mehrzeilig\n' * 100000
        basis['units']['u0']['text'] = text
        before = copy.deepcopy(basis)
        result = count_topics(basis, [topic('T', ['u0'])], [assignment('T', 'u0')])
        self.assertEqual(basis, before)
        self.assertNotIn(text, json.dumps(result, ensure_ascii=False))
        self.assertEqual(first(result)['counts']['mentioned']['exact_person_count'], 1)

    def test_derived_kind_counts_material_support_instead_of_literal_mentions(self):
        basis = material(['P1'])
        result = first(count_topics(basis, [topic('D', ['u0'], kind='derived')], [assignment('D', 'u0')]))
        self.assertEqual(result['count_meaning'], 'material_support_for_inference')
        self.assertEqual(result['counts']['mentioned']['exact_person_count'], 1)

    def test_membership_is_labeled_as_model_group_assignment_not_mention(self):
        basis = material(['P1'])
        result = first(count_topics(basis, [topic('C', ['u0'], kind='membership')], [assignment('C', 'u0')]))
        self.assertEqual(result['count_meaning'], 'model_assigned_group_membership')
        self.assertEqual(result['kind'], 'membership')
        self.assertEqual(result['counts']['supporting']['exact_person_count'], 1)

    def test_results_are_deterministic_and_inputs_not_mutated(self):
        basis = material(['P1', 'P2'])
        topics = [topic('Z', ['u1', 'u0']), topic('A', ['u0'])]
        rows = [assignment('Z', 'u1'), assignment('A', 'u0'), assignment('Z', 'u0', 'opposed')]
        before = copy.deepcopy((basis, topics, rows))
        result = count_topics(basis, topics, rows)
        self.assertEqual(result, count_topics(basis, list(reversed(topics)), list(reversed(rows))))
        self.assertEqual((basis, topics, rows), before)
        result['definitions'][0]['scope_unit_ids'].append('changed')
        self.assertEqual((basis, topics, rows), before)

    def test_unknown_out_of_scope_duplicate_or_invalid_assignments_fail(self):
        basis = material(['P1', 'P2'])
        topics = [topic('T', ['u0'])]
        for rows in ([assignment('Other', 'u0')], [assignment('T', 'u1')],
                     [assignment('T', 'unknown')], [assignment('T', 'u0', 'invented')],
                     [assignment('T', 'u0'), assignment('T', 'u0')],
                     [{**assignment('T', 'u0'), 'estimated_person_count': 100}],
                     [{'topic_id': [], 'unit_id': 'u0', 'status': 'supported'}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                count_topics(basis, topics, rows)

    def test_invalid_topic_identity_definition_scope_and_fields_fail(self):
        basis = material(['P1'])
        good = topic('T', ['u0'])
        for topics in ([good, good], [{**good, 'topic_id': ''}], [{**good, 'definition': ''}],
                       [{**good, 'inclusion': None}], [{**good, 'kind': 'unknown'}],
                       [{**good, 'scope_unit_ids': ['unknown']}], [{**good, 'scope_unit_ids': ['u0', 'u0']}],
                       [{**good, 'guessed_weight': 1.5}]):
            with self.subTest(topics=topics), self.assertRaises(ValueError):
                count_topics(basis, topics, [])

    def test_invalid_material_partition_or_person_directory_fail(self):
        good = material(['P1', 'P2'])
        for change in ('duplicate_row', 'wrong_persons', 'wrong_basis', 'coding_row_multiple_ids'):
            basis = copy.deepcopy(good)
            if change == 'duplicate_row':
                basis['units']['u1']['segment_ids'] = ['s0']
            elif change == 'wrong_persons':
                basis['persons'] = ['P1']
            elif change == 'wrong_basis':
                basis['person_basis'] = 'inferred'
            else:
                basis['units']['u0']['kind'] = 'coding_row'
                basis['units']['u0']['segment_ids'].append('extra')
            with self.subTest(change=change), self.assertRaises(ValueError):
                count_topics(basis, [], [])

    def union_source(self, *, incomplete=False):
        basis = material(['P1', 'P2', 'P1'])
        topics = [topic('A', ['u0', 'u1']), topic('B', ['u1', 'u2'])]
        rows = [assignment('A', 'u0'), assignment('A', 'u1'), assignment('B', 'u2')]
        if not incomplete:
            rows.append(assignment('B', 'u1', 'opposed'))
        return basis, count_topics(basis, topics, rows)

    def union(self, basis, source, **kwargs):
        return union_topics(basis, source, topic_id='U', member_topic_ids=['A', 'B'],
                            definition='Explicit union of A or B in their named scopes', exact_union=True, **kwargs)

    def test_exact_union_uses_sets_across_overlapping_scopes_not_summed_counts(self):
        basis, source = self.union_source()
        result = self.union(basis, source)
        self.assertEqual(result['scope']['unit_count'], 3)
        self.assertEqual(result['coverage']['expected_cells'], 4)
        self.assertEqual(result['counts']['mentioned']['exact_passage_count'], 3)
        self.assertEqual(result['counts']['mentioned']['exact_person_count'], 2)
        self.assertEqual(result['counts']['both']['exact_person_count'], 1)
        self.assertEqual(result['counts']['both']['exact_passage_count'], 1)
        self.assertEqual(result['union_semantics'], 'explicit_or_of_scoped_topics')
        self.assertEqual(result['position_semantics'], 'position_towards_at_least_one_member_topic')

    def test_incomplete_union_preserves_unknown_cells_even_when_all_units_have_some_support(self):
        basis, source = self.union_source(incomplete=True)
        result = self.union(basis, source)
        self.assertEqual(result['counts']['mentioned']['observed_unit_count'], 3)
        self.assertIsNone(result['counts']['mentioned']['exact_unit_count'])
        self.assertIsNone(result['counts']['mentioned']['exact_person_count'])
        self.assertEqual(result['coverage']['status_counts']['not_checked'], 1)
        self.assertEqual(result['coverage']['expected_cells'], 4)

    def test_union_requires_explicit_declaration_and_same_verified_count_basis(self):
        basis, source = self.union_source()
        for consent in (False, None, 'yes', 1):
            with self.subTest(consent=consent), self.assertRaises(ValueError):
                union_topics(basis, source, topic_id='U', member_topic_ids=['A', 'B'], definition='Union', exact_union=consent)
        wrong = copy.deepcopy(source)
        wrong['basis_fingerprint'] = 'other'
        with self.assertRaises(ValueError):
            self.union(basis, wrong)
        wrong = copy.deepcopy(source)
        wrong['topics'][0]['counts']['mentioned']['exact_person_count'] = 900
        with self.assertRaises(ValueError):
            self.union(basis, wrong)

    def test_union_rejects_changed_material_even_if_caller_forgot_to_refresh_basis_id(self):
        basis, source = self.union_source()
        basis['units']['u0']['text'] = 'A materially changed synthetic statement'
        with self.assertRaisesRegex(ValueError, 'Quellzählung verändert'):
            self.union(basis, source)

    def test_union_rejects_mixed_claim_kinds_unknown_members_and_reused_ids(self):
        basis = material(['P1'])
        source = count_topics(basis, [topic('A', ['u0']), topic('B', ['u0'], kind='derived')],
                              [assignment('A', 'u0'), assignment('B', 'u0')])
        with self.assertRaises(ValueError):
            self.union(basis, source)
        basis, source = self.union_source()
        for tid, members in (('U', ['unknown']), ('A', ['A', 'B']), ('U', ['A', 'A'])):
            with self.subTest(tid=tid, members=members), self.assertRaises(ValueError):
                union_topics(basis, source, topic_id=tid, member_topic_ids=members, definition='Union', exact_union=True)

    def test_union_accepts_separate_same_basis_results_but_not_ambiguous_ids(self):
        basis = material(['P1', 'P2'])
        first_result = count_topics(basis, [topic('A', ['u0'])], [assignment('A', 'u0')])
        second = count_topics(basis, [topic('B', ['u1'])], [assignment('B', 'u1')])
        result = self.union(basis, [first_result, second])
        self.assertEqual(result['counts']['mentioned']['exact_person_count'], 2)
        with self.assertRaises(ValueError):
            self.union(basis, [first_result, first_result, second])


if __name__ == '__main__':
    unittest.main()
