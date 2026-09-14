"""Synthetic pathological material: preserve data, explain limits, never infer truth."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from coding_validation_common import load_segments, CodebookEntry, Segment
from context_preflight import check_context, require_context
from diagnostic_sources import make_snapshot, project_stage
from coverage_core import analyze_coverage, render_coverage
from runtime_support import fingerprint


class DiagnosticEdgeCases(unittest.TestCase):
    def test_megabyte_segment_survives_csv_and_deterministic_diagnosis(self):
        text = ('„Zitat; mit Trennzeichen“\n日本語 🙂 äöü <script>kein Code</script> '+
                '  unterschiedliche Leerzeichen\t') * 10000
        self.assertGreater(len(text.encode('utf-8')), 1000000)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sonderfall.csv'
            with path.open('w',encoding='utf-8-sig',newline='') as out:
                writer=csv.writer(out,delimiter=';')
                writer.writerow(['ID','Person','Code','Text'])
                writer.writerow(['a','P | <b>1</b>','A',text])
            before=path.read_bytes()
            segments=load_segments(path,{'segment_id':'ID','person':'Person','code':'Code','segment':'Text'})
            self.assertEqual(segments[0].text,text)
            snap=make_snapshot(segments,{})
            result=analyze_coverage(snap)
            self.assertEqual(result['material']['material_units'],1)
            self.assertEqual(snap['inputs']['a']['text_sha256'],fingerprint(text))
            self.assertEqual(path.read_bytes(),before)
            # Exported Markdown must not inject table cells or literal HTML tags.
            self.assertNotIn('<b>',render_coverage(result))

    def test_very_long_segment_and_large_codebook_block_model_work_in_preflight(self):
        cfg={'llm':{'num_ctx':16384,'max_tokens':2048},'context':{},
             'prompts':{'blind_coding':{'system':'Prüfe','user':'{segment}\n{codebook}'}},
             'coding_agreement':{'label_mode':'unspecified'}}
        short_book=[CodebookEntry('A','A','','','','Regel','Beispiel')]
        for text,book in [('Langtext '*20000,short_book),
                          ('Kurz', [CodebookEntry('A','A','','','','Definition '*20000,'Anker')])]:
            rows=[Segment('id',text,'A','P')]
            before=text
            report=check_context(cfg,rows,book,['blind_coding'])
            with self.assertRaisesRegex(ValueError,'Start gesperrt'):
                require_context(report)
            self.assertEqual(rows[0].text,before)
            # Deterministic diagnostics do not need a model context window.
            require_context(check_context(cfg,rows,book,['coverage']))

    def test_corrupt_nested_register_is_explained_not_empty_success(self):
        for stage,payload in [('person_analysis',{'persons':{'P':None}}),
            ('meta_swot',{'finding_registry':{'F':None},'meta_swot':{'Stärken':{
                'uebergreifende_muster':[{'finding_ids':['F']}],'einzelbefunde':[]}}})]:
            with self.assertRaises(ValueError):
                project_stage(stage,payload)

    def test_partial_source_failure_is_not_cached_as_completed_coverage(self):
        snap=make_snapshot([Segment('s','kurz','A','P')],{
            'swot':{'status':'unavailable','reason':'failed','warnings':[],'records':[]}})
        result=analyze_coverage(snap)
        self.assertEqual(result['processing_status'],'incomplete')
        self.assertIn('Vorläufige Diagnose',render_coverage(result))
        # Non-selected sources are not failures.
        snap['stages']['swot']['reason']='disabled'
        self.assertEqual(analyze_coverage(snap)['processing_status'],'completed')


if __name__=='__main__':unittest.main()
