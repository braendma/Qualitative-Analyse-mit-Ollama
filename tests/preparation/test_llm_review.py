import copy
import json
from pathlib import Path
import tempfile
import unittest
import llm_review as m


RAW = {'segments': [{'id': 1, 'start': 0., 'end': 3., 'text': 'Ich arbeite gern mit Jugendlichen.', 'speaker': None}]}
CAT = {'id': 'C1', 'code': 'Motivation > Jugendliche', 'definition': 'Freude an der Arbeit mit Jugendlichen.', 'inclusion': 'Ausdrückliche Freude.', 'exclusion': 'Nur fachliche Interessen.', 'reason': 'Explizit genannt.', 'evidence': [{'segment_id': '1', 'quote': 'gern mit Jugendlichen'}]}


def packet(mode='categories', answer=None, book=None):
    transcript = m.approve_transcript(RAW, 'synthetic_test')
    task = m.prepare(transcript, mode, book=book)
    answer = answer or {'suggestions': [copy.deepcopy(CAT)]}
    p = {'kind': 'review_packet', 'task': task, 'answer': answer, 'generation': 'synthetic_fixture'}
    p['packet_sha256'] = m.fingerprint(p)
    return p


def decide(p, decision='accept', changes=None):
    return {'packet_sha256': p['packet_sha256'], 'decisions': [{'id': x['id'], 'decision': decision, 'changes': changes or {}} for x in p['answer']['suggestions']]}


class ReviewTests(unittest.TestCase):
    def test_json_fence_accepted_but_surrounding_prose_rejected(self):
        for value in ['{"suggestions": []}', '```json\n{"suggestions": []}\n```']:
            self.assertEqual(m.parse_answer(value), {'suggestions': []})
        for value in ['Vorwort {"suggestions": []}', '{"suggestions": []} Nachwort', '```json\n{}\n```\n```json\n{}\n```']:
            with self.assertRaises(ValueError): m.parse_answer(value)

    def test_raw_and_modified_transcripts_block_categories(self):
        with self.assertRaisesRegex(ValueError, 'bestätigen'):
            m.prepare(RAW, 'categories')
        confirmed = m.approve_transcript(RAW, 'tester')
        confirmed['segments'][0]['text'] += ' extra'
        with self.assertRaisesRegex(ValueError, 'geändert'):
            m.prepare(confirmed, 'categories')

    def test_hallucinated_quotes_unknown_ids_duplicates_rejected(self):
        p = packet()
        for evidence in [{'segment_id':'1','quote':'nicht gern'}, {'segment_id':'99','quote':'gern'}]:
            a = copy.deepcopy(p['answer']); a['suggestions'][0]['evidence'] = [evidence]
            with self.assertRaises(ValueError): m.validate_suggestions(p['task'], a)
        with self.assertRaisesRegex(ValueError, 'Doppelte'):
            m.validate_suggestions(p['task'], {'suggestions': [CAT, CAT]})

    def test_pending_wrong_binding_and_forged_evidence_not_accepted(self):
        p = packet()
        with self.assertRaisesRegex(ValueError, 'offene'): m.finalize(p, decide(p, 'pending'), 'tester')
        wrong = decide(p); wrong['packet_sha256'] = 'wrong'
        with self.assertRaises(ValueError): m.finalize(p, wrong, 'tester')
        with self.assertRaisesRegex(ValueError, 'Unzulässige'):
            m.finalize(p, decide(p, 'edit', {'evidence': []}), 'tester')

    def test_reviewed_categories_csv_and_coding(self):
        p = packet(); book = m.finalize(p, decide(p), 'tester')
        m.validate_book(book)
        q = packet('coding', {'suggestions': [{'id':'A1','category_id':'C1','reason':'passt','evidence':CAT['evidence']}]}, book)
        result = m.finalize(q, decide(q), 'tester')
        self.assertFalse(result['person_mapping_confirmed'])
        self.assertEqual(result['segments_without_accepted_code'], [])
        q['answer']['suggestions'][0]['category_id'] = 'unknown'
        with self.assertRaises(ValueError): m.validate_suggestions(q['task'], q['answer'])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'book.csv'; m.csv_export(book,path)
            self.assertIn('Einschluss;Ausschluss',path.read_text(encoding='utf-8-sig'))
            with self.assertRaises(FileExistsError): m.csv_export(book,path)

    def test_corrections_preserve_source_and_require_review(self):
        correction = {'id':'E1','segment_id':'1','original':RAW['segments'][0]['text'], 'replacement':'Ich arbeite gern mit Jugendlichen!', 'reason':'Zeichensetzung prüfen'}
        p = packet('corrections', {'suggestions':[correction]})
        out = m.finalize(p,decide(p),'tester')
        self.assertEqual(RAW['segments'][0]['text'],correction['original'])
        self.assertEqual(out['segments'][0]['text'],correction['replacement'])
        self.assertNotIn('words',out['segments'][0]); m.confirmed(out)

    def test_large_input_never_silently_truncated(self):
        raw = copy.deepcopy(RAW); raw['segments'][0]['text'] = 'x'*40000
        with self.assertRaisesRegex(ValueError,'zu groß'):
            m.prepare(m.approve_transcript(raw,'tester'),'categories')

    def test_html_script_injection_escaped(self):
        p = packet();p['answer']['suggestions'][0]['reason']='</script><script>alert(1)</script>'
        p['packet_sha256']=m.fingerprint({k:v for k,v in p.items() if k!='packet_sha256'})
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'review.html';m.render_review(p,path)
            self.assertNotIn('</script><script>alert',path.read_text(encoding='utf-8'))

    def test_remote_model_and_truncated_response_rejected(self):
        task = packet()['task']
        for remote in (True,False):
            calls=[]
            def api(port,endpoint,payload=None):
                calls.append(endpoint)
                if endpoint=='tags': return {'models':[{'name':task['request']['model'],'digest':'a'*64}]}
                if endpoint=='show': return {'remote_host':'https://remote' if remote else '', 'model_info':{'test.context_length':32768}}
                return {'done':True,'done_reason':'length','message':{'content':'{}'}}
            with tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(ValueError): m.run(task,Path(temp)/'out',api=api)
            if remote:self.assertNotIn('chat',calls)


if __name__=='__main__': unittest.main()
