"""Full stored synthetic ASR/speaker packet through human-review and CSV contracts."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

import llm_review as review
from speaker_review import make_draft,source_words,original_text,validate_draft,finish
from workspace_store import ProjectStore
from verify_coding_export import verify

ROOT=Path(__file__).resolve().parent


class SpeakerExportTests(unittest.TestCase):
    def test_full_source_partition_person_gates_and_coding_export(self):
        packet=review.read(ROOT/'diarization_tests/v2/EINZEL_P01_clean/speaker_suggestions.json')
        original=copy.deepcopy(packet);words=source_words(packet);draft=make_draft(packet)
        with self.assertRaises(ValueError):finish(packet,draft,'SYN-FUNCTIONAL',True)
        for group in draft['groups']:
            group.update(speaker=group['speaker'] or 'SYN-REVIEWED',person='SYN-P01')
        draft['groups'][0].update(speaker=None,person='',exclude=True)
        with self.assertRaises(ValueError):finish(packet,draft,'SYN-FUNCTIONAL',False)
        group=next(g for g in draft['groups'][1:] if g['last']-g['first']>=4)
        index=draft['groups'].index(group);middle=group['first']+2
        draft['groups'][index:index+1]=[{**group,'last':middle,'text':original_text(words,group['first'],middle)},
            {**group,'id':str(uuid.uuid4()),'first':middle,'text':original_text(words,middle,group['last']),'person':'SYN-P02'}]
        chosen=draft['groups'][index];chosen['text']='🙂 Synthetisch; "ja"\nTestkorrektur'
        draft['groups'][0]['text']='EXCLUDED_INTERVIEWER_ONLY'
        validate_draft(packet,draft)
        result=finish(packet,draft,'SYN-FUNCTIONAL',True)
        transcript=result['transcript'];project=result['project'];document=project['documents'][0]
        review.confirmed(transcript)
        self.assertEqual(packet,original)
        self.assertEqual(sum(g['last']-g['first'] for g in draft['groups']),len(words))
        self.assertEqual(len(document['segments']),len(draft['groups']))
        self.assertEqual(transcript['speaker_review_source_sha256'],review.fingerprint(packet))
        self.assertEqual(document['transcript_sha256'],review.fingerprint(transcript))
        self.assertEqual(transcript['review']['person_assignments_sha256'],review.fingerprint(transcript['person_assignments']))
        for segment,group in zip(document['segments'],draft['groups']):
            self.assertEqual((segment['text'],segment['person'],segment['exclude']),(group['text'],group['person'],group['exclude']))
            selected=words[group['first']:group['last']]
            self.assertEqual((segment['start'],segment['end']),(min(w['start'] for w in selected),max(w['end'] for w in selected)))
        project['categories']=[{'id':f'C{i}','code':f'SYN-Test > Code {i}','definition':'Synthetischer Funktionstest','inclusion':'','exclusion':'','anchors':''} for i in (1,2)]
        for position,category in [(index,'C1'),(index,'C2'),(index+1,'C1'),(0,'C1')]:
            segment=document['segments'][position]
            project['annotations'].append({'id':str(uuid.uuid4()),'document_id':document['id'],'segment_id':segment['id'],'start':0,'end':len(segment['text']),'quote':segment['text'],'category_id':category,'origin':'manual','memo':'Kontrollierter Test, kein Browsernachweis'})
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);input_path=folder/'project.json';input_path.write_text(json.dumps(project),encoding='utf-8')
            script="const fs=require('fs'),C=require('../../src/preparation/coding_core');const p=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));const out=C.exportsFor(p);fs.writeFileSync(process.argv[2]+'/Kategoriesystem.csv',out.categories);fs.writeFileSync(process.argv[2]+'/maxqda_export.csv',out.segments);"
            subprocess.run(['node','-e',script,str(input_path),str(folder)],cwd=ROOT,check=True,capture_output=True)
            report=verify(project,folder/'Kategoriesystem.csv',folder/'maxqda_export.csv')
            self.assertEqual((report['rows'],report['categories'],report['passages']),(3,2,2))
            self.assertEqual(report['people'],['SYN-P01','SYN-P02'])
            self.assertNotIn('EXCLUDED_INTERVIEWER_ONLY',(folder/'Kategoriesystem.csv').read_text(encoding='utf-8-sig'))
            self.assertEqual(len(project['annotations']),4)

    def test_speaker_store_write_failure_and_retry_keep_original(self):
        packet=review.read(ROOT/'diarization_tests/v2/EINZEL_P01_clean/speaker_suggestions.json');draft=make_draft(packet)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'speaker.json';store=ProjectStore(path,validator=lambda d:validate_draft(packet,d),initial=draft)
            store.save(draft,0,'initial');before=path.read_bytes()
            changed=copy.deepcopy(draft);changed['groups'][0]['text']='SYN fehlgeschlagen, später erneut gespeichert'
            with patch('workspace_store.os.replace',side_effect=OSError('synthetic disk failure')):
                with self.assertRaises(OSError):store.save(changed,1,'retry')
            self.assertEqual(store.get()['project'],draft);self.assertEqual(path.read_bytes(),before)
            store.save(changed,1,'retry')
            restored=ProjectStore(path,validator=lambda d:validate_draft(packet,d),initial=draft)
            self.assertEqual(restored.get()['project'],changed)
            with self.assertRaises(ValueError):restored.save(draft,1,'stale')
            self.assertEqual(restored.get()['project'],changed)


if __name__=='__main__':unittest.main()
