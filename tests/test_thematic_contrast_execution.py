"""Contrast contexts keep global/case denominators and polarities distinct."""
import copy
import json
import unittest
from unittest.mock import patch

from thematic_execution import execute_perspective, perspective_markdown
from thematic_interpretation import interpret_counts
from runtime_context import ContextBudgetError
from test_thematic_execution import SyntheticBackend
from test_thematic_contrast_adapter import contrast_fixture


class ContrastExecutionTests(unittest.TestCase):
    def setUp(self):
        self.params = {'model': 'synthetic', 'num_ctx': 32768, 'max_tokens': 1500,
                       'parallel_workers': 1, 'partial_checkpoints': False}
        for name in ('analysis_work.update_progress', 'runtime_context.update_progress',
                     'thematic_interpretation.begin_phase'):
            handle=patch(name);handle.start();self.addCleanup(handle.stop)

    def run_fixture(self, count=2, mode='both'):
        material,persons,comparison,payload=contrast_fixture(count)
        requests=[]
        class Backend(SyntheticBackend):
            def __call__(self, messages, params):
                request,_=json.JSONDecoder().raw_decode(messages[1]['content'])
                if 'cells' not in request: requests.append(request)
                return super().__call__(messages,params)
        result=execute_perspective('contrast_analysis',mode,material,payload,self.params,
            person_payload=persons,comparison_payload=comparison,llm=Backend())
        return material,persons,comparison,payload,result,requests

    def test_twelve_people_and_rare_case_use_complete_separate_registers(self):
        material,persons,comparison,payload,result,requests=self.run_fixture(12)
        links=result['source_links']; topics=result['counting']['topics']
        global_ids={tid for tid,link in links.items() if link['scope_kind']=='global_pattern'}
        self.assertTrue(global_ids); self.assertTrue(set(links)-global_ids)
        for request in requests:
            tid=request['topic']['topic_id'];link=links[tid]
            ids={row['topic_id'] for row in request['comparison_register']}
            if tid in global_ids:
                self.assertEqual(request['comparison_scope'],'global_patterns')
                self.assertEqual(ids,global_ids)
                self.assertTrue(all(row['scope']['person_count']==12 for row in request['comparison_register']))
                expected=set(link['countercase_topic_ids'])
            else:
                self.assertEqual(request['comparison_scope'],'same_person_countercases')
                self.assertEqual(ids,{key for key,value in links.items() if value.get('person')==link['person']
                    and value['scope_kind']=='individual_countercase'})
                self.assertTrue(all(row['scope']['person_count']==1 for row in request['comparison_register']))
                expected={link['pattern_topic_id']}
            self.assertEqual({row['topic_id'] for row in request['reference_context']},expected)
            self.assertTrue(all('counts' not in row for row in request['reference_context']))
            self.assertEqual(request['comparison_topic_count'],len(ids))
            self.assertEqual(request['module_topic_count'],len(links))
        # Positive support of a deviation is not automatically opposing support
        # of a global pattern. Both matrices receive their own model decisions.
        for topic in topics:
            self.assertEqual(topic['counts']['opposing']['exact_person_count'],0)
            self.assertEqual(topic['counts']['supporting']['exact_person_count'],topic['scope']['person_count'])
        self.assertIn('Verknüpfte qualitative Befunde',perspective_markdown(result))

    def test_one_person_study_still_distinguishes_global_pattern_from_case(self):
        *_,result,requests=self.run_fixture(1)
        self.assertEqual({r['comparison_scope'] for r in requests},{'global_patterns','same_person_countercases'})
        self.assertEqual({t['scope']['person_count'] for t in result['counting']['topics']},{1})

    def test_identically_labeled_patterns_and_countercases_keep_full_distinct_definitions(self):
        for duplicate_kind in ('pattern', 'case'):
            material,persons,comparison,payload=contrast_fixture()
            if duplicate_kind=='pattern':
                payload['dominante_muster'].append({**payload['dominante_muster'][0],
                    'beschreibung':'Anders definierte Nutzung planbarer Zeiten.'})
            else:
                payload['negativfaelle'].append({**payload['negativfaelle'][0],
                    'abweichung':'Eine andere, vollständige Abweichung von Planbarkeit.'})
            requests=[]
            class Backend(SyntheticBackend):
                def __call__(self,messages,params):
                    request,_=json.JSONDecoder().raw_decode(messages[1]['content'])
                    if 'cells' not in request:requests.append(request)
                    return super().__call__(messages,params)
            result=execute_perspective('contrast_analysis','both',material,payload,self.params,
                person_payload=persons,comparison_payload=comparison,llm=Backend())
            definitions={t['topic_id']:t['definition'] for t in result['counting']['definitions']}
            multi=[r for r in requests if len(r['comparison_register'])==2]
            self.assertTrue(multi)
            for request in multi:
                register=request['comparison_register']
                self.assertEqual(len({r['label'] for r in register}),1)
                self.assertEqual(len({r['definition'] for r in register}),2)
                self.assertTrue(all(r['definition']==definitions[r['topic_id']] for r in register))
            if duplicate_kind=='pattern':
                self.assertIn('Mehrere verschiedene Musterdefinitionen',perspective_markdown(result))

    def test_unresolved_countercase_is_visible_in_markdown_without_fabricated_counts(self):
        material,persons,comparison,payload=contrast_fixture()
        payload['dominante_muster']=[]
        payload['negativfaelle'][0]['bezugs_muster']='<script>synthetic()</script>'
        llm=SyntheticBackend()
        result=execute_perspective('contrast_analysis','both',material,payload,self.params,
            person_payload=persons,comparison_payload=comparison,llm=llm)
        text=perspective_markdown(result)
        self.assertIn('Nicht thematisch gezählte Befunde',text)
        self.assertIn('Bezugsmuster nicht eindeutig',text)
        self.assertNotIn('<script>',text)
        self.assertIn('Spontane Gestaltung',text)
        self.assertEqual(result['counting']['topics'],[])
        self.assertEqual(llm.assignment_calls+llm.interpretation_calls,0)

    def test_malformed_roles_scopes_and_pattern_links_fail_before_interpretation(self):
        material,*_,result,_=self.run_fixture()
        original=result['source_links']; counted=result['counting']
        case=next(tid for tid,link in original.items() if link['scope_kind']=='individual_countercase')
        global_id=next(tid for tid,link in original.items() if link['scope_kind']=='global_pattern')
        for change in ('role','person','reference','reciprocal','missing'):
            links=copy.deepcopy(original)
            if change=='role':links[case]['scope_kind']='global_pattern'
            if change=='person':links[case]['person']='not-confirmed'
            if change=='reference':links[case]['pattern_topic_id']=case
            if change=='reciprocal':links[global_id]['countercase_topic_ids']=['missing']
            if change=='missing':links.pop(case)
            llm=SyntheticBackend()
            with self.subTest(change=change),self.assertRaises(ValueError):
                interpret_counts(material,counted,{tid:link['qualitative_text'] for tid,link in original.items()},
                    self.params,module='contrast_analysis',llm=llm,source_links=links)
            self.assertEqual(llm.interpretation_calls,0)

    def test_both_and_frequency_share_counts_and_leave_original_payloads_unchanged(self):
        material,persons,comparison,payload=contrast_fixture()
        before=copy.deepcopy((material,persons,comparison,payload)); results=[]
        for mode in ('both','frequency'):
            results.append(execute_perspective('contrast_analysis',mode,material,payload,self.params,
                person_payload=persons,comparison_payload=comparison,llm=SyntheticBackend()))
        self.assertEqual(results[0]['counting'],results[1]['counting'])
        self.assertEqual(before,(material,persons,comparison,payload))

    def test_long_complete_pattern_fails_before_calls_instead_of_shortening(self):
        material,persons,comparison,payload=contrast_fixture()
        payload['dominante_muster'][0]['beschreibung']='Vollständiger Befund. '*5000
        llm=SyntheticBackend()
        with self.assertRaises(ContextBudgetError):
            execute_perspective('contrast_analysis','both',material,payload,self.params,
                person_payload=persons,comparison_payload=comparison,llm=llm)
        self.assertEqual(llm.assignment_calls+llm.interpretation_calls,0)


if __name__=='__main__':unittest.main()
