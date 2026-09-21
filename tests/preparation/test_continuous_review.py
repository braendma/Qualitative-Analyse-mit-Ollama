import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
from types import SimpleNamespace

import llm_review as r
from continuous_review import align,reading
from transcription_monitor import Session
from reading_workflow import ReadingWorkflow,workspace
from reading_speakers import SpeakerPanel


def fixture(folder, speakers=False):
    audio=folder/'audio.wav'
    with wave.open(str(audio),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*16000*4)
    output=folder/'asr';output.mkdir()
    document={'segments':[{'id':1,'start':0,'end':2,'text':'Hallo eins','speaker':None,'words':[{'word':'Hallo','start':0,'end':1},{'word':' eins','start':1,'end':2}]},{'id':2,'start':2,'end':4,'text':'Zwei drei','speaker':None,'words':[{'word':' Zwei','start':2,'end':3},{'word':' drei','start':3,'end':4}]}]}
    r.write(output/'transcript.json',document)
    session=Session(audio,output);session.model_dir=folder/'model';session.model_dir.mkdir();(session.model_dir/'model_manifest.json').write_text('{}')
    r.write(output/'run.json',{'status':'completed','identity':{'audio_sha256':session.audio_hash},'outputs':{'transcript.json':session.file_hash(output/'transcript.json')}})
    if speakers:
        packet={'schema':1,'audio_sha256':session.audio_hash,'transcript_sha256':session.file_hash(output/'transcript.json'),'duration':4,'turns':[{'speaker':'A','start':0,'end':3},{'speaker':'B','start':3,'end':4}],'segments':copy.deepcopy(document['segments'])}
        for segment in packet['segments']:
            for word in segment['words']:word.update(speaker='A' if word['start']<3 else 'B',reason='suggested')
        target=folder/'asr_Sprecher';target.mkdir();r.write(target/'speaker_suggestions.json',packet);r.write(target/'run.json',{'status':'completed','outputs':{'speaker_suggestions.json':session.file_hash(target/'speaker_suggestions.json')}})
    return session,document


class ContinuousTests(unittest.TestCase):
    def test_utf16_edits_and_duplicate_tokens_never_get_invented_word_times(self):
        with tempfile.TemporaryDirectory() as temp:
            _,doc=fixture(Path(temp));values=align(doc,'🙂 Hallo neu Zwei drei')
            self.assertEqual((values[1]['from'],values[1]['to']),(3,8))
            self.assertFalse(values[0]['exact']);self.assertIsNone(values[0]['start']);self.assertEqual(values[0]['anchor'],0)
            self.assertFalse(values[2]['exact']);self.assertTrue(values[-1]['exact'])
            repeated=align(doc,'Hallo Hallo eins Zwei drei')
            self.assertTrue(all(not w['exact'] for w in repeated if w['text']=='Hallo'))

    def test_speaker_runs_cross_segments_and_switch_inside_segment(self):
        with tempfile.TemporaryDirectory() as temp:
            session,doc=fixture(Path(temp),True);state=reading(session).state()
            self.assertEqual(state['project']['text'],'Hallo eins Zwei\n\ndrei')
            self.assertEqual([w['speaker_label'] for w in state['words']],['P1','P1','P1','P2'])
            self.assertTrue(all(not w['person_confirmed'] for w in state['words']))
            session.expected_speakers=3
            self.assertIn('Erwartet 3',ReadingWorkflow(session,Session).state()['speaker_count_note'])

    def test_unknown_words_stay_inline_without_inheriting_speaker_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp),True)
            packet_path=session.output.parent/'asr_Sprecher'/'speaker_suggestions.json'
            packet=r.read(packet_path);packet['turns']=[{'speaker':'A','start':0,'end':4}]
            for segment in packet['segments']:
                for word in segment['words']:word['speaker']='A' if word['start'] in (1,3) else None
            packet_path.write_text(json.dumps(packet),encoding='utf-8');packet_path.with_name('run.json').write_text(json.dumps({'status':'completed','outputs':{'speaker_suggestions.json':session.file_hash(packet_path)}}),encoding='utf-8')
            state=reading(session).state()
            self.assertEqual(state['project']['text'],'Hallo eins Zwei drei')
            self.assertEqual([w['speaker'] for w in state['words']],[None,'A',None,'A'])
            self.assertEqual([w['speaker_label'] for w in state['words']],['','P1','','P1'])
            self.assertTrue(all(not w['person_confirmed'] for w in state['words']))

    def test_unknown_leadin_precedes_known_speaker_change_without_identity_assignment(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp),True)
            packet_path=session.output.parent/'asr_Sprecher'/'speaker_suggestions.json'
            packet=r.read(packet_path)
            for segment in packet['segments']:
                for word in segment['words']:word['speaker']='A' if word['start']==0 else None if word['start']==1 else 'B'
            packet_path.write_text(json.dumps(packet),encoding='utf-8');packet_path.with_name('run.json').write_text(json.dumps({'status':'completed','outputs':{'speaker_suggestions.json':session.file_hash(packet_path)}}),encoding='utf-8')
            state=reading(session).state()
            self.assertEqual(state['project']['text'],'Hallo\n\neins Zwei drei')
            self.assertIsNone(state['words'][1]['speaker'])
            self.assertEqual(state['words'][2]['speaker'],'B')
            self.assertEqual(state['words'][2]['anchor'],2)

    def test_direct_person_ranges_persist_export_and_detect_changed_text(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp),True);editor=reading(session);state=editor.state();project=copy.deepcopy(state['project'])
            project['speaker_overrides']=[{'id':'manual-1','first':1,'last':3,'person_id':'speaker:B','exclude':False,'reviewed_tokens':['eins','Zwei'],'reviewed_indices':[1,2]}]
            saved=editor.save({'project':project,'revision':0,'mutation_id':'direct'})
            self.assertEqual(saved['words'][1]['person'],'P2');self.assertTrue(saved['words'][1]['person_confirmed'])
            self.assertEqual(saved['words'][1]['start'],1)
            fresh=Session(session.audio,session.output);restored=reading(fresh).state()
            self.assertEqual(restored['project'],project)
            result=reading(fresh).finish({'revision':1,'reviewer':'Synthetic direct assignment','confirmed':True})
            self.assertTrue(any(s['person']=='P2' for s in result['project']['documents'][0]['segments']))
            self.assertEqual(result['transcript']['reading_speaker_overrides'],project['speaker_overrides'])
            changed={**project,'text':project['text'].replace('eins','korrigiert')}
            state=reading(fresh).save({'project':changed,'revision':1,'mutation_id':'text-after-person'})
            self.assertEqual(state['words'][1]['person'],'P2');self.assertTrue(state['words'][1]['assignment_needs_review'])
            self.assertFalse(state['words'][1]['person_confirmed']);self.assertIsNone(state['words'][1]['start'])
            with self.assertRaises(ValueError):reading(fresh).save({'project':project,'revision':1,'mutation_id':'stale-person'})
            invalid=copy.deepcopy(changed);invalid['speaker_overrides'].append({**invalid['speaker_overrides'][0],'id':'overlap','first':2,'last':4})
            with self.assertRaises(ValueError):reading(fresh).save({'project':invalid,'revision':2,'mutation_id':'overlap'})
            changed['people'].append({'id':'new-person','label':'P3','name':'SYN-P3','origin':'manual'})
            changed['speaker_overrides'].append({'id':'manual-2','first':3,'last':4,'person_id':'new-person','exclude':True,'reviewed_tokens':['drei'],'reviewed_indices':[3]})
            added=reading(fresh).save({'project':changed,'revision':2,'mutation_id':'new-person'})
            self.assertEqual(added['words'][-1]['speaker_label'],'P3');self.assertTrue(added['words'][-1]['exclude'])
            changed['people'][-1]['name']='SYN-Umbenannt'
            renamed=reading(fresh).save({'project':changed,'revision':3,'mutation_id':'rename'})
            self.assertEqual(renamed['words'][-1]['speaker_label'],'P3');self.assertEqual(renamed['words'][-1]['person'],'SYN-Umbenannt')
            final=reading(fresh).finish({'revision':4,'reviewer':'Synthetic direct assignment','confirmed':True})
            self.assertTrue(final['project']['documents'][0]['segments'][-1]['exclude'])

    def test_edited_word_end_does_not_expand_across_next_speaker_in_same_asr_segment(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp),True);editor=reading(session);project=editor.state()['project'];project['text']='Hallo eins Anders\n\ndrei'
            state=editor.save({'project':project,'revision':0,'mutation_id':'edited-before-switch'})
            self.assertIsNone(state['words'][2]['end']);self.assertEqual(state['words'][2]['anchor_end'],3)
            result=editor.finish({'revision':1,'reviewer':'Synthetic boundary test','confirmed':True})
            segment=next(s for s in result['transcript']['segments'] if s['text']=='Anders')
            self.assertEqual((segment['start'],segment['end']),(2,3))
            source=next(s for s in result['transcript']['source_segments'] if s['segment_id']==segment['id'])
            self.assertTrue(source['end_approximate']);self.assertEqual(source['last_source_token_exclusive'],3)

    def test_asr_only_is_unknown_and_source_tamper_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp));state=reading(session).state()
            self.assertTrue(all(w['speaker_label']=='' for w in state['words']))
            (session.output/'transcript.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Prüfsumme'):reading(session).ensure()

    def test_confirmed_speakers_preserve_existing_reading_text_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp),True);editor=reading(session);state=editor.state();project={**state['project'],'text':'Hallo Änderung Zwei\n\ndrei'}
            editor.save({'project':project,'revision':0,'mutation_id':'text'})
            # Simulate restart followed by opening speaker review before the reading page.
            session=Session(session.audio,session.output)
            panel=SpeakerPanel(session);draft=panel.store.get()['project']
            for g in draft['groups']:g['person']='SYN-'+g['speaker']
            panel.store.save(draft,0,'people');panel.approve({'revision':1,'reviewer':'Synthetic test','confirmed':True})
            fresh=Session(session.audio,session.output);new=reading(fresh).state()
            self.assertEqual(new['project']['text'],project['text'])
            self.assertNotEqual(new['project']['person_source_sha256'],project['person_source_sha256'])
            self.assertEqual(new['words'][-1]['person'],'SYN-B')
            self.assertTrue(new['words'][-1]['person_confirmed'])
            result=reading(fresh).finish({'revision':0,'reviewer':'Synthetic','confirmed':True})
            document=result['project']['documents'][0]
            self.assertEqual(document['transcript_sha256'],r.fingerprint(result['transcript']))
            self.assertEqual(document['segments'][-1]['person'],'SYN-B')
            self.assertEqual(document['segments'][0]['source_person_suggestion'],'SYN-A')
            self.assertEqual(document['segments'][0]['person'],'')
            self.assertFalse(document['segments'][0]['source_person_confirmed'])
            self.assertTrue((session.output.parent/result['project_filename']).is_file())
            with self.assertRaises(ValueError):reading(fresh).save({'project':project,'revision':0,'mutation_id':'stale-source'})
            second=SpeakerPanel(fresh);draft=second.store.get()['project']
            for group in draft['groups']:group['person']='SYN-B' if group['speaker']=='A' else 'SYN-A'
            second.store.save(draft,1,'correct-persons');second.approve({'revision':2,'reviewer':'Synthetic','confirmed':True})
            corrected=reading(fresh).state()
            self.assertEqual(corrected['words'][0]['person'],'SYN-B')
            self.assertEqual(corrected['words'][0]['speaker_label'],'P2')
            self.assertEqual(corrected['words'][-1]['speaker_label'],'P1')

    def test_finish_requires_confirmation_and_receipt_file_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp),True);editor=reading(session);editor.state()
            with self.assertRaises(ValueError):editor.finish({'revision':0,'reviewer':'Synthetic','confirmed':False})
            result=editor.finish({'revision':0,'reviewer':'Synthetic','confirmed':True});self.assertTrue(editor.is_approved())
            self.assertEqual([s['speaker'] for s in result['transcript']['segments']],['A','A','B'])
            self.assertEqual(result['transcript']['segments'][-1]['start'],3)
            self.assertFalse(result['transcript']['person_mapping_confirmed'])
            (session.output.parent/result['filename']).write_text('{}')
            self.assertFalse(editor.is_approved())

    def test_temporary_empty_draft_can_be_saved_and_retyped_but_not_approved(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp));editor=reading(session);project=editor.state()['project']
            empty={**project,'text':''};saved=editor.save({'project':empty,'revision':0,'mutation_id':'clear'})
            self.assertEqual(saved['words'],[])
            with self.assertRaises(ValueError):editor.finish({'revision':1,'reviewer':'Synthetic','confirmed':True})
            restored=editor.save({'project':{**project,'text':'Hallo neu'},'revision':1,'mutation_id':'retype'})
            self.assertEqual(restored['revision'],2)

    def test_upload_rechecks_approval_and_persists_next_recording(self):
        with tempfile.TemporaryDirectory() as temp:
            session,_=fixture(Path(temp));editor=reading(session);state=editor.state();editor.finish({'revision':0,'reviewer':'Synthetic','confirmed':True})
            workflow=ReadingWorkflow(session,Session);data=session.audio.read_bytes()
            headers={'X-Workspace-Id':workspace(session),'X-Reading-Revision':'0','Content-Length':str(len(data)),'X-Audio-Name':'next.wav','X-Expected-Speakers':'5'}
            handler=SimpleNamespace(headers=headers,connection=SimpleNamespace(settimeout=lambda _:None),rfile=io.BytesIO(data))
            original_read=handler.rfile.read
            def changed_read(n):
                if editor.store.get()['revision']==0:editor.save({'project':{**state['project'],'text':'Changed during upload'},'revision':0,'mutation_id':'during-upload'})
                return original_read(n)
            handler.rfile=SimpleNamespace(read=changed_read)
            with patch('reading_workflow.subprocess.Popen') as start:
                with self.assertRaises(ValueError):workflow.upload(handler)
                start.assert_not_called()
            self.assertIs(workflow.session,session);self.assertFalse(workflow.uploading)
            editor.finish({'revision':1,'reviewer':'Synthetic','confirmed':True});headers['X-Reading-Revision']='1';handler.rfile=io.BytesIO(data)
            with patch('reading_workflow.subprocess.Popen',return_value=SimpleNamespace(poll=lambda:None)):
                workflow.upload(handler)
            self.assertNotEqual(workflow.session.output,session.output)
            reopened=ReadingWorkflow(session,Session)
            self.assertEqual(reopened.session.output,workflow.session.output)
            self.assertEqual(reopened.state()['expected_speakers'],5)
            self.assertIn('höchstens vier',reopened.state()['speaker_count_note'])
            with self.assertRaises(ValueError):workflow.upload(handler)


if __name__=='__main__':unittest.main()
