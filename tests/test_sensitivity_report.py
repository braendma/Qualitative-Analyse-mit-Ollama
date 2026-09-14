import unittest

from test_codebook_diagnostics import book, single
from test_stability_core import clusters
from coding_validation_common import Segment
from sensitivity_core import analyze_sensitivity
from sensitivity_report import render_sensitivity


class SensitivityReportTests(unittest.TestCase):
    def report(self, segments, baseline, variant, mid='blind_coding'):
        configurations = [{'configuration_id': cid, 'changes': [] if cid == 'baseline' else
            [{'path': 'prompts.blind_coding.system', 'before_sha256': 'a'*64, 'after_sha256': 'b'*64}],
            'joint_changes': cid != 'baseline'} for cid in ('baseline', 'variant')]
        samples = [{'sample_id': f'{cid}-{i}', 'configuration_id': cid, 'status': 'success', 'payload': payload}
                   for cid, payload in [('baseline', baseline), ('variant', variant)] for i in (1, 2)]
        comparison = analyze_sensitivity(segments, [book('A'), book('B')], mid, configurations, samples)
        for within in comparison['within_configurations'].values():
            within['runtime_comparison'] = {'parameter_profiles_same': None}
        return render_sensitivity({'configurations': configurations, 'comparisons': {mid: comparison},
            'conditions': [{k: s[k] for k in ('sample_id', 'configuration_id', 'status')} for s in samples],
            'notes': ['Keine serverinterne Bestätigung.']})

    def test_quotes_safe_no_fingerprints_and_missing_runtime_explicit(self):
        segments = [Segment('a', '<script>alert(1)</script>' * 100, 'A', 'P | <b>')]
        rendered = self.report(segments, single(segments, ['A']), single(segments, ['keine_zuordnung']))
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<b>', rendered)
        self.assertNotIn('a'*64, rendered)
        self.assertNotIn('b'*64, rendered)
        self.assertIn('Textauszug gekürzt', rendered)
        self.assertIn('Keine akzeptierten Anfragen nachgewiesen', rendered)
        self.assertIn('Mehrere Änderungen gleichzeitig', rendered)
        self.assertIn('tatsächliche Verwendung ist nicht gesondert nachgewiesen', rendered)
        self.assertIn('begründet keine Zuordnung', rendered)
        self.assertIn('keine Codes zugeordnet', rendered)

    def test_display_limits_have_explicit_remainder(self):
        segments = [Segment(str(i), 'Künstlicher Text', 'A', f'P{i}') for i in range(90)]
        payload = clusters(*[[s.segment_id] for s in segments])
        rendered = self.report(segments, payload, payload, 'clusterer')
        self.assertIn('weitere Befunde stehen vollständig in der JSON-Datei', rendered)
        self.assertIn('weitere Verteilungen stehen vollständig im JSON', rendered)
        self.assertIn('Spannweiten zeigen Minimum bis Maximum', rendered)


if __name__ == '__main__':
    unittest.main()
