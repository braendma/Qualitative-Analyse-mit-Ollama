import copy
import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from test_codebook_diagnostics import verify, single
from coding_validation_common import load_codebook, load_segments
from coding_agreement_core import calculate_agreement
from review_queue import build_queue
from runtime_support import file_hash, atomic_json
from codebook_diagnostics import load_codebook_snapshot, analyze_snapshot, main


class Workspace:
    def __init__(self, root):
        self.root = root
        self.config, self.source, self.book = root/'config.yaml', root/'input.csv', root/'book.csv'
        self.source.write_text('ID;Person;Code;Text\ns1;P1;A;Künstlicher Text\ns2;P2;B;Weiteres Beispiel\n', encoding='utf-8')
        self.book.write_text('Code;Definition;Ankerbeispiel\nA;Erste Bedeutung;Erstes Beispiel\nB;Zweite Bedeutung;Zweites Beispiel\n', encoding='utf-8')
        self.cfg = {'paths': {'category_system_csv': 'book.csv'},
                    'columns': {'segment_id':'ID', 'person':'Person', 'code':'Code', 'segment':'Text'},
                    'pipeline': {'modules': []}}
        self.paths = {'code_verification':'verify-custom.json', 'blind_coding':'blind-custom.json',
                      'coding_agreement':'agreement-custom.json', 'review_queue':'queue-custom.json'}
        for mid, name in self.paths.items():
            self.cfg['pipeline']['modules'].append({'id':mid, 'enabled':True,
                'args':['--queue-json' if mid=='review_queue' else '--out-json', name],
                'outputs':[name, 'auxiliary.json']})
        self.config.write_text(yaml.safe_dump(self.cfg, allow_unicode=True), encoding='utf-8')
        self.segments = load_segments(self.source, self.cfg['columns'])
        self.codes, _ = load_codebook(self.book)
        v, b = verify(self.segments), single(self.segments, ['B','B'])
        _, a = calculate_agreement(self.segments, self.codes, v, b)
        q = build_queue(self.segments, self.codes, a, v, b, {'befunde':[]})
        self.payloads = dict(zip(self.paths, [v,b,a,q]))
        for mid, payload in self.payloads.items():
            atomic_json(root/self.paths[mid], payload)
        atomic_json(root/'auxiliary.json', {'not_a_source':True})
        self.manifest = {'run_id':'synthetic-codebook', 'completed_steps':list(self.paths),
            'module_status':{mid:'success' for mid in self.paths},
            'output_hashes':{name:file_hash(root/name) for name in self.paths.values()},
            'provenance':{'config_sha256':file_hash(self.config), 'input_sha256':file_hash(self.source),
                          'codebook_sha256':file_hash(self.book)}}
        self.save_manifest()

    def save_manifest(self):
        atomic_json(self.root/'workflow_manifest.json', self.manifest)

    def load(self):
        return load_codebook_snapshot(self.root, self.config, self.source)

    def args(self, stem='diagnosis'):
        return ['--config', str(self.config), '--input-csv', str(self.source), '--run-dir', str(self.root),
                '--out-json', str(self.root/(stem+'.json')), '--out-md', str(self.root/(stem+'.md'))]


class CodebookLoaderTests(unittest.TestCase):
    def test_megabyte_multiline_unicode_csv_reaches_diagnosis_without_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            text=('„Zitat; mehrere Spalten?“\n日本語 🙂 <script>kein Code</script>\t' * 22000)
            self.assertGreater(len(text),1000000)
            for path, header, rows in (
                (w.source,['ID','Person','Code','Text'],[['s1','P1','A',text],['s2','P2','B','Kurz']]),
                (w.book,['Code','Definition','Ankerbeispiel'],[['A',text,'Anker; mit\nZeilenumbruch'],['B','Andere Definition','']])):
                with path.open('w',encoding='utf-8-sig',newline='') as stream:
                    writer=csv.writer(stream,delimiter=';');writer.writerow(header);writer.writerows(rows)
            for module in w.cfg['pipeline']['modules']:module['enabled']=False
            w.config.write_text(yaml.safe_dump(w.cfg),encoding='utf-8')
            for key,path in [('input_sha256',w.source),('codebook_sha256',w.book),('config_sha256',w.config)]:
                w.manifest['provenance'][key]=file_hash(path)
            w.save_manifest();before={p:p.read_bytes() for p in (w.source,w.book)}
            snapshot=w.load()
            self.assertEqual(snapshot['segments'][0].text,text)
            # Existing codebook import normalizes whitespace, but must keep all content.
            self.assertEqual(snapshot['codebook'][0].definition,' '.join(text.split()))
            main(w.args())
            result=json.loads((w.root/'diagnosis.json').read_text(encoding='utf-8'))
            self.assertEqual(result['processing_status'],'completed')
            self.assertNotIn('<script>',(w.root/'diagnosis.md').read_text(encoding='utf-8'))
            for path,content in before.items():self.assertEqual(path.read_bytes(),content)

    def test_verified_but_broken_json_and_missing_file_are_visible_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));target=w.root/'blind-custom.json'
            for content in ('{"results":', '[]', '['*1500+'0'+']'*1500):
                with self.subTest(content_length=len(content)):
                    target.write_text(content,encoding='utf-8')
                    w.manifest['output_hashes'][target.name]=file_hash(target);w.save_manifest()
                    snap=w.load()
                    self.assertEqual(snap['stages']['blind_coding']['status'],'invalid')
                    self.assertTrue(snap['stages']['blind_coding']['reason'])
                    self.assertEqual(analyze_snapshot(snap)['processing_status'],'incomplete')
            target.unlink()
            self.assertEqual(w.load()['stages']['blind_coding']['status'],'invalid')

    def test_declared_custom_outputs_queue_selector_and_originals_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            before={p:p.read_bytes() for p in w.root.iterdir()}
            main(w.args())
            result=json.loads((w.root/'diagnosis.json').read_text(encoding='utf-8'))
            self.assertEqual(result['processing_status'],'completed')
            self.assertEqual(result['codebook_source']['sha256'],file_hash(w.book))
            self.assertEqual(result['source_artifacts']['review_queue']['artifact'],'queue-custom.json')
            self.assertEqual(result['categories'][0]['missing_in_blind'],1)
            self.assertIn('verify-custom.json',(w.root/'diagnosis.md').read_text(encoding='utf-8'))
            self.assertNotIn('payload',result['source_artifacts']['blind_coding'])
            for path, content in before.items():
                self.assertEqual(path.read_bytes(),content)

    def test_changed_codebook_and_missing_provenance_reject_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));original=w.book.read_bytes()
            w.book.write_text(w.book.read_text(encoding='utf-8').replace('Erste Bedeutung','Geänderte Bedeutung'),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Kategoriesystem fehlt.*verändert'):
                main(w.args())
            self.assertFalse((w.root/'diagnosis.json').exists())
            w.book.write_bytes(original)
            del w.manifest['provenance']['codebook_sha256'];w.save_manifest()
            with self.assertRaisesRegex(ValueError,'Kategoriesystem fehlt'):
                main(w.args())

    def test_changed_inputs_config_and_duplicate_source_ids_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            w.source.write_text(w.source.read_text(encoding='utf-8')+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Diagnose abgelehnt'):
                w.load()
            w.manifest['provenance']['input_sha256']=file_hash(w.source);w.save_manifest()
            w.cfg['pipeline']['modules'].append(copy.deepcopy(w.cfg['pipeline']['modules'][0]))
            w.config.write_text(yaml.safe_dump(w.cfg),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Diagnose abgelehnt'):
                w.load()
            w.manifest['provenance']['config_sha256']=file_hash(w.config);w.save_manifest()
            with self.assertRaisesRegex(ValueError,'doppelte Quellmodul-ID'):
                w.load()

    def test_corruption_and_unfinished_sources_are_not_empty_successes(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            (w.root/'blind-custom.json').write_text('{}',encoding='utf-8')
            snap=w.load();result=analyze_snapshot(snap)
            self.assertEqual(result['processing_status'],'incomplete')
            self.assertEqual(snap['stages']['blind_coding']['status'],'invalid')
            self.assertEqual(snap['stages']['coding_agreement']['status'],'invalid')
            self.assertIsNone(result['categories'][0]['predicted_units'])
            payload=copy.deepcopy(w.payloads['blind_coding']);payload['processing_status']='incomplete'
            atomic_json(w.root/'blind-custom.json',payload)
            w.manifest['output_hashes']['blind-custom.json']=file_hash(w.root/'blind-custom.json');w.save_manifest()
            self.assertEqual(w.load()['stages']['blind_coding']['status'],'invalid')

    def test_disabled_source_is_not_read_and_does_not_invalidate_material_only_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            for module in w.cfg['pipeline']['modules']:module['enabled']=False
            w.config.write_text(yaml.safe_dump(w.cfg),encoding='utf-8')
            w.manifest['provenance']['config_sha256']=file_hash(w.config);w.save_manifest()
            (w.root/'blind-custom.json').write_text('invalid JSON',encoding='utf-8')
            result=analyze_snapshot(w.load())
            self.assertEqual(result['processing_status'],'completed')
            self.assertIsNone(result['blind_unit_states'])
            self.assertEqual(result['categories'][0]['human_units'],1)

    def test_outside_run_artifact_is_rejected_even_with_matching_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';run.mkdir();w=Workspace(run)
            external=root/'external.json';atomic_json(external,w.payloads['blind_coding'])
            module=w.cfg['pipeline']['modules'][1]
            module.update(args=['--out-json','../external.json'],outputs=['../external.json'])
            w.config.write_text(yaml.safe_dump(w.cfg),encoding='utf-8')
            w.manifest['provenance']['config_sha256']=file_hash(w.config)
            w.manifest['output_hashes']['../external.json']=file_hash(external);w.save_manifest()
            self.assertEqual(w.load()['stages']['blind_coding']['status'],'invalid')

    def test_own_retry_recomputes_and_never_overwrites_original_codebook(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            w.manifest['completed_steps'].remove('blind_coding')
            w.manifest['module_status']['blind_coding']='failed';w.save_manifest()
            main(w.args())
            self.assertEqual(json.loads((w.root/'diagnosis.json').read_text())['processing_status'],'incomplete')
            w.manifest['completed_steps'].append('blind_coding')
            w.manifest['module_status'].update(blind_coding='success',codebook_diagnostics='running');w.save_manifest()
            with self.assertRaisesRegex(ValueError,'existiert bereits'):
                main(w.args())
            original=w.book.read_bytes()
            with patch.dict(os.environ,{'WORKFLOW_RUN_ID':'synthetic-codebook','WORKFLOW_MODULE':'codebook_diagnostics'}):
                main(w.args())
                with self.assertRaisesRegex(ValueError,'überschreiben'):
                    main(w.args()[:-4]+['--out-json',str(w.book),'--out-md',str(w.root/'fresh.md')])
            self.assertEqual(w.book.read_bytes(),original)
            self.assertEqual(json.loads((w.root/'diagnosis.json').read_text())['processing_status'],'completed')

    def test_hash_verified_but_structurally_invalid_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));v=copy.deepcopy(w.payloads['code_verification'])
            v['results'][0]['segment_id']='unexpected'
            atomic_json(w.root/'verify-custom.json',v)
            w.manifest['output_hashes']['verify-custom.json']=file_hash(w.root/'verify-custom.json');w.save_manifest()
            with self.assertRaisesRegex(ValueError,'Codebook-Diagnose abgelehnt'):
                main(w.args())
            self.assertFalse((w.root/'diagnosis.json').exists())


if __name__=='__main__':
    unittest.main()
