import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from synthesis_sources import source_details, clarify_source_lines
from html_report import build_html_report


class SourceTests(unittest.TestCase):
    def payload(self):
        return {'source_labels':['SWOT','Vergleich'], 'kernergebnisse':[{'quellen':['Nabc']}],
                'hierarchical_reduction':{'nodes':{'Nabc':{'input_ids':['Nchild','L2'], 'text':'Eine Verdichtung'},
                                                 'Nchild':{'input_ids':['L1','L2']}},
                 'leaves':{'L1':{'source':'SWOT','content':{'segment_ids':['S1'],'count':99}},
                           'L2':{'source':'Vergleich','content':{'nested':[{'segment_ids_a':['S2'],'segment_ids_b':['S1']}],
                                                             'unrelated_text':'S9'}}}}}

    def test_transitive_shared_sources_without_invented_or_duplicate_quotes(self):
        row=source_details(self.payload())['Nabc']
        self.assertEqual(row['labels'], ['SWOT','Vergleich'])
        self.assertEqual(row['segment_ids'], ['S1','S2'])
        self.assertFalse(row['unresolved'])
        self.assertIn('keine automatisch bestätigten', row['note'])

    def test_missing_and_cyclic_records_are_not_silently_complete(self):
        p=self.payload();p['hierarchical_reduction']['nodes']['Nchild']['input_ids'] += ['missing','Nabc']
        row=source_details(p)['Nabc']
        self.assertTrue(row['unresolved'])
        self.assertEqual(row['segment_ids'], ['S1','S2'])

    def test_old_markdown_explained_without_replacing_model_statement(self):
        text='## Ergebnis\nUnveränderte Aussage.\n**Analytische Quellen:** Nabc\n'
        rendered=clarify_source_lines(text, source_details(self.payload()))
        self.assertIn('Unveränderte Aussage.', rendered)
        self.assertIn('SWOT, Vergleich', rendered)
        self.assertIn('`Nabc`', rendered)
        self.assertNotIn('**Analytische Quellen:**', rendered)

    def test_custom_json_export_and_missing_registry_fail_visibly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);text='**Analytische Quellen:** Nabc\n'
            (root/'synth.md').write_text(text,encoding='utf-8')
            (root/'custom.json').write_text(json.dumps(self.payload()),encoding='utf-8')
            modules=[{'id':'overall_synthesis','name':'Synthese','args':['--out-json','custom.json'],
                      'report':{'markdown':'synth.md'}}]
            path=build_html_report(root,modules,'2026',config={})
            data=json.loads(re.search(r'id="report-data">(.*?)</script>',path.read_text(encoding='utf-8'),re.S)[1])
            self.assertEqual(data['sections'][0]['source_refs']['Nabc']['labels'],['SWOT','Vergleich'])
            self.assertEqual((root/'synth.md').read_text(encoding='utf-8'),text)
            (root/'custom.json').unlink()
            path=build_html_report(root,modules,'2026',config={})
            self.assertIn('Herkunftsdetails der Gesamtsynthese fehlen',path.read_text(encoding='utf-8'))
