import base64
import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from passage_ids import prepare, apply
from local_app import App

COLS={'person':'Dokumentname','segment':'Segment','code':'Code','segment_id':'','unit_id':''}
RAW=('Dokumentgruppe;Dokumentname;Anfang;Ende;Code;Segment\n'
     'A;P1;2;2;Übung;  Exakter Text.\n'
     'A;P1;2;2;Austausch;  Exakter Text.\n'
     'B;P1;2;2;Übung;  Exakter Text.\n'
     'A;P1;3;3;Übung;  Exakter Text.\n'
     'A;P2;2;2;Übung;  Exakter Text.\n'
     'A;P1;2;2;Übung;Exakter Text.\n'
     'A;P1;;;Übung;  Exakter Text.\n').encode()

class PassageTests(unittest.TestCase):
    def test_exact_location_candidates_and_explicit_confirmation(self):
        preview,_,_=prepare(RAW,COLS)
        self.assertEqual([c['rows'] for c in preview['candidates']],[[2,3]])
        raw,mapped,meta=apply(RAW,COLS,preview['fingerprint'],['0'])
        rows=list(csv.DictReader(io.StringIO(raw.decode()),delimiter=';'))
        self.assertEqual(len(rows),7)
        self.assertEqual(len({r['segment_id'] for r in rows}),7)
        self.assertEqual(len({r['PassageID'] for r in rows}),6)
        self.assertEqual(rows[0]['Segment'],'  Exakter Text.')
        self.assertEqual(mapped['unit_id'],'PassageID')
        self.assertEqual(meta['passages'],6)
        _,_,separate=apply(RAW,COLS,preview['fingerprint'],[])
        self.assertEqual(separate['passages'],7)

    def test_stale_input_mapping_and_invalid_groups_are_rejected(self):
        preview,_,_=prepare(RAW,COLS)
        for raw,columns,groups in [(RAW+b'A;P3;1;1;C;Text\n',COLS,[]),
                                  (RAW,{**COLS,'segment_id':None},[]),
                                  (RAW,COLS,['999']),(RAW,COLS,['0','0'])]:
            with self.assertRaises(ValueError):apply(raw,columns,preview['fingerprint'],groups)

    def test_no_guessing_without_positions_or_overwriting_existing_ids(self):
        for raw in [b'Dokumentname;Code;Segment\nP;C;T\n',
                    RAW.replace(b'Dokumentgruppe;',b'PassageID;')]:
            with self.assertRaises(ValueError):prepare(raw,COLS)
        with self.assertRaises(ValueError):prepare(RAW,{**COLS,'unit_id':'custom'})

    def test_app_creates_new_input_preserves_original_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetic')['id']
            source=app.upload(pid,'segments','export.csv',base64.b64encode(RAW).decode())['segments']['id']
            preview=app.passage_preview(pid,COLS)
            updated=app.passage_apply(pid,{'columns':COLS,'model':'mock'},preview['fingerprint'],['0'])
            self.assertNotEqual(updated['uploads']['segments']['id'],source)
            self.assertEqual((app.project_dir(pid)/'inputs'/(source+'.csv')).read_bytes(),RAW)
            self.assertEqual(App(tmp).project(pid)['settings']['columns']['unit_id'],'PassageID')
            with self.assertRaises(ValueError):app.passage_apply(pid,{'columns':COLS},preview['fingerprint'],['0'])
