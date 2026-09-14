import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from coding_validation_common import Segment
from person_identity import preview, apply
from runtime_support import file_hash
from thematic_material import build_material, load_counting_material, unit_ids_for_segments


def workspace(root, *, people=None):
    text=io.StringIO();writer=csv.writer(text,delimiter=';',lineterminator='\n')
    writer.writerow(['ID','Document','Passage','Code','Text'])
    mapping={}
    for i in range(12):
        for part in (1,2):
            document=f'D{i}_Teil{part}';mapping[document]=(people or {}).get(i,f'P{i}')
            writer.writerow([f's{i}_{part}',document,f'u{i}_{part}','A','Gleicher künstlicher Text; unverändert.'])
    raw=text.getvalue().encode('utf-8');columns={'segment_id':'ID','person':'Document','unit_id':'Passage','code':'Code','segment':'Text'}
    info=preview(raw,columns)
    normalized,columns,receipt=apply(raw,columns,{'confirmed':True,'fingerprint':info['fingerprint'],'mapping':mapping})
    (root/'input.csv').write_bytes(normalized)
    (root/'book.csv').write_text('Code;Definition;Ankerbeispiel\nA;Künstliches Thema;Künstlicher Text\n',encoding='utf-8')
    cfg={'paths':{'input_csv':'input.csv','category_system_csv':'book.csv'},'columns':columns,'person_identity':receipt}
    path=root/'config.yaml';path.write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf-8')
    return path,cfg


class ThematicMaterialTests(unittest.TestCase):
    def test_declared_passages_deduplicate_codes_but_never_equal_text(self):
        rows=[Segment('s1','gleich','A','P1','u1'),Segment('s2','gleich','B','P1','u1'),
              Segment('s3','gleich','A','P2','u2'),Segment('s4','gleich','A','P1','u3')]
        m=build_material(rows,person_basis='confirmed')
        self.assertEqual(m['counts'],{'coding_rows':4,'material_units':3,'passages':3,'persons':2})
        self.assertEqual(m['units']['passage:u1']['code_paths'],['A','B'])
        self.assertEqual(unit_ids_for_segments(m,['s2','s1','s3']),['passage:u1','passage:u2'])
        self.assertEqual(build_material(list(reversed(rows)),person_basis='confirmed'),m)
        with self.assertRaises(ValueError):unit_ids_for_segments(m,['foreign'])

    def test_unconfirmed_people_or_missing_passage_ids_never_become_exact_counts(self):
        rows=[Segment('s1','gleich','A','Document_1'),Segment('s2','gleich','A','Document_2')]
        m=build_material(rows)
        self.assertIsNone(m['counts']['persons']);self.assertIsNone(m['counts']['passages'])
        self.assertEqual(m['counts']['material_units'],2)
        mixed=build_material(rows+[Segment('s3','gleich','A','Document_1','s1')])
        self.assertEqual(len(mixed['units']),3)
        self.assertIsNone(mixed['counts']['passages'])
        self.assertIn('coding_row:s1',mixed['units']);self.assertIn('passage:s1',mixed['units'])

    def test_conflicts_and_invalid_kennungen_fail_without_printing_text(self):
        base=Segment('a','PRIVATE SYNTHETIC TEXT','A','P1','u')
        for other in (Segment('b','different','B','P1','u'),Segment('b',base.text,'B','P2','u'),base,
                      Segment('b','text','A','','u2'),Segment('b','text','A','P1','')):
            with self.subTest(other=other),self.assertRaises(ValueError) as caught:build_material([base,other])
            self.assertNotIn(base.text,str(caught.exception))

    def test_very_long_text_preserved_and_content_identity_changes(self):
        text=('Ä🙂;\nAbweichende Position. '*50000)
        m=build_material([Segment('s1',text,'A','P1','u')])
        self.assertEqual(m['units']['passage:u']['text'],text)
        changed=build_material([Segment('s1',text+'x','A','P1','u')])
        self.assertNotEqual(m['basis_fingerprint'],changed['basis_fingerprint'])
        confirmed=build_material([Segment('s1',text,'A','P1','u')],person_basis='confirmed')
        self.assertNotEqual(m['basis_fingerprint'],confirmed['basis_fingerprint'])

    def test_loader_uses_confirmed_twelve_persons_from_twentyfour_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,cfg=workspace(root)
            before={p.name:p.read_bytes() for p in root.iterdir()}
            material=load_counting_material(path)
            self.assertEqual(material['counts']['persons'],12)
            self.assertEqual(material['counts']['passages'],24)
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})
            run=root/'run';run.mkdir()
            manifest={'provenance':{'input_sha256':file_hash(root/'input.csv'),'config_sha256':file_hash(path),'codebook_sha256':file_hash(root/'book.csv')}}
            (run/'workflow_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            self.assertEqual(material,load_counting_material(path,run_dir=run))
            manifest['provenance']['input_sha256']='0'*64
            (run/'workflow_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaises(ValueError):load_counting_material(path,run_dir=run)

    def test_missing_or_changed_confirmation_is_explicit_not_inferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,cfg=workspace(root)
            cfg.pop('person_identity');path.write_text(yaml.safe_dump(cfg),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'bestätigen'):load_counting_material(path)
            unknown=load_counting_material(path,require_confirmed=False)
            self.assertIsNone(unknown['counts']['persons'])
            path,cfg=workspace(root);cfg['person_identity']['mapping']['D0_Teil1']='OTHER'
            path.write_text(yaml.safe_dump(cfg),encoding='utf-8')
            with self.assertRaises(ValueError):load_counting_material(path,require_confirmed=False)

    def test_person_label_normalization_must_not_silently_merge_people(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,_=workspace(Path(tmp),people={0:'P 1',1:'P  1'})
            with self.assertRaisesRegex(ValueError,'Kennungen'):load_counting_material(path)

    def test_category_rules_and_confirmation_are_bound_in_material_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,_=workspace(root);before=load_counting_material(path)
            book=root/'book.csv';book.write_text(book.read_text(encoding='utf-8').replace('Künstliches Thema','Neue Regel'),encoding='utf-8')
            after=load_counting_material(path)
            self.assertNotEqual(before['basis_fingerprint'],after['basis_fingerprint'])
            book.write_text('Code;Definition\nB;Andere Kategorie\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Codes'):load_counting_material(path)


if __name__=='__main__':unittest.main()
