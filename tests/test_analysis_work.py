import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from analysis_work import analyze_items
from llm_client import ContextBudgetError, LLMError, request_chat
from person_analysis_core import compact_person_payload, build_person_analysis, build_person_payloads
from swot_core import build_swot
import progress_events


PARAMS = {'model': 'synthetic', 'provider': 'ollama_local', 'temperature': 0,
          'num_ctx': 32768, 'max_tokens': 1024, 'parallel_workers': 2}


def items(n):
    return [{'key': str(i), 'system': 'Analyse', 'user': 'Künstlicher Text',
             'texts': {str(i): 'Beleg'}} for i in range(n)]


class AnalysisWorkTests(unittest.TestCase):
    def test_failure_visible_before_slow_peer_finishes_and_resume_reuses_peer(self):
        barrier = threading.Barrier(2)
        reported = threading.Event()
        release = threading.Event()
        calls = []
        def compute(item):
            calls.append(item['key'])
            barrier.wait(timeout=5)
            if item['key'] == '0':
                raise ValueError('PRIVATE_TEXT_MUST_NOT_REACH_PROGRESS')
            if not release.wait(5): raise TimeoutError('test release missing')
            return {'value': item['key']}
        original = progress_events.update_progress
        def update(**values):
            original(**values)
            if values.get('failed'): reported.set()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'progress.json'
            params = {**PARAMS, 'partial_checkpoint_dir': str(Path(tmp) / 'cache')}
            with patch.dict(os.environ, WORKFLOW_PROGRESS_FILE=str(path), WORKFLOW_MODULE='swot'), \
                 patch('analysis_work.update_progress', update), ThreadPoolExecutor(1) as pool:
                future = pool.submit(analyze_items, items(5), compute, params, 'swot', 'categories')
                try:
                    self.assertTrue(reported.wait(5))
                    self.assertFalse(future.done(), 'Failure must be visible while peer is active')
                    self.assertEqual(json.loads(path.read_text())['failed'], 1)
                    self.assertNotIn('PRIVATE_TEXT', path.read_text())
                finally:
                    release.set()
                with self.assertRaises(ValueError): future.result(timeout=5)
                self.assertEqual(set(calls), {'0', '1'})
                resumed_calls = []
                def resume(item):
                    resumed_calls.append(item['key'])
                    return {'value': item['key']}
                out = analyze_items(items(5), resume, params, 'swot', 'categories')
                self.assertEqual([r['value'] for r in out], ['0','1','2','3','4'])
                self.assertNotIn('1', resumed_calls)
                detail = json.loads(path.read_text())
                self.assertEqual((detail['completed'], detail['reused'], detail['failed']), (5,1,0))

    def test_later_oversized_item_blocks_all_new_inference(self):
        work = items(2)
        work[1]['user'] = 'ü' * 20000
        calls = []
        params = copy.deepcopy(PARAMS)
        with self.assertRaises(ContextBudgetError):
            analyze_items(work, lambda i: calls.append(i), params, 'swot', 'categories')
        self.assertEqual(calls, [])
        self.assertEqual(params, PARAMS, 'Context must not silently expand runtime memory')

    def test_transport_guard_checks_actual_answer_budget_before_network(self):
        from unittest.mock import Mock
        backend = Mock()
        request = {'model':'synthetic','messages':[{'content':'x'*100}],
                   'options':{'num_predict':32768}}
        with self.assertRaises(LLMError): request_chat(backend, request, PARAMS)
        backend.Client.assert_not_called()

    def test_duplicate_keys_cannot_race_on_same_checkpoint(self):
        with self.assertRaisesRegex(ValueError, 'eindeutige'):
            analyze_items([items(1)[0]] * 2, lambda i: self.fail(), PARAMS, 'swot', 'categories')

    def test_shared_contexts_expand_losslessly_without_merging_distinct_codes(self):
        first = {'hauptkategorie':'A','cluster_name':'Gleich','definition':'Definition '*80,
                 'summary':'Zusammenfassung '*80}
        other = {**first, 'hauptkategorie':'B'}
        source = {'person':'P', 'segments':[
            {'id':f'P#SEG{i}', 'text':f'Ungekürztes Zitat {i}',
             'cluster_contexts':[first,other] if i%2 else [first]} for i in range(20)]}
        before = copy.deepcopy(source)
        compact = compact_person_payload(source)
        self.assertEqual(source, before)
        expanded = {'person':compact['person'], 'segments':[
            {**{k:v for k,v in s.items() if k!='cluster_context_ids'},
             'cluster_contexts':[compact['cluster_contexts'][key] for key in s['cluster_context_ids']]}
            for s in compact['segments']]}
        self.assertEqual(expanded, source)
        self.assertEqual(len(compact['cluster_contexts']), 2)
        self.assertLess(len(json.dumps(compact)), len(json.dumps(source))/3)

    def test_contexts_with_different_third_level_remain_distinct(self):
        base={'hauptkategorie':'K','subkategorie':'U','facette':'F','cluster_name':'Gleich',
              'segments':['P#SEG1']}
        payload=build_person_payloads([{**base,'auspraegung':'A'}, {**base,'auspraegung':'B'}],
                                     {'P#SEG1':'Original'}, {})['P']
        compact=compact_person_payload(payload)
        self.assertEqual({c['auspraegung'] for c in compact['cluster_contexts'].values()}, {'A','B'})
        self.assertEqual(len(compact['segments'][0]['cluster_context_ids']),2)

    def test_real_analysis_assembly_parallel_matches_serial_and_preserves_evidence(self):
        texts = {f'P{i}#SEG1':f'Unverändertes Zitat {i}' for i in range(4)}
        clusters = [{'hauptkategorie':f'K{i//2}', 'subkategorie':'U', 'auspraegung':'A',
                     'facette':'F', 'cluster_name':f'Cluster{i}', 'segments':[sid]}
                    for i,sid in enumerate(texts)]
        prompts = {'swot_analysis':{'system':'swot','user':'{clusters}'},
                   'person_analysis':{'system':'person','user':'{persons}'}}
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for name,data in [('clusters',{'clusters':clusters}),('texts',texts),('summary',{})]:
                p=Path(tmp)/(name+'.json');p.write_text(json.dumps(data),encoding='utf-8');paths.append(str(p))
            for module, builder, section in [('swot_core',build_swot,'swot'),
                                              ('person_analysis_core',build_person_analysis,'persons')]:
                def execute(count):
                    barrier=threading.Barrier(count)
                    def fake(system,user,params):
                        barrier.wait(timeout=5)
                        payload=json.loads(user)
                        if section=='swot':
                            ids=[s['id'] for c in payload['clusters'] for s in c['segments']]
                            return json.dumps({'Stärken':[{'thema':'T','analyse':'A','segment_ids':ids}],
                                               'Schwächen':[],'Chancen':[],'Risiken':[]})
                        ids=[s['id'] for s in payload['segments']]
                        self.assertTrue(all(s['cluster_context_ids'] for s in payload['segments']))
                        return json.dumps({'zentrale_themen':[{'thema':'T','verdichtung':'A','segment_ids':ids}],
                                           'perspektiven':[],'spannungsfelder':[],
                                           'kontrastierende_aspekte':[],'gesamtverdichtung':'A'})
                    method='llm_swot' if section=='swot' else 'llm_person_analysis'
                    with patch(module+'.'+method, fake):
                        return builder(*paths,{**PARAMS,'parallel_workers':count,'partial_checkpoints':False},prompts,{})[1][section]
                serial,parallel=execute(1),execute(2)
                self.assertEqual(list(serial),list(parallel))
                self.assertEqual(serial,parallel)
                for text in texts.values(): self.assertIn(text,json.dumps(parallel,ensure_ascii=False))


if __name__=='__main__': unittest.main()
