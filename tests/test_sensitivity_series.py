import json
import os
import unittest
from unittest.mock import patch

import test_sensitivity_dispatch as dispatch
import diagnostic_series as series
from diagnostic_sensitivity import prepare_sensitivity
from stability_series import load_sensitivity_series, load_stability_series
from sensitivity_report import render_sensitivity


class SensitivitySeriesTests(unittest.TestCase):
    setUp = dispatch.SensitivityDispatchTests.setUp

    def test_verified_readonly_comparison_and_tampering(self):
        original = series._execute
        def varied_answer(command, directory, log, env):
            if 'warm-repeat-002' in str(log):
                env = {**env, 'MOCK_BLIND_CODE': 'A > B > C > positiv'}
            return original(command, directory, log, env)
        with patch.object(series, '_execute', side_effect=varied_answer):
            self.assertEqual(series.execute_repetitions(self.plan, self.root)['status'], 'success')
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(series, '_execute', side_effect=AssertionError('Do not dispatch')):
            result = load_sensitivity_series(self.root)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(result['processing_status'], 'completed')
        self.assertTrue(result['comparisons']['blind_coding']['within_configurations']['warm']['runtime_comparison']['parameter_profiles_same'])
        profiles = [c['runtime']['profiles'] for c in result['conditions']]
        self.assertNotEqual(profiles[0], profiles[2])
        comparison = result['comparisons']['blind_coding']
        self.assertEqual(comparison['within_configurations']['baseline']['pairs'][0]['code_set_agreement']['value'], 1)
        self.assertEqual(comparison['within_configurations']['warm']['pairs'][0]['code_set_agreement']['value'], .5)
        negative = next(f for f in comparison['findings'] if f['feature_type'] == 'code_presence' and
                        f['value'].endswith('negativ'))
        self.assertEqual(negative['all_observed_repeats']['value'], .5)
        rendered = render_sensitivity(result)
        self.assertIn('Schwankungen innerhalb jeder Einstellung', rendered)
        self.assertIn('0.05 → 0.2', rendered)
        self.assertIn('2/2 (100.0%)', rendered)
        for name in ('configuration-warm.yaml', 'baseline-repeat-001.supervision.json', 'repetition_plan.json'):
            path = self.root / name; saved = path.read_bytes()
            try:
                path.write_text('{}', encoding='utf-8')
                with self.assertRaises((ValueError, KeyError)):
                    load_sensitivity_series(self.root)
            finally:
                path.write_bytes(saved)
        with self.assertRaises(ValueError):
            load_stability_series(self.root)

    def test_failed_variant_excluded_and_resume(self):
        original = series._execute
        def fail_variant(command, directory, log, env):
            if 'configuration-warm.yaml' in command[command.index('--config') + 1]:
                env = {**env, 'MOCK_FAIL_MODULE': 'blind_coding', 'MOCK_FAIL_AFTER': '1'}
            return original(command, directory, log, env)
        with patch.object(series, '_execute', side_effect=fail_variant):
            self.assertEqual(series.execute_repetitions(self.plan, self.root)['status'], 'failed')
        result = load_sensitivity_series(self.root)
        self.assertEqual(result['processing_status'], 'incomplete')
        row = result['comparisons']['blind_coding']['findings'][0]
        self.assertEqual(row['excluded_configurations'], ['warm'])
        self.assertEqual(row['any_observed_repeat']['denominator'], 1)
        self.assertIn('kein Vergleich zwischen Einstellungen möglich', render_sensitivity(result))
        self.assertEqual(series.execute_repetitions(self.plan, self.root, resume=True)['status'], 'success')
        self.assertEqual(load_sensitivity_series(self.root)['processing_status'], 'completed')

    def test_intentional_model_change_verified_per_model(self):
        self.plan = prepare_sensitivity(self.w.path, ['blind_coding'], [{'id': 'other', 'llm': {'model': 'other-model'}}])
        original = series._execute
        def other_model(command, directory, log, env):
            if 'configuration-other.yaml' in command[command.index('--config') + 1]:
                env = {**env, 'MOCK_MODEL_DIGEST': 'b'*64, 'MOCK_MODEL_NAME': 'other-model:latest'}
            return original(command, directory, log, env)
        with patch.object(series, '_execute', side_effect=other_model):
            self.assertEqual(series.execute_repetitions(self.plan, self.root)['status'], 'success')
        result = load_sensitivity_series(self.root)
        self.assertEqual(result['model_identity_status'], 'local_digest_observed_per_model')
        self.assertEqual(len(result['model_digests']), 2)
        self.assertEqual(result['local_digests'], ['a'*64, 'b'*64])


if __name__ == '__main__':
    unittest.main()
