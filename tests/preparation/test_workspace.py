import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import llm_review as r
from import_transcript import parse_bytes
from workspace_store import ProjectStore, empty_project
from transcription_monitor import Session


class ImportTests(unittest.TestCase):
    def test_txt_unknown_times_and_f4_timestamp(self):
        d=parse_bytes('f4.txt','I: Warum?\nB: Gern. #00:01:02-5#'.encode())
        self.assertIsNone(d['segments'][0]['start']);self.assertEqual(d['segments'][1]['start'],62.5)
        self.assertFalse(d['review']['confirmed']);self.assertEqual(d['segments'][1]['speaker'],'B')
    def test_srt_vtt_preserve_unicode_overlap(self):
        for suffix,value in [('srt','1\n00:00:01,000 --> 00:00:03,000\n🙂 Ja\n\n2\n00:00:02,000 --> 00:00:04,000\nNein'),('vtt','WEBVTT\n\n00:01.000 --> 00:03.000\n<v Person A>Ja &amp; nein</v>')]:
            d=parse_bytes('test.'+suffix,value.encode());self.assertEqual(d['segments'][0]['start'],1)
            self.assertNotIn('<v',d['segments'][0]['text'])
        with self.assertRaises(ValueError):parse_bytes('bad.srt',b'broken unrecognised block')
    def test_docx_rtf_and_encoding(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hallo Welt</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(parse_bytes('t.docx',stream.getvalue())['segments'][0]['text'],'Hallo Welt')
        self.assertIn('Grüße',parse_bytes('t.rtf',br"{\rtf1\ansi Gr\'fc\'dfe\par Zweite Zeile}")['segments'][0]['text'])
        with self.assertRaises(ValueError):parse_bytes('t.txt','Grüße'.encode('cp1252'))
        self.assertEqual(parse_bytes('t.txt','Grüße'.encode('cp1252'),'cp1252')['segments'][0]['text'],'Grüße')
        with self.assertRaises(ValueError):parse_bytes('t.mqda',b'anything')


class PersistenceTests(unittest.TestCase):
    def test_llm_decisions_reload_and_remain_bound_to_packet(self):
        from test_llm_review import packet, decide
        p=packet()
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'review'
            session=Session(None,output,p)
            draft=decide(p,'edit',{'code':'Motivation > Lehren'})
            session.review_store.save(draft,0,'decision-1')
            restored=Session(None,output,p).review_store.get()
            self.assertEqual(restored['project'],draft)
            self.assertEqual(restored['revision'],1)
            wrong=copy.deepcopy(draft);wrong['packet_sha256']='other'
            with self.assertRaises(ValueError):session.review_store.save(wrong,1,'decision-2')
            self.assertEqual(session.review_store.get()['project'],draft)

    def test_atomic_reload_conflict_and_backup_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'project.json';store=ProjectStore(path);p=empty_project()
            store.save(p,0,'m1');self.assertEqual(ProjectStore(path).get()['revision'],1)
            self.assertEqual(store.save(p,0,'m1')['revision'],1)
            with self.assertRaisesRegex(ValueError,'Speicherkonflikt'):store.save(p,0,'m2')
            p['ui_draft']={'code':'noch nicht fertig'};store.save(p,1,'m2')
            self.assertEqual(ProjectStore(path).get()['project']['ui_draft']['code'],'noch nicht fertig')
            path.write_text('{broken',encoding='utf-8');restored=ProjectStore(path)
            self.assertEqual(restored.get()['revision'],1);self.assertTrue(restored.get()['recovery'])
    def test_partial_transcript_edits_survive_arrival_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);audio=root/'test.wav';audio.write_bytes(b'synthetic placeholder; no playback in this unit test')
            output=root/'out';output.mkdir();segment={'id':1,'start':0,'end':1,'text':'Roh text','speaker':None}
            (output/'segments.partial.jsonl').write_text(json.dumps(segment)+'\n'+ '{unfinished',encoding='utf-8')
            session=Session(audio,output);state=session.state();self.assertEqual(len(state['segments']),1)
            s=state['segments'][0];session.edit({'revision':0,'segment_id':'1','source_sha256':s['source_sha256'],'text':'Rohtext'})
            later={'id':2,'start':1,'end':2,'text':'Weiter','speaker':None}
            (output/'segments.partial.jsonl').write_text(json.dumps(segment)+'\n'+json.dumps(later)+'\n',encoding='utf-8')
            restored=Session(audio,output);self.assertEqual(restored.state()['segments'][0]['display_text'],'Rohtext')
            self.assertEqual(len(restored.state()['segments']),2)
            segment['text']='Neuer ASR Stand'
            (output/'segments.partial.jsonl').write_text(json.dumps(segment)+'\n',encoding='utf-8')
            self.assertTrue(restored.state()['segments'][0]['conflict'])
            self.assertEqual(restored.state()['segments'][0]['display_text'],'Rohtext')
    def test_cross_language_integral_float_hash(self):
        self.assertEqual(r.fingerprint({'time':0.0}),r.fingerprint({'time':0}))


if __name__=='__main__':unittest.main()
