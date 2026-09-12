import json,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from comparison_reduction import prepare_people
from runtime_support import fingerprint
from summary_reduction import reduce_prompt

class ComparisonReductionTests(unittest.TestCase):
    def test_complete_comparison_keeps_people_and_reports_reduction(self):
        from person_comparison_core import build_person_comparison
        people={f'P{i}':{'person':f'P{i}','text':'Beleg und Gegenbeleg '*6000} for i in range(3)}
        def final(system,user,params):
            data=json.loads(user)
            self.assertEqual([p['person'] for p in data['personen']],sorted(people))
            self.assertEqual(params['max_tokens'],6000)
            self.assertEqual(params['num_ctx'],16384)
            return json.dumps({'gemeinsame_muster':[],'zentrale_unterschiede':[],
                'typen':[],'nicht_zugeordnete_personen':[],'gesamtvergleich':'Künstliches Ergebnis'})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'persons.json';path.write_text(json.dumps({'persons':people}),encoding='utf-8')
            with patch('summarizer_core.llm_summary',return_value='Verdichtung mit Gegenbelegen.'), \
                 patch('person_comparison_core.llm_person_comparison',side_effect=final):
                md,result=build_person_comparison(str(path),{'num_ctx':16384,'max_tokens':6000,
                    'parallel_workers':2,'partial_checkpoints':False},
                    {'person_comparison':{'system':'Vergleiche','user':'{persons}'}},{})
            self.assertTrue(result['input_reduction']['used'])
            self.assertIn('Methodischer Hinweis',md)
            self.assertEqual(result['source_persons'],sorted(people))

    def test_small_payload_unchanged(self):
        people={'P1':{'person':'P1','text':'Beleg'}}
        payload,ledger=prepare_people(people,lambda p:('Analyse',json.dumps(p)),
            {'num_ctx':8192,'max_tokens':1024},lambda *a:self.fail('Unneeded inference'))
        self.assertEqual(payload,{'personen':list(people.values())});self.assertFalse(ledger['used'])

    def test_all_persons_full_inputs_covered_and_cached(self):
        people={f'P{i}':{'person':f'P{i}','text':(('MARKER'+str(i)+' ') * 12000)} for i in range(3)}
        seen=[]
        def summarize(s,u,p):
            seen.append(u)
            return 'Unterschiede, Gegenbeispiele und Unsicherheit bleiben zu prüfen.'
        build=lambda p:('Vergleiche ausschließlich die Personen.',json.dumps(p,ensure_ascii=False,indent=2))
        with tempfile.TemporaryDirectory() as tmp:
            params={'num_ctx':16384,'max_tokens':6000,'parallel_workers':2,'partial_checkpoint_dir':tmp}
            payload,ledger=prepare_people(people,build,params,summarize)
            self.assertEqual([x['person'] for x in payload['personen']],sorted(people))
            for name in people:
                self.assertEqual(ledger['sources'][name]['source_sha256'],fingerprint(people[name]))
            # Every original text marker goes into first-level chunks. Markers may
            # cross chunk boundaries; concatenation per marker is not relied on.
            for i in range(3):self.assertGreater(sum(u.count('MARKER'+str(i)) for u in seen),11980)
            self.assertLess(len(build(payload)[1].encode())+6000+1024,16384)
            again,_=prepare_people(people,build,params,lambda *a:self.fail('Repeated inference'))
            self.assertEqual(again,payload)
            self.assertEqual(ledger['source_sha256'],fingerprint(people))

    def test_no_room_for_distinct_people_fails_before_inference(self):
        people={f'P{i}':{'person':f'P{i}','text':'x'*1000} for i in range(100)}
        with self.assertRaisesRegex(ValueError,'alle Personen'):
            prepare_people(people,lambda p:('system',json.dumps(p)),
                {'num_ctx':8192,'max_tokens':6000},lambda *a:self.fail())

    def test_reduction_does_not_truncate_when_model_cannot_shrink(self):
        with self.assertRaises(ValueError):
            reduce_prompt('system','x'*40000,{'num_ctx':16384,'max_tokens':6000},
                          lambda s,u,p:u,target_bytes=1200)

    def test_unicode_target_is_measured_in_bytes(self):
        out=reduce_prompt('system','ü'*12000,{'num_ctx':16384,'max_tokens':6000},
                          lambda s,u,p:'ä'*100,target_bytes=256)
        self.assertEqual(len(out.encode()),200)

if __name__=='__main__':unittest.main()
