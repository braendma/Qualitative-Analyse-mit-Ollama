import base64
import csv
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from coding_validation_common import load_codebook, MockLLM, Segment
from local_app import App, csv_info
from blind_coding_core import blind_code_segments
from code_verification_core import verify_segments
from multi_label_core import blind_code_units
from review_workspace import compare_books
from test_review_workspace import fixture, decision


class CodebookRuleTests(unittest.TestCase):
    def test_manual_mapping_preview_and_optional_rules_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Artificial mapping')['id']
            raw=(ROOT/'demo/Kategoriesystem_mit_Regeln.csv').read_bytes()
            info=app.upload(pid,'codebook','example.csv',base64.b64encode(raw).decode())['codebook']
            self.assertEqual(info['headers'][0],'Bezeichnung')
            self.assertEqual(info['count'],3)
            self.assertNotIn('book_columns',app.project(pid)['settings'])
            seg='Text;Person;Code\nEin geduldiger Mentor erklärt mir den Sensor.;P1;Lernangebot > Begleitung\n'
            app.upload(pid,'segments','segments.csv',base64.b64encode(seg.encode()).decode())
            opts={'model':'mock','columns':{'segment':'Text','person':'Person','code':'Code'},'label_mode':'unspecified',
                  'modules':['blind_coding'],'book_columns':{'code':'Bezeichnung','definition':'Bedeutung',
                  'abgrenzung':'Abgrenzende Hinweise','einschluss':'Wann zuordnen','ausschluss':'Wann nicht zuordnen','ankerbeispiel':'Typische Aussage'}}
            for book in ({},{'code':'Bezeichnung'},{'definition':'Bedeutung'},{**opts['book_columns'],'definition':'Fehlt'},
                         {**opts['book_columns'],'ausschluss':'Wann zuordnen'}):
                with self.assertRaises(ValueError):app.save(pid,{**opts,'book_columns':book})
                with self.assertRaises(ValueError):app.start(pid)
            identity=app.person_preview(pid,opts['columns'])
            opts['person_identity']={'confirmed':True,'fingerprint':identity['fingerprint'],'mapping':{'P1':'P1'}}
            result=app.save(pid,opts)
            self.assertEqual(result['codebook_fields']['einschluss'],3)
            self.assertEqual(result['model_calls'],0)
            rev=app.project_dir(pid)/'revisions'/app.project(pid)['revision']
            book=load_codebook(rev/'codebook.csv')[1]
            self.assertIn('Begleitperson',book['Lernangebot > Begleitung'].einschluss)
            self.assertIn('persönliche Unterstützung',book['Lernangebot > Begleitung'].abgrenzung)
            self.assertEqual(book['Lernangebot > Begleitung'].levels()['unterkategorie'],'Lernangebot > Begleitung')
            before=(rev/'codebook.csv').read_bytes()
            app.save(pid,{**opts,'book_columns':{'code':'Bezeichnung','definition':'Bedeutung'}})
            current=app.project_dir(pid)/'revisions'/app.project(pid)['revision']
            self.assertFalse(any(c.einschluss for c in load_codebook(current/'codebook.csv')[0]))
            self.assertEqual((rev/'codebook.csv').read_bytes(),before)
            self.assertEqual((app.project_dir(pid)/'inputs'/(info['id']+'.csv')).read_bytes(),raw)

    def test_minimal_legacy_duplicate_and_conflicting_hierarchy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'book.csv'
            path.write_text('Code;Definition;Einschlusskriterien;Ausschlusskriterien\nA > B;Test;Erste Regel;Kein C\nA > B;Test;Zweite Regel;Kein C\n',encoding='utf-8')
            entry=load_codebook(path)[0][0]
            self.assertEqual(entry.einschluss,'Erste Regel | Zweite Regel')
            self.assertEqual(entry.ausschluss,'Kein C')
            path.write_text('Kategorie;Definition\nA;Test\n',encoding='utf-8')
            self.assertEqual(load_codebook(path)[0][0].einschluss,'')
            for text in ('Code;Kategorie;Definition\nA > B;X;Test\n','Code;Definition\nA >> B;Test\n','Code;Definition\n;Test\n'):
                path.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError):load_codebook(path)
            demo=load_codebook(ROOT/'demo/Kategoriesystem.csv')[0]
            self.assertEqual(len(demo),12)
            self.assertTrue(all(c.einschluss and c.ausschluss and c.abgrenzung for c in demo))

    def test_rules_reach_all_coding_prompts_without_human_labels_in_blind(self):
        book=load_codebook(ROOT/'demo/Kategoriesystem.csv')[0][:1]
        book=[replace(book[0],einschluss='Konkrete Begleitung erforderlich.',ausschluss='Reine Geräteausstattung ausschließen.',abgrenzung='Persönliche Unterstützung von Ausstattung unterscheiden.')]
        seg=[Segment('S1','Jemand erklärt mir den Sensor.',book[0].code,'P1','U1')]
        params={'model':'mock','max_tokens':1000}
        prompts={'blind_coding':{'system':'Codiere','user':'{segment_id} {segment} {codebook}'},
                 'code_verification':{'system':'Prüfe','user':'{segment_id} {segment} {human_code} {target_code} {codebook}'}}
        responses=[{'segment_id':'S1','predicted_code':book[0].code,'confidence':'mittel','begruendung':'Test','alternative_codes':[]},
                   {'segment_id':'S1','human_code':book[0].code,'verification':'bestätigt','confidence':'mittel','begruendung':'Test','alternative_codes':[]}]
        for function,response in zip((blind_code_segments,verify_segments),responses):
            mock=MockLLM([response]);function(seg,book,prompts,{},params,llm=mock)
            content=json.dumps(mock.calls,ensure_ascii=False)
            self.assertIn(book[0].einschluss,content);self.assertIn(book[0].ausschluss,content)
            self.assertIn('Einschlussbedingungen',content);self.assertIn(book[0].abgrenzung,content)
            if function==blind_code_segments:self.assertNotIn('human_code',content)
        captured=[]
        def llm(messages,params):
            captured.extend(messages);payload=json.loads(messages[1]['content'])
            return json.dumps({'unit_id':payload['unit_id'],'predicted_codes':[book[0].code],'assignment_status':'assigned','confidence':'mittel','begruendung':'Test'})
        blind_code_units(seg,book,prompts,{},params,llm=llm)
        content=json.dumps(captured,ensure_ascii=False)
        self.assertIn(book[0].ausschluss,content);self.assertIn('Einschlussbedingungen',content);self.assertIn(book[0].abgrenzung,content);self.assertNotIn('human_code',content)
        changed=compare_books(book,[replace(book[0],ausschluss='Neue Grenze')],seg)
        self.assertEqual(changed['affected_count'],1)
        self.assertEqual(changed['changed'][0]['after']['ausschluss'],'Neue Grenze')

    def test_followup_retains_rules_after_next_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,queue,cfg=fixture(tmp)
            path=Path(yaml.safe_load(cfg.read_text())['paths']['category_system_csv'])
            rows=list(csv.reader(io.StringIO(path.read_text(encoding='utf-8')),delimiter=';'))
            for row in rows[1:]:
                row[rows[0].index('Einschlussregeln')]='Regel erhalten'
                row[rows[0].index('Ausschlussregeln')]='Grenze erhalten'
            output=io.StringIO();csv.writer(output,delimiter=';',lineterminator='\n').writerows(rows);path.write_text(output.getvalue(),encoding='utf-8')
            app.save_review(pid,jid,decision(),0)
            prepared=app.prepare_followup(pid,jid,1)['project']
            self.assertEqual(prepared['settings']['book_columns']['einschluss'],'Einschlussregeln')
            app.save(pid,prepared['settings'])
            new=app.project_dir(pid)/'revisions'/app.project(pid)['revision']/'codebook.csv'
            self.assertTrue(all(c.einschluss=='Regel erhalten' and c.ausschluss=='Grenze erhalten' for c in load_codebook(new)[0]))


if __name__=='__main__':unittest.main()
