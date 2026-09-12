import csv
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from person_identity import preview,apply,verify
from coding_validation_common import segments_from_frame
import pandas as pd

class PersonIdentityTests(unittest.TestCase):
    def setUp(self):
        self.raw='Document;Text;Code\nInterview_A_part1;Gleicher Text;K\nInterview_A_part2;Anderer Text;K\nInterview_B;Gleicher Text;K\n'.encode()
        self.columns={'person':'Document','segment':'Text','code':'Code','segment_id':None,'unit_id':None}
        self.assignment={'confirmed':True,'fingerprint':preview(self.raw,self.columns)['fingerprint'],
            'mapping':{'Interview_A_part1':'P01','Interview_A_part2':'P01','Interview_B':'P02'}}

    def test_grouping_preserves_original_ids_text_codes_and_order(self):
        rows=list(csv.DictReader(io.StringIO(self.raw.decode()),delimiter=';'))
        old=segments_from_frame(pd.DataFrame(rows),self.columns)
        raw,columns,receipt=apply(self.raw,self.columns,self.assignment)
        newrows=list(csv.DictReader(io.StringIO(raw.decode()),delimiter=';'))
        new=segments_from_frame(pd.DataFrame(newrows),columns)
        self.assertEqual(verify(raw,columns,receipt),2)
        self.assertEqual([s.person for s in new],['P01','P01','P02'])
        self.assertEqual([s.segment_id for s in old],[s.segment_id for s in new])
        self.assertEqual([{k:r[k] for k in rows[0]} for r in newrows],rows)
        self.assertEqual(len({s.segment_id for s in new}),3)

    def test_optional_empty_columns_match_ui_and_backend(self):
        columns={**self.columns,'segment_id':'','unit_id':''}
        self.assertEqual(preview(self.raw,columns)['fingerprint'],self.assignment['fingerprint'])

    def test_missing_confirmation_stale_file_and_incomplete_mapping_rejected(self):
        for assignment in (None,{**self.assignment,'confirmed':False},
                {**self.assignment,'mapping':{'Interview_B':'P02'}}):
            with self.assertRaises(ValueError):apply(self.raw,self.columns,assignment)
        with self.assertRaises(ValueError):apply(self.raw+b'Interview_B;Neu;K\n',self.columns,self.assignment)
        with self.assertRaises(ValueError):apply(self.raw,{**self.columns,'person':'Text'},self.assignment)

    def test_saved_receipt_rejects_modified_csv(self):
        raw,columns,receipt=apply(self.raw,self.columns,self.assignment)
        with self.assertRaises(ValueError):verify(raw.replace(b'P02',b'P01'),columns,receipt)

    def test_explicit_segment_ids_preserved(self):
        raw=b'Document;Text;Code;ID\nInterview_A_part1;Text;K;original-id\n'
        columns={**self.columns,'segment_id':'ID'}
        assignment={'confirmed':True,'fingerprint':preview(raw,columns)['fingerprint'],
            'mapping':{'Interview_A_part1':'P01'}}
        normalized,cols,receipt=apply(raw,columns,assignment)
        rows=list(csv.DictReader(io.StringIO(normalized.decode()),delimiter=';'))
        self.assertEqual(rows[0][cols['segment_id']],'original-id')

if __name__=='__main__':unittest.main()
