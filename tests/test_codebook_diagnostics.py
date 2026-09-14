import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from coding_validation_common import CodebookEntry, Segment
from coding_agreement_core import calculate_agreement
from codebook_diagnostics_core import analyze_codebook, render_codebook_diagnostics
from review_queue import build_queue


def book(code, definition='Bedeutung', anchor='Konkretes Beispiel'):
    return CodebookEntry(code, code, '', '', '', definition, anchor)


def verify(segments):
    return {'results': [{'segment_id': s.segment_id, 'human_code': s.human_code,
                        'verification': 'bestätigt', 'processing_status': 'completed', 'alternative_codes': []}
                       for s in segments]}


def single(segments, predicted):
    return {'results': [{'segment_id': s.segment_id, 'predicted_code': pred, 'confidence': 'mittel',
                         'begruendung': 'Künstliche Begründung', 'processing_status': 'completed'}
                        for s, pred in zip(segments, predicted)]}


def multi(segments, predictions):
    from multi_label_core import group_units
    units = [{'unit_id': uid, 'segment_ids': [s.segment_id for s in members],
              'predicted_codes': predictions[uid][0], 'assignment_status': predictions[uid][1],
              'confidence': 'mittel', 'begruendung': 'Künstliche Begründung', 'processing_status': 'completed'}
             for uid, members in group_units(segments).items()]
    return {'label_mode': 'multi_label', 'unit_results': units,
            'results': [{**r, 'segment_id': sid} for r in units for sid in r['segment_ids']]}


class CodebookDiagnosticsTests(unittest.TestCase):
    def test_missing_sources_are_unavailable_not_perfect_or_zero(self):
        result=analyze_codebook([Segment('s', 'Text', 'A', 'P')], [book('A'),book('B',anchor='')])
        a,b=result['categories']
        self.assertIsNone(a['predicted_units'])
        self.assertIsNone(a['verification_unklar'])
        self.assertEqual(b['human_units'],0)
        self.assertIn('not_used_in_human_material',b['hints'])
        self.assertIn('no_anchor_example',b['hints'])
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(result['coassignments']['status'],'not_applicable')
        self.assertIsNone(result['coassignments']['pair_events'])
        self.assertNotIn('quality_score',result)
        self.assertIn('nicht verfügbar',render_codebook_diagnostics(result))

    def test_single_none_abstention_and_technical_failures_remain_distinct(self):
        segments=[Segment(str(i),'Text','A','P') for i in range(4)]
        v=verify(segments); b=single(segments,['keine_zuordnung','unklar','unklar','B'])
        b['results'][2]['processing_status']='failed'
        v['results'][3]['processing_status']='invalid_input'
        result=analyze_codebook(segments,[book('A'),book('B')],verification=v,blind=b)
        self.assertEqual(result['processing_status'],'incomplete')
        self.assertEqual(result['blind_unit_states'],{'none':1,'abstained':1,'technical_failure':1,'assigned':1})
        a,bb=result['categories']
        self.assertEqual(a['blind_none_units'],1)
        self.assertEqual(a['blind_abstained_units'],1)
        self.assertEqual(a['comparison_technical_failure_units'],2)
        self.assertEqual(a['verification_technical_rows'],1)
        self.assertEqual(a['verification_unklar'],0)
        self.assertEqual(a['evaluated_human_units'],0)
        self.assertEqual(bb['predicted_units'],1)
        self.assertEqual(result['difference_patterns'],[])

    def test_directional_single_code_differences_use_valid_units(self):
        segments=[Segment('a','Text','A','P'),Segment('b','Text','A','P'),Segment('c','Text','B','Q')]
        b=single(segments,['B','B','A'])
        result=analyze_codebook(segments,[book('A'),book('B')],blind=b)
        self.assertEqual(result['difference_patterns'][0],{'missing_codes':['A'],'additional_codes':['B'],
            'units':2,'case_ids':['row:a','row:b'],'is_single_code_pair':True})
        self.assertIsNone(result['categories'][0]['verification_unklar'])
        self.assertEqual(result['categories'][0]['missing_in_blind'],2)

    def test_multi_label_passages_and_none_use_set_denominators(self):
        segments=[Segment('a','Text','A','P','u1'),Segment('b','Text','B','P','u1'),
                  Segment('c','Andere Stelle','A','Q','u2'),Segment('d','Noch anders','A','Q','u3')]
        b=multi(segments,{'u1':(['A','B'],'assigned'),'u2':([],'none'),'u3':([],'abstained')})
        result=analyze_codebook(segments,[book('A'),book('B')],verification=verify(segments),blind=b,settings={'label_mode':'multi_label'})
        self.assertEqual((result['n_rows'],result['n_units']),(4,3))
        a=result['categories'][0]
        self.assertEqual(a['human_units'],3)
        self.assertEqual(a['evaluated_human_units'],2)
        self.assertEqual(a['missing_in_blind'],1)
        self.assertEqual(a['blind_abstained_units'],1)
        self.assertEqual(result['difference_patterns'][0]['additional_codes'],[])
        self.assertFalse(result['difference_patterns'][0]['is_single_code_pair'])

    def test_many_to_many_difference_does_not_invent_confusion_pairs(self):
        segments=[Segment('a','Text','A','P','u'),Segment('b','Text','B','P','u')]
        result=analyze_codebook(segments,[book(c) for c in 'ABCD'],blind=multi(segments,{'u':(['C','D'],'assigned')}),settings={'label_mode':'multi_label'})
        self.assertEqual(len(result['difference_patterns']),1)
        self.assertEqual(result['difference_patterns'][0]['missing_codes'],['A','B'])
        self.assertEqual(result['difference_patterns'][0]['additional_codes'],['C','D'])
        self.assertFalse(result['difference_patterns'][0]['is_single_code_pair'])
        self.assertEqual(result['coassignments']['pairs'][0]['codes'],['A','B'])

    def test_coassignment_is_not_confusion_and_rare_counterpositions_are_not_deleted(self):
        segments=[Segment(f'{i}{c}','Text',c,'P',str(i)) for i in range(3) for c in 'AB']
        result=analyze_codebook(segments,[book('A'),book('B')],settings={'label_mode':'multi_label'})
        pair=result['coassignments']['pairs'][0]
        self.assertEqual(pair['overlap_coefficient'],1)
        self.assertTrue(pair['repeated_coassignment_hint'])
        self.assertEqual(result['difference_patterns'],[])
        self.assertIn('Gemeinsame Codierung ist keine Verwechslung',render_codebook_diagnostics(result))

    def test_long_unicode_definitions_compare_full_text_without_copying_it_into_report(self):
        long='Lange Definition 🧪;\n' * 60000
        books=[book('A',long),book('B',long),book('C',long+' Unterschied')]
        before=copy.deepcopy(books)
        result=analyze_codebook([],books)
        self.assertEqual(result['identical_definitions'][0]['codes'],['A','B'])
        self.assertEqual(result['categories'][0]['definition_characters'],len(long))
        self.assertEqual(len(result['categories'][0]['definition_preview']),600)
        self.assertTrue(result['categories'][0]['definition_preview_truncated'])
        self.assertEqual(books,before)
        self.assertNotIn(long,render_codebook_diagnostics(result))

    def test_normalization_and_repeated_anchor_are_only_review_hints(self):
        books=[book('A',' Lernen  in Gruppen ','LERNEN in Gruppen'),book('B','LERNEN\nin Gruppen','Beispiel')]
        result=analyze_codebook([],books)
        self.assertEqual(result['identical_definitions'][0]['codes'],['A','B'])
        self.assertIn('anchor_repeats_definition',result['categories'][0]['hints'])

    def test_large_dense_codebook_skips_pair_expansion_explicitly(self):
        books=[book(f'C{i}',f'Definition {i}') for i in range(450)]
        segments=[Segment(str(i),'Gleiche Passage',b.code,'P','u') for i,b in enumerate(books)]
        result=analyze_codebook(segments,books,settings={'label_mode':'multi_label'})
        self.assertEqual(result['coassignments']['status'],'not_calculated')
        self.assertEqual(result['coassignments']['pair_events'],101025)
        self.assertEqual(result['categories'][0]['human_units'],1)
        self.assertIn('Nicht berechnet: 101025',render_codebook_diagnostics(result))

    def test_corrupted_unit_copies_and_contradictory_passages_fail_closed(self):
        segments=[Segment('a','Text','A','P','u'),Segment('b','Text','B','P','u')]
        b=multi(segments,{'u':(['A'],'assigned')})
        b['results'][0]['predicted_codes']=['B']
        with self.assertRaisesRegex(ValueError,'Zeilenkopie widerspricht'):
            analyze_codebook(segments,[book('A'),book('B')],blind=b,settings={'label_mode':'multi_label'})
        segments[1]=Segment('b','Anderer Text','B','P','u')
        with self.assertRaisesRegex(ValueError,'unterschiedliche Originaltexte'):
            analyze_codebook(segments,[book('A'),book('B')],settings={'label_mode':'multi_label'})

    def test_saved_agreement_and_review_are_checked_against_sources(self):
        segments=[Segment('a','Text','A','P')];books=[book('A'),book('B')]
        v=verify(segments);b=single(segments,['B'])
        _,agreement=calculate_agreement(segments,books,v,b)
        queue=build_queue(segments,books,agreement,v,b,{'befunde':[]})
        before=copy.deepcopy((v,b,agreement,queue))
        result=analyze_codebook(segments,books,verification=v,blind=b,agreement=agreement,review=queue)
        self.assertEqual(result['categories'][0]['review_flagged_units'],1)
        self.assertEqual((v,b,agreement,queue),before)
        wrong=copy.deepcopy(agreement);wrong['confusion_matrix']['matrix'][0][1]=99
        with self.assertRaisesRegex(ValueError,'Agreement widerspricht'):
            analyze_codebook(segments,books,verification=v,blind=b,agreement=wrong)
        wrong=copy.deepcopy(queue);wrong['codebook'][0]['definition']='Verändert'
        with self.assertRaisesRegex(ValueError,'anderen Codebuch'):
            analyze_codebook(segments,books,verification=v,blind=b,review=wrong)
        queue['cases'][0]['needs_review']=False
        with self.assertRaisesRegex(ValueError,'Prüffall widerspricht'):
            analyze_codebook(segments,books,verification=v,blind=b,agreement=agreement,review=queue)
        agreement['case_counts']['strittig']=99
        with self.assertRaisesRegex(ValueError,'Agreement widerspricht'):
            analyze_codebook(segments,books,verification=v,blind=b,agreement=agreement)

    def test_verification_alternatives_do_not_become_extra_blind_assignments(self):
        segments=[Segment('a','Text','A','P')]
        v=verify(segments);v['results'][0]['alternative_codes']=['B','B']
        result=analyze_codebook(segments,[book('A'),book('B')],verification=v,blind=single(segments,['A']))
        self.assertEqual(result['verification_alternatives'],[{'human_code':'A','alternative_code':'B','rows':1}])
        self.assertEqual(result['categories'][1]['predicted_units'],0)
        self.assertEqual(result['difference_patterns'],[])

    def test_real_multi_agreement_and_review_use_one_case_per_passage(self):
        segments=[Segment('a','Text','A','P','u'),Segment('b','Text','B','P','u')]
        books=[book('A'),book('B')];v=verify(segments);b=multi(segments,{'u':(['A'],'assigned')})
        settings={'label_mode':'multi_label'}
        _,agreement=calculate_agreement(segments,books,v,b,settings=settings)
        queue=build_queue(segments,books,agreement,v,b,{'befunde':[]})
        result=analyze_codebook(segments,books,verification=v,blind=b,agreement=agreement,review=queue,settings=settings)
        self.assertEqual(result['n_units'],1)
        self.assertEqual(result['categories'][0]['review_flagged_units'],1)
        self.assertEqual(result['categories'][1]['missing_in_blind'],1)
        self.assertEqual(result['difference_patterns'][0]['case_ids'],['unit:u'])

    def test_invalid_inputs_reserved_names_and_markup(self):
        for segments,books in (([Segment('s','Text','MISSING','P')],[book('A')]),
                               ([Segment('s','Text','A','P')]*2,[book('A')]),
                               ([],[book('A'),book('A')]),([], [book('unklar')])):
            with self.assertRaises(ValueError):
                analyze_codebook(segments,books)
        with self.assertRaises(ValueError):
            analyze_codebook([],[],blind=[])
        result=analyze_codebook([],[book('<b>[A]</b>')])
        text=render_codebook_diagnostics(result)
        self.assertNotIn('<b>',text)
        self.assertIn('&lt;b&gt;',text)


if __name__=='__main__':
    unittest.main()
