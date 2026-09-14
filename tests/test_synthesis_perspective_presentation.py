"""Synthetic, model-free prompt, effort and bounded progress presentation."""
import copy
import unittest
from unittest.mock import patch

from analysis_perspectives import perspective_effort
from context_preflight import check_context
from prompt_catalog import catalog
from progress_presentation import safe_numeric_progress
from synthesis_countability import SYSTEM, CORRECTION
from telegram_progress import format_progress


def config(mode='both'):
    return {'analysis_perspectives': {'overall_synthesis': mode},
            'llm': {'num_ctx': 32768, 'max_tokens': 1024},
            'context': {'study': 'SYNTHETIC_UNEXPANDED_CONTEXT'},
            'prompts': {'overall_synthesis': {'system': 'Original synthesis', 'user': '{data}'}}}


class SynthesisPerspectivePresentationTests(unittest.TestCase):
    def test_one_selection_phase_shared_by_both_and_no_autoactivation(self):
        for mode in ('frequency', 'both'):
            cfg = config(mode)
            before = copy.deepcopy(cfg)
            effort = perspective_effort(cfg, ['overall_synthesis'], implemented_modules=['overall_synthesis'])
            self.assertEqual(effort['additional_countability_selection_phases'], 1)
            self.assertEqual(effort['modules'][0]['additional_countability_selection_phases'], 1)
            self.assertEqual(effort['shared_assignment_bases'], 1)
            self.assertEqual(effort['additional_frequency_interpretation_phases'], 1)
            self.assertIsNone(effort['additional_model_calls'])
            self.assertEqual(cfg, before)
        for cfg, selected in ((config('qualitative'), ['overall_synthesis']), (config(), ['swot'])):
            effort = perspective_effort(cfg, selected, implemented_modules=['overall_synthesis', 'swot'])
            self.assertEqual(effort['additional_countability_selection_phases'], 0)

    def test_prompt_view_shows_actual_selection_and_repair_without_expanding_inputs(self):
        cfg = config()
        modules = [{'id': 'overall_synthesis', 'name': 'Gesamtsynthese'}]
        result = catalog(cfg, modules)
        templates = {row['key']: row for row in result['modules'][0]['templates']}
        self.assertEqual(templates['overall_synthesis / countability_selection']['system'], SYSTEM)
        self.assertEqual(templates['overall_synthesis / countability_selection_repair']['system'], CORRECTION)
        self.assertIn('overall_synthesis / thematic_assignment', templates)
        self.assertIn('overall_synthesis / frequency_interpretation', templates)
        self.assertNotIn('SYNTHETIC_UNEXPANDED_CONTEXT', str(result))
        self.assertIn('unbestätigt', result['modules'][0]['note'])
        ordinary = catalog(config('qualitative'), modules)
        self.assertEqual([x['key'] for x in ordinary['modules'][0]['templates']], ['overall_synthesis'])

    def test_repetition_catalog_includes_selection_from_target_closure(self):
        cfg = config()
        cfg['diagnostics'] = {'stability': {'modules': ['overall_synthesis']}}
        result = catalog(cfg, [{'id':'overall_synthesis','name':'Synthese'},
                               {'id':'stability','name':'Stabilität','depends_on':[]}])
        keys = [row['key'] for row in result['modules'][1]['templates']]
        self.assertIn('overall_synthesis / countability_selection', keys)

    def test_context_screen_includes_selection_and_repair_fixed_lower_bound(self):
        cfg = config()
        # Make this instruction uniquely limiting: tests plumbing, not the current text length.
        with patch('synthesis_countability.SYSTEM', 'x' * 40000):
            result = check_context(cfg, [], {}, ['overall_synthesis'])
        self.assertEqual(result['blocked'][0]['module'], 'overall_synthesis')
        self.assertGreater(result['blocked'][0]['required_bound'], 40000)
        self.assertTrue(any('Auswahlphase' in value for value in result['warnings']))
        ordinary = check_context(config('qualitative'), [], {}, ['overall_synthesis'])
        self.assertFalse(any('Auswahlphase' in value for value in ordinary['warnings']))

    def test_main_and_nested_progress_keep_fixed_phase_and_counters_only(self):
        raw = {'phase':'countability_selection','unit':'summaries','completed':2,'total':5,
               'text':'SYNTHETIC_MUST_NOT_RENDER','candidate_id':'SYNTHETIC_SECRET_ID'}
        clean = safe_numeric_progress(raw)
        self.assertEqual(clean, {key:raw[key] for key in ('phase','unit','completed','total')})
        main = format_progress(3, 10, {'module':'overall_synthesis', **raw}, now=100)
        nested = format_progress(3, 10, {'module':'stability','phase':'repetitions',
            'completed':0,'total':2,'unit':'repetitions','series_current':{
                'state':'running','module':'overall_synthesis','detail':raw}}, now=100)
        for value in (main, nested):
            self.assertIn('Synthesebefunde auf Zählbarkeit prüfen (Modellvorschlag)', value)
            self.assertNotIn('SYNTHETIC_', value)
        self.assertIn('2 von 5 Synthesebefunde', main)
        self.assertIn('2/5 Synthesebefunde in dieser Phase', nested)
        unknown = format_progress(0, 10, {'module':'overall_synthesis', 'phase':'countability_selection'}, now=100)
        self.assertNotIn(' %', unknown)


if __name__ == '__main__':
    unittest.main()
