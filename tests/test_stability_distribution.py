import copy
import unittest

from test_stability_core import samples, swot, clusters
from coding_validation_common import Segment
from stability_core import analyze_stage_repetitions
from stability_report import render_stability


class StabilityDistributionTests(unittest.TestCase):
    def test_multi_coding_deduplicates_people_but_preserves_category_rows(self):
        segments=[Segment('a','Same','A > Positiv','P','u'),Segment('b','Same','B > Negativ','P','u'),
                  Segment('c','Other','A > Positiv','Q','v')]
        result=analyze_stage_repetitions(segments,'swot',samples(swot(ids=['a','b','c']),swot(ids=['a','c'])))
        change=result['pairs'][0]['selection_distribution_changes'][0]
        self.assertEqual((change['selected_units_left'],change['selected_units_right']),(2,2))
        self.assertEqual(change['by_person'][0]['share_delta'],0)
        a=next(c for c in change['by_category'] if c['code']=='A')
        b=next(c for c in change['by_category'] if c['code']=='B')
        self.assertEqual((a['level_selected_rows_left'],a['level_selected_rows_right']),(3,2))
        self.assertAlmostEqual(a['share_delta'],1/3)
        self.assertEqual((b['selected_coding_rows_left'],b['selected_coding_rows_right']),(1,0))
        self.assertEqual(result['unit_basis'],'explicit_passages')

    def test_identical_text_and_merged_person_documents_are_not_extra_people(self):
        segments=[Segment('doc1-a','Same text','A','MergedPerson'),Segment('doc2-a','Same text','A','MergedPerson'),
                  Segment('doc3-a','Other','B','SecondPerson')]
        result=analyze_stage_repetitions(segments,'clusterer',samples(
            clusters(['doc1-a','doc2-a','doc3-a']),clusters(['doc1-a','doc3-a'])))
        change=result['pairs'][0]['selection_distribution_changes'][0]
        self.assertEqual(change['material_units'],3)
        self.assertEqual(len(change['by_person']),2)
        p=change['by_person'][0]
        self.assertEqual((p['selected_units_left'],p['selected_units_right']),(2,1))
        self.assertAlmostEqual(p['share_delta'],-1/6)

    def test_repeated_citations_do_not_inflate_selection(self):
        segments=[Segment('a','Text','A','P'),Segment('b','Else','B','Q')]
        a=swot(ids=['a']);b=copy.deepcopy(a)
        b['swot']['Code/1']['Stärken']*=10
        result=analyze_stage_repetitions(segments,'swot',samples(a,b))
        change=result['pairs'][0]['selection_distribution_changes'][0]
        self.assertEqual((change['selected_units_left'],change['selected_units_right']),(1,1))
        self.assertEqual(change['by_person'][0]['share_delta'],0)
        self.assertLess(result['pairs'][0]['projected_record_overlap']['value'],1)

    def test_empty_selection_keeps_counts_zero_shares_unknown(self):
        segments=[Segment('a','Text','A','P')]
        empty={'swot':{'Code/1':{d:[] for d in ('Stärken','Schwächen','Chancen','Risiken')}}}
        result=analyze_stage_repetitions(segments,'swot',samples(empty,swot()))
        change=result['pairs'][0]['selection_distribution_changes'][0]
        self.assertEqual(change['selected_units_left'],0)
        self.assertIsNone(change['by_person'][0]['share_left'])
        self.assertIsNone(change['by_person'][0]['share_delta'])
        self.assertEqual(change['by_category'][0]['level_selected_rows_left'],0)
        result['runtime_comparison']={'parameter_profiles_same':None}
        text=render_stability({'conditions':[],'comparisons':{'swot':result},'notes':[]})
        self.assertIn('keine ausgewählten Einheiten',text)
        self.assertIn('keine umfassende thematische Nennungshäufigkeit',text)

    def test_person_only_reference_does_not_expand_to_all_person_text(self):
        segments=[Segment('a','Text','A','P')]
        a={'dominante_muster':[],'negativfaelle':[{'person':'P','abweichung':'Befund'}],
           'spannungen_zwischen_typen':[],'relativierungen':[]}
        result=analyze_stage_repetitions(segments,'contrast_analysis',samples(a,a))
        change=result['pairs'][0]['selection_distribution_changes'][0]
        self.assertFalse(change['comparable'])
        self.assertEqual(change['reason'],'person_references_only')
        self.assertEqual(change['by_category'],[])
        self.assertEqual(change['persons_named_left'],['P'])

    def test_inconsistent_passages_reject_even_all_failed_samples(self):
        for segments in ([Segment('a','Text','A','P','u'),Segment('b','Text','A','Q','u')],
                         [Segment('a','Text','A','P','u'),Segment('b','Different','A','P','u')]):
            data=samples(clusters(),clusters())
            for sample in data:sample['status']='failed'
            with self.assertRaises(ValueError):
                analyze_stage_repetitions(segments,'clusterer',data)

    def test_failed_sample_has_no_zero_distribution_and_deep_paths_have_levels(self):
        segments=[Segment('a','Text','A > B > C > D','P')]
        data=samples(swot(),swot(),swot());data[-1]['status']='failed'
        result=analyze_stage_repetitions(segments,'swot',data)
        self.assertEqual(len(result['pairs']),1)
        self.assertEqual(len(result['sample_details']),2)
        categories=result['pairs'][0]['selection_distribution_changes'][0]['by_category']
        self.assertEqual([c['level'] for c in categories],[1,2,3,4])

    def test_level_denominators_exclude_rows_without_that_depth(self):
        segments=[Segment('a','Text','A > B > C > D','P'),Segment('b','Short','X','Q')]
        result=analyze_stage_repetitions(segments,'swot',samples(swot(ids=['a','b']),swot(ids=['a'])))
        rows=result['pairs'][0]['selection_distribution_changes'][0]['by_category']
        self.assertEqual(next(r for r in rows if r['code']=='A')['level_selected_rows_left'],2)
        self.assertEqual(next(r for r in rows if r['code']=='A > B')['level_selected_rows_left'],1)
        self.assertEqual(next(r for r in rows if r['code']=='A > B')['share_delta'],0)


if __name__=='__main__':unittest.main()
