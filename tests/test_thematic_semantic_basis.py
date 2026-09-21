"""Metric basis guards and checkpoint revalidation with synthetic material."""
import copy
import json
import unittest
from unittest.mock import patch
import thematic_interpretation as m
from thematic_counts import count_topics
from test_thematic_counts import material, topic, assignment

class SemanticBasisTests(unittest.TestCase):
    def setUp(self):
        self.material = material(['P1', 'P1', 'P2', 'P3'])
        self.counted = count_topics(self.material, [topic('T', list(self.material['units']))],
            [assignment('T', uid, 'supported' if uid != 'u3' else 'opposed') for uid in self.material['units']])
        self.row = m._summary(self.counted['topics'][0])
        self.good = dict(topic_id='T', interpretation='Synthetischer Befund.', counterpositions='Gegenposition erhalten.',
            limitations='Viele Aussagen einer Person entsprechen nicht vielen Personen.', basis_check=m.target_basis(self.row))

    def test_legitimate_single_person_caveat(self):
        self.assertNotIn('basis_check', m.validate_compact_basis(self.good, self.row))

    def test_wrong_single_person_scope(self):
        bad = copy.deepcopy(self.good)
        bad['interpretation'] = 'Die Bezugsmenge umfasst nur eine Person.'
        with self.assertRaises(ValueError): m.validate_compact_basis(bad, self.row)

    def test_wrong_basis_type_and_value(self):
        for key, value in [('persons', 1), ('persons', True), ('units', 3)]:
            with self.subTest(key=key, value=value):
                bad = copy.deepcopy(self.good)
                bad['basis_check']['scope'][key] = value
                with self.assertRaises(ValueError): m.validate_compact_basis(bad, self.row)

    def test_wrong_named_unit_share(self):
        bad = copy.deepcopy(self.good)
        bad['interpretation'] = 'unit_share_in_scope=0.66'
        with self.assertRaises(ValueError): m.validate_compact_basis(bad, self.row)

    def test_share_zero_integer_spelling_is_equivalent_but_boolean_is_not(self):
        good = copy.deepcopy(self.good)
        for stance in good['basis_check']['stances'].values():
            for kind in ('persons','units'):
                if stance[kind]['share'] == 0.0: stance[kind]['share'] = 0
        m.validate_compact_basis(good, self.row)
        bad = copy.deepcopy(good)
        bad['basis_check']['stances']['supporting']['persons']['share'] = True
        with self.assertRaises(ValueError):m.validate_compact_basis(bad, self.row)

    def test_actual_genitive_single_scope_contradiction_rejected(self):
        bad=copy.deepcopy(self.good)
        bad['limitations']='Die Grenzen resultieren aus der Bezugsmenge einer einzigen Person im scope (n=3 Personen).'
        with self.assertRaises(ValueError):m.validate_compact_basis(bad,self.row)

    def test_changed_numeric_values_null_and_count_types_still_rejected(self):
        for actual in (True, None, '0', 0.1):
            self.assertFalse(m._same_basis(0.0, actual))
        self.assertFalse(m._same_basis(1,1.0))
        self.assertFalse(m._same_basis(False,0))
        self.assertFalse(m._same_basis(None,0))
        self.assertTrue(m._same_basis(0.0,0))

    def compact_prompt(self, payload, params):
        own = next(row for row in payload['comparison_register'] if row['topic_id']=='T')
        return 'CPU compact protocol fixture', json.dumps({**payload, 'target_basis':m.target_basis(own)})

    def run_interpret(self, llm):
        return m.interpret_counts(self.material, self.counted, {'T':'Originaler Befund'},
            {'num_ctx':57344,'max_tokens':8192,'partial_checkpoints':False}, module='swot', llm=llm)

    def test_repair_then_persist_full_basis_and_strip_public_field(self):
        bad = copy.deepcopy(self.good); bad['basis_check']['scope']['persons']=1
        replies = [bad, self.good]; calls=[]; stored=[]
        def llm(messages, params):
            calls.append(messages)
            self.assertIn('basis_check', params['response_schema']['required'])
            for field in ('interpretation','counterpositions','limitations'):
                self.assertEqual(params['response_schema']['properties'][field]['minLength'],1)
                self.assertEqual(params['response_schema']['properties'][field]['pattern'],r'\S')
            return json.dumps(replies.pop(0))
        def checkpoint(items, compute, params, module, unit):
            stored.extend(compute(item) for item in items)
            return stored
        with patch.object(m, '_interpretation_prompt', self.compact_prompt), patch.object(m, 'analyze_items', checkpoint):
            result=self.run_interpret(llm)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1][-1]['content'],m.COMPACT_CORRECTION)
        self.assertEqual(stored[0]['basis_check'],self.good['basis_check'])
        self.assertNotIn('basis_check',result[0])

    def test_cached_invalid_basis_rejected_without_llm(self):
        bad=copy.deepcopy(self.good); bad['basis_check']['scope']['units']=1
        with patch.object(m,'_interpretation_prompt',self.compact_prompt), patch.object(m,'analyze_items',return_value=[bad]):
            with self.assertRaises(ValueError): self.run_interpret(lambda *args:self.fail('Cache test called model'))

if __name__=='__main__': unittest.main()
