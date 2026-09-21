"""Child failures remain actionable without exposing persisted diagnostic text."""
import copy
import json
import unittest

from failure_help import (child_failure_guidance, failure_help, fixed_failure_help,
                          repetition_failure_marker)
from stability_report import render_stability
from sensitivity_report import render_sensitivity


class RepetitionFailureHelpTests(unittest.TestCase):
    def test_project_only_failed_planned_modules_and_fixed_help(self):
        manifest = {'error': 'PRIVATE_LOG',
            'module_status': {'blind_coding': 'failed', 'swot': 'success', 'alien': 'failed'},
            'module_errors': {'blind_coding': {'kind': 'context', 'cause': 'PRIVATE_TEXT',
                'action': 'PRIVATE_KEY', 'module_name': 'PRIVATE_PERSON'},
                'swot': {'kind': 'memory'}, 'alien': {'kind': 'quota'}}}
        before = copy.deepcopy(manifest)
        rows = child_failure_guidance(manifest, {'blind_coding': {}, 'swot': {}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['module'], 'blind_coding')
        self.assertEqual(rows[0]['kind'], 'context')
        self.assertIn('Kontextfenster', rows[0]['cause'])
        self.assertNotIn('PRIVATE', json.dumps(rows))
        self.assertEqual(manifest, before)

    def test_unknown_and_legacy_error_metadata_falls_back_without_guessing(self):
        for error in (None, [], {'kind': ['memory']}, {'kind': 'PRIVATE_KIND'},
                      {'cause': 'ContextBudgetError PRIVATE'}):
            with self.subTest(error=error):
                rows = child_failure_guidance({'module_status': {'blind_coding': 'failed'},
                    'module_errors': {'blind_coding': error}}, ['blind_coding'])
                self.assertEqual(rows[0]['kind'], 'unknown')
                self.assertNotIn('PRIVATE', json.dumps(rows))
        self.assertEqual(child_failure_guidance({'module_status': None}, ['blind_coding']), [])
        custom = child_failure_guidance({'module_status': {'PRIVATE_SCRIPT': 'failed'}}, ['PRIVATE_SCRIPT'])
        self.assertEqual(custom[0]['module'], 'custom_module')
        self.assertNotIn('PRIVATE', json.dumps(custom))

    def test_parent_classifier_preserves_concrete_child_cause(self):
        for kind in ('context', 'memory', 'quota', 'credentials', 'connection', 'timeout', 'response',
                     'call_budget', 'reduction', 'unknown'):
            with self.subTest(kind=kind):
                result = {'conditions': [{'status': 'failed', 'failure_guidance': [{'kind': kind}]}]}
                marker = repetition_failure_marker(result)
                help_ = failure_help(marker + 'Sensitivitätsanalyse unvollständig. Variante PRIVATE_LOG')
                self.assertEqual(help_['kind'], kind)
                self.assertIn('kontrollierte Wiederholung', help_['cause'])
                self.assertIn('Teilbericht', help_['action'])
                self.assertNotIn('PRIVATE', json.dumps(help_))
        self.assertEqual(repetition_failure_marker({'conditions': [{'status': 'success',
            'failure_guidance': [{'kind': 'memory'}]}]}), '')
        self.assertEqual(repetition_failure_marker({'conditions': []}), '')
        self.assertEqual(failure_help('Wiederholungsfehler [PRIVATE_UNKNOWN]')['kind'], 'unknown')

    def test_both_reports_show_fixed_actions_but_never_saved_free_text(self):
        condition = {'sample_id': 'baseline-1', 'configuration_id': 'baseline', 'status': 'failed',
            'failure_guidance': [{'module': 'blind_coding', 'kind': 'context',
                                  'cause': 'PRIVATE', 'action': 'PRIVATE'}]}
        stability = {'conditions': [condition], 'comparisons': {}, 'notes': []}
        sensitivity = {**stability, 'configurations': [{'configuration_id': 'baseline',
            'changes': [], 'joint_changes': False}]}
        for rendered in (render_stability(stability), render_sensitivity(sensitivity)):
            self.assertIn('Fehlerhilfe: baseline-1', rendered)
            self.assertIn('Unabhängige Codierung', rendered)
            self.assertIn('Kontextfenster', rendered)
            self.assertIn('neuen Lauf', rendered)
            self.assertNotIn('PRIVATE', rendered)

    def test_unrecorded_failure_is_explicit_in_report(self):
        rendered = render_stability({'conditions': [{'sample_id': 'repeat-1', 'status': 'failed'}],
                                    'comparisons': {}, 'notes': []})
        self.assertIn('Fehlerkategorie wurde nicht gesichert', rendered)
        self.assertIn('Vor dem Teilen', rendered)
        self.assertNotIn('Kontextfenster', rendered)
        for value in (None, {}, [], True):
            self.assertEqual(fixed_failure_help(value)['kind'], 'unknown')


if __name__ == '__main__':
    unittest.main()
