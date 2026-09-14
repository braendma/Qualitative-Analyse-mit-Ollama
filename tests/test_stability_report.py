import unittest
from test_stability_core import samples, swot
from test_codebook_diagnostics import book, single
from coding_validation_common import Segment
from stability_core import analyze_stage_repetitions, analyze_coding_repetitions
from stability_report import render_stability, ratio


class StabilityReportTests(unittest.TestCase):
    def test_readable_changed_texts_and_codes_are_escaped_not_opaque_hashes(self):
        segments=[Segment('a','Text <script>alert(1)</script> | [Link](http://example.org)','A','Person <b>')]
        a,b=single(segments,['A']),single(segments,['B'])
        coding=analyze_coding_repetitions(segments,[book('A'),book('B')],'blind_coding',samples(a,b))
        stage=analyze_stage_repetitions(segments,'swot',samples(swot(text='<img src=x>'),swot(text='Andere Aussage')))
        for result in (coding,stage):result['runtime_comparison']={'parameter_profiles_same':None}
        report={'conditions':[],'comparisons':{'blind_coding':coding,'swot':stage},'notes':[]}
        text=render_stability(report)
        self.assertIn('Andere Aussage',text)
        self.assertIn('&lt;script&gt;',text)
        self.assertNotIn('<script>',text)
        self.assertNotIn('<img',text)
        self.assertIn('Person &lt;b&gt;',text)
        self.assertIn('Codes: B',text)
        self.assertNotIn(stage['record_occurrences'][0]['fingerprint'],text)
        self.assertEqual(ratio({'value':None}),'nicht berechenbar')

    def test_empty_evidence_and_truncated_text_remain_explicit(self):
        segments=[Segment('a','A'*1500,'A','P')]
        a,b=single(segments,['A']),single(segments,['unklar'])
        result=analyze_coding_repetitions(segments,[book('A')],'blind_coding',samples(a,b))
        result['runtime_comparison']={'parameter_profiles_same':False}
        text=render_stability({'conditions':[],'comparisons':{'blind_coding':result},'notes':[]})
        self.assertIn('Auszug gekürzt (1500 Zeichen',text)
        self.assertIn('inhaltlich unsicher',text)
        self.assertIn('nicht berechenbar',text)
        self.assertIn('Bedingungen vor Interpretation prüfen',text)


if __name__=='__main__':unittest.main()
