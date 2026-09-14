"""Opt-in modes and honest cost projection, without activating future adapters."""
import copy
import unittest

from analysis_perspectives import (normalize_analysis_perspectives, perspective_capabilities,
                                   perspective_effort, perspective_metadata)


class AnalysisPerspectivesTests(unittest.TestCase):
    def test_legacy_and_null_default_without_migration_or_shared_mutable_results(self):
        for config in ({}, {'analysis_perspectives': None}, {'analysis_perspectives': {}}):
            before = copy.deepcopy(config)
            result = normalize_analysis_perspectives(config)
            self.assertEqual(len(result), 10)
            self.assertEqual(set(result.values()), {'qualitative'})
            self.assertEqual(config, before)
            result['swot'] = 'both'
            self.assertEqual(normalize_analysis_perspectives(config)['swot'], 'qualitative')

    def test_availability_is_explicit_and_no_nondefault_mode_works_by_default(self):
        for mode in ('frequency', 'both'):
            with self.assertRaisesRegex(ValueError, 'noch nicht integriert'):
                normalize_analysis_perspectives({'analysis_perspectives': {'swot': mode}})
            result = normalize_analysis_perspectives({'analysis_perspectives': {'swot': mode}}, implemented_modules=['swot'])
            self.assertEqual(result['swot'], mode)
            self.assertEqual(result['meta_swot'], 'qualitative')
        self.assertEqual(normalize_analysis_perspectives({'analysis_perspectives': {'swot': 'qualitative'}})['swot'], 'qualitative')

    def test_capabilities_explain_all_twenty_modules_and_distinguish_future_eligibility(self):
        rows = perspective_capabilities(implemented_modules=['clusterer'])
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({r['module_id'] for r in rows}), 20)
        self.assertEqual(sum(r['eligible'] for r in rows), 10)
        self.assertTrue(all(r['reason'] for r in rows))
        by_id = {row['module_id']: row for row in rows}
        self.assertEqual(by_id['clusterer']['available_modes'], ['qualitative', 'frequency', 'both'])
        self.assertEqual(by_id['swot']['available_modes'], ['qualitative'])
        self.assertFalse(by_id['swot']['implemented'])
        for mid in ('evidence_audit', 'review_queue', 'coding_agreement', 'stability', 'blind_coding'):
            self.assertFalse(by_id[mid]['eligible'])
            self.assertEqual(by_id[mid]['available_modes'], [])
        rows[0]['available_modes'].clear()
        self.assertEqual(perspective_capabilities(implemented_modules=['clusterer'])[0]['available_modes'], ['qualitative', 'frequency', 'both'])

    def test_bad_sections_modes_module_ids_and_implementation_grants_are_rejected(self):
        for config in (None, [], {'analysis_perspectives': []}, {'analysis_perspectives': 'both'},
                       {'analysis_perspectives': {'swot': None}}, {'analysis_perspectives': {'swot': True}},
                       {'analysis_perspectives': {'swot': ['qualitative', 'frequency']}},
                       {'analysis_perspectives': {'swot': 'BOTH'}}, {'analysis_perspectives': {'unknown': 'both'}},
                       {'analysis_perspectives': {2: 'qualitative'}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                normalize_analysis_perspectives(config, implemented_modules=['swot'])
        for mid in ('evidence_audit', 'coverage', 'coding_agreement', 'review_queue', 'code_verification'):
            with self.assertRaisesRegex(ValueError, 'kein zusätzlicher Perspektivmodus'):
                normalize_analysis_perspectives({'analysis_perspectives': {mid: 'qualitative'}})
        for grant in (None, 'swot', ['swot', 'swot'], ['unknown'], ['evidence_audit'], [None]):
            with self.subTest(grant=grant), self.assertRaises(ValueError):
                perspective_capabilities(implemented_modules=grant)

    def test_metadata_is_order_independent_and_binds_modes_without_free_text(self):
        a = {'analysis_perspectives': {'swot': 'both', 'clusterer': 'frequency'}, 'context': 'PRIVATE_TEXT'}
        b = {'analysis_perspectives': {'clusterer': 'frequency', 'swot': 'both'}}
        enabled = ['clusterer', 'swot']
        self.assertEqual(perspective_metadata(a, implemented_modules=enabled), perspective_metadata(b, implemented_modules=enabled))
        self.assertNotIn('PRIVATE_TEXT', str(perspective_metadata(a, implemented_modules=enabled)))
        self.assertEqual(perspective_metadata({}), perspective_metadata({'analysis_perspectives': {'swot': 'qualitative'}}))
        b['analysis_perspectives']['swot'] = 'frequency'
        self.assertNotEqual(perspective_metadata(a, implemented_modules=enabled)['fingerprint'],
                            perspective_metadata(b, implemented_modules=enabled)['fingerprint'])
        self.assertEqual(a['analysis_perspectives']['swot'], 'both')

    def test_selected_module_projection_ignores_noninterpretive_modules_but_checks_all_settings(self):
        meta = perspective_metadata({}, module_ids=['coding_agreement', 'swot'])
        self.assertEqual(meta['modes'], {'swot': 'qualitative'})
        self.assertEqual(perspective_metadata({}, module_ids=[])['modes'], {})
        for ids in ('swot', ['swot', 'swot'], [None], ['unknown']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                perspective_metadata({}, module_ids=ids)
        # Invalid saved settings do not become harmless merely by disabling a module.
        with self.assertRaisesRegex(ValueError, 'noch nicht integriert'):
            perspective_metadata({'analysis_perspectives': {'swot': 'both'}}, module_ids=['clusterer'])

    def test_both_shares_one_basis_and_unknown_cost_is_not_a_zero_estimate(self):
        for mode in ('frequency', 'both'):
            config = {'analysis_perspectives': {'swot': mode}}
            before = copy.deepcopy(config)
            result = perspective_effort(config, ['swot'], implemented_modules=['swot'])
            self.assertTrue(result['additional_work_required'])
            self.assertEqual(result['shared_assignment_bases'], 1)
            self.assertEqual(result['additional_frequency_interpretation_phases'], 1)
            self.assertIsNone(result['additional_model_calls'])
            self.assertIsNone(result['modules'][0]['additional_assignment_cells'])
            self.assertEqual(len(result['modules'][0]['interpretation_outputs']), 2 if mode == 'both' else 1)
            self.assertEqual(config, before)
        combined = perspective_effort({'analysis_perspectives': {'swot': 'both', 'meta_swot': 'both'}},
            ['swot', 'meta_swot', 'evidence_audit'], implemented_modules=['swot', 'meta_swot'])
        self.assertEqual(combined['shared_assignment_bases'], 2)
        self.assertEqual(len(combined['modules']), 2)

    def test_qualitative_has_no_added_work_without_claiming_zero_total_model_cost(self):
        result = perspective_effort({}, ['swot', 'evidence_audit'])
        self.assertFalse(result['additional_work_required'])
        self.assertEqual(result['additional_model_calls'], 0)
        self.assertEqual(result['shared_assignment_bases'], 0)
        self.assertEqual(result['modules'][0]['interpretation_outputs'], ['qualitative'])
        self.assertNotIn('total_model_calls', result)
        self.assertIn('Gesamtaufwand', ' '.join(result['limits']))


if __name__ == '__main__':
    unittest.main()
