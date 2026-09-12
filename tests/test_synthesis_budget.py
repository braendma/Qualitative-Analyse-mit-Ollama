import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hierarchical_synthesis import reduce_sources,SynthesisCallBudgetError
from failure_help import failure_help


class SynthesisBudgetTests(unittest.TestCase):
    def test_first_round_is_rejected_before_any_model_call(self):
        sources={'A':{'items':[{'text':str(i)+'x'*100} for i in range(10)]}}
        params={'num_ctx':20000,'max_tokens':1000,'hierarchical_synthesis':{
            'force':True,'batch_items':2,'max_calls':4}}
        with self.assertRaisesRegex(SynthesisCallBudgetError,'mindestens 5 Teilaufgaben, 4 Aufrufe übrig'):
            reduce_sources(sources,lambda x:('final',json.dumps(x)),params,lambda *_:self.fail('No LLM call allowed'))

    def test_next_round_rechecks_remaining_budget(self):
        sources={'A':{'items':[{'text':str(i)+'x'*600} for i in range(4)]}}
        params={'num_ctx':5000,'max_tokens':100,'hierarchical_synthesis':{
            'force':True,'batch_items':2,'max_calls':2,'summary_chars':1000}}
        def final(payload):
            if payload.get('teilanalysen'):return 'final','x'*6000
            return 'final',json.dumps(payload)
        calls=[]
        def llm(*_):calls.append(1);return json.dumps({'summary':'y'*900})
        with self.assertRaisesRegex(SynthesisCallBudgetError,'Verdichtungsebene 2.*mindestens 1 Teilaufgaben, 0 Aufrufe übrig'):
            reduce_sources(sources,final,params,llm)
        self.assertEqual(len(calls),2)

    def test_budget_help_is_distinct_from_context_and_keeps_only_numeric_details(self):
        for error in ('SynthesisCallBudgetError: mindestens 112 Teilaufgaben, 64 Aufrufe übrig',
                      'llm_client.ContextBudgetError: Hierarchische Synthese erreicht max_calls.'):
            help=failure_help(error+' SECRET /private/study')
            self.assertEqual(help['kind'],'call_budget')
            self.assertIn('max_calls',help['action'])
            self.assertNotIn('SECRET',str(help));self.assertNotIn('/private/study',str(help))
        self.assertIn('112',failure_help('Synthese-Aufrufbudget: mindestens 112 Teilaufgaben, 64 Aufrufe übrig')['cause'])


if __name__=='__main__':unittest.main()
