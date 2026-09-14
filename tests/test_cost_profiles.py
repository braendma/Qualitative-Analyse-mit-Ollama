import copy
import importlib
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
runner = importlib.import_module('00_WORKFLOW_RUNNER')


class CostProfileTests(unittest.TestCase):
    def test_old_configs_get_same_profiles_without_changing_source_or_execution(self):
        config = yaml.safe_load((ROOT / 'config/config_v2.yaml').read_text(encoding='utf-8'))
        old = copy.deepcopy(config)
        for module in old['pipeline']['modules']:
            del module['cost_profile']
        untouched = copy.deepcopy(old)
        actual = runner.normalize_modules(old)
        current = runner.normalize_modules(config)
        self.assertEqual(actual, current)
        self.assertEqual(old, untouched)
        self.assertTrue(all(m['cost_profile'] for m in actual))
        self.assertEqual([m['id'] for m in runner.topological_order(actual)],
                         [m['id'] for m in runner.topological_order(current)])
        self.assertTrue(all(not m['enabled'] for m in actual[-5:]))

    def test_custom_script_cannot_inherit_unrelated_builtin_estimate(self):
        for module in ({'id': 'custom', 'script': 'custom.py'},
                       {'id': 'coverage', 'script': 'custom.py'}):
            result = runner.normalize_modules({'pipeline': {'modules': [module]}})
            self.assertIsNone(result[0]['cost_profile'])

    def test_explicit_custom_profile_is_supported_and_copied(self):
        profile = {'class': 'HOCH', 'recommendation': ' eigene Prüfung ', 'note': ' großer Datenbestand '}
        module = {'id': 'custom', 'script': 'custom.py', 'cost_profile': profile}
        result = runner.normalize_modules({'pipeline': {'modules': [module]}})[0]
        self.assertEqual(result['cost_profile']['recommendation'], 'eigene Prüfung')
        result['cost_profile']['note'] = 'changed'
        self.assertEqual(profile['note'], ' großer Datenbestand ')

    def test_malformed_profiles_give_actionable_module_specific_errors(self):
        for value in ('HOCH', [], {}, {'class': 'SCHNELL', 'recommendation': 'test'},
                      {'class': 'HOCH', 'recommendation': ''},
                      {'class': 'HOCH', 'recommendation': 12},
                      {'class': 'HOCH', 'recommendation': 'test', 'note': []}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Modul custom: cost_profile'):
                runner.normalize_modules({'pipeline': {'modules': [
                    {'id': 'custom', 'script': 'custom.py', 'cost_profile': value}]}})

    def test_null_profile_falls_back_without_sharing_mutable_defaults(self):
        config = {'pipeline': {'modules': [{'id': 'coverage', 'script': 'coverage_analysis.py', 'cost_profile': None}]}}
        first = runner.normalize_modules(config)[0]
        first['cost_profile']['class'] = 'HOCH'
        self.assertEqual(runner.normalize_modules(config)[0]['cost_profile']['class'], 'NIEDRIG')


if __name__ == '__main__':
    unittest.main()
