"""Real relation-core inputs and stored selection receipts must agree."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from relation_analysis_core import build_relation_analysis, build_candidate_pairs
from runtime_support import fingerprint
from test_relation_selection import relation_fixture


class RelationSelectionCoreTests(unittest.TestCase):
    def run_core(self, *, reduce=False, verified=True):
        material,clusters,summaries=relation_fixture()
        if reduce:
            for item in summaries['cluster_summaries']:
                item['summary']='Vollständiger synthetischer Clusterkontext. '*2000
        seen=[]
        def model(system,user,params):
            data=json.loads(user);seen.extend(data['kandidaten'])
            return json.dumps({'beziehungen':[{'pair_id':p['pair_id'],'thema':'Synthetische Verbindung',
                'beziehungstyp':'wird_miteinander_verknuepft','beschreibung':'Eine mögliche Verbindung.',
                'segment_ids_a':[p['segmente_a'][0]['id']], 'segment_ids_b':[p['segmente_b'][0]['id']]}
                for p in data['kandidaten']], 'gesamteinordnung':'Synthetische Einordnung.'})
        def compact(value,*args):
            return {'verdichteter_kontext':'Vollständiger Eingang künstlich verdichtet.'}, {
                'used':True,'source_sha256':fingerprint(value), 'summary':'Vollständiger Eingang künstlich verdichtet.',
                'note':'Synthetischer Test einer vollständigen Kontextverdichtung.'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            texts={sid:material['units'][row['unit_id']]['text'] for sid,row in material['segment_index'].items()}
            for name,value in [('clusters',clusters),('texts',texts),('summaries',summaries)]:
                (root/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
            with patch('relation_analysis_core._llm',side_effect=model), patch('analysis_context.compact_context',side_effect=compact):
                md,result=build_relation_analysis(str(root/'clusters.json'),str(root/'texts.json'),str(root/'summaries.json'),
                    {'model':'synthetic','num_ctx':32768,'max_tokens':1500,'partial_checkpoints':False},
                    {'relation_analysis':{'system':'synthetic','user':'{data}'}},{},max_pairs=1,max_segments_per_path=2,
                    material=material if verified else None)
        return material,clusters,summaries,seen,md,result

    def test_actual_model_pairs_equal_receipt_and_legacy_mode_is_unchanged(self):
        *_,seen,md,result=self.run_core()
        receipt=result['selection_provenance']
        expected={row['pair_id']:row for row in receipt['submitted_pairs'].values()}
        self.assertEqual(set(expected),{p['pair_id'] for p in seen})
        for pair in seen:
            self.assertEqual(expected[pair['pair_id']]['original_pair_fingerprint'],fingerprint(pair))
        self.assertIn('Auswahlnachweis',md)
        *_,legacy_seen,legacy_md,legacy=self.run_core(verified=False)
        self.assertEqual(seen,legacy_seen)
        self.assertEqual(result['beziehungen'],legacy['beziehungen'])
        self.assertNotIn('selection_provenance',legacy)
        self.assertNotIn('Auswahlnachweis',legacy_md)

    def test_reduced_context_keeps_original_selected_sides_and_validates_source_receipts(self):
        material,clusters,summaries,seen,md,result=self.run_core(reduce=True)
        from relation_selection import validate_relation_selection
        self.assertTrue(result['context_reduction'])
        validate_relation_selection(material,result,clusters,summaries)
        expected={row['pair_id']:row for row in result['selection_provenance']['submitted_pairs'].values()}
        for pair in seen:
            for side in ('a','b'):
                self.assertEqual([s['id'] for s in pair['segmente_'+side]],expected[pair['pair_id']]['segment_ids_'+side])
                self.assertTrue(all(s['text']==material['units'][material['segment_index'][s['id']]['unit_id']]['text']
                                    for s in pair['segmente_'+side]))

    def test_invalid_limits_fail_even_without_candidate_pairs_and_before_file_reads(self):
        for pairs,segments in [(-1,6),(True,6),('80',6),(1,False),(1,0),(1,-1),(1,'6')]:
            with self.subTest(pairs=pairs,segments=segments),self.assertRaises(ValueError):
                build_candidate_pairs({},pairs,segments)
            with self.assertRaises(ValueError):
                build_relation_analysis('missing','missing','missing',{}, {}, {},pairs,segments)
        self.assertEqual(build_candidate_pairs({},0,1),([],0))

    def test_changed_original_text_map_fails_before_model_calls(self):
        material,clusters,summaries=relation_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,value in [('clusters',clusters),('texts',{}),('summaries',summaries)]:
                (root/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
            with patch('relation_analysis_core._llm') as llm, self.assertRaisesRegex(ValueError,'Originaltext-Zuordnung'):
                build_relation_analysis(str(root/'clusters.json'),str(root/'texts.json'),str(root/'summaries.json'),
                    {}, {}, {}, material=material)
            llm.assert_not_called()

    def test_equal_cluster_names_do_not_replace_another_clusters_summary(self):
        from relation_analysis_core import build_units
        clusters=[{'code_path':'A','cluster_name':'Gleich benannt','definition':'Definition '+str(i),
                   'segments':['s'+str(i)]} for i in range(2)]
        summaries={'cluster_summaries':[{**copy.deepcopy(row),'summary':'Zusammenfassung '+str(i)}
                                      for i,row in enumerate(clusters)]}
        units=build_units(clusters,{'s0':'Erste Aussage','s1':'Zweite Aussage'},summaries,
                          {'s0':{'person':'P'},'s1':{'person':'P'}})
        self.assertEqual([row['summary'] for row in units['A']['cluster']],
                         ['Zusammenfassung 0','Zusammenfassung 1'])
        summaries['cluster_summaries'].reverse()
        self.assertEqual(units,build_units(clusters,{'s0':'Erste Aussage','s1':'Zweite Aussage'},summaries,
                                          {'s0':{'person':'P'},'s1':{'person':'P'}}))

    def test_consistently_shortened_sources_cannot_hide_an_original_coding_row(self):
        from relation_selection import build_relation_selection
        material,clusters,summaries=relation_fixture()
        material['segment_index'].pop('B1')
        clusters['segment_metadata'].pop('B1')
        for row in clusters['clusters']+summaries['cluster_summaries']:
            if 'B1' in row['segments']:row['segments'].remove('B1')
        with self.assertRaisesRegex(ValueError,'vollständige Originalzuordnung'):
            build_relation_selection(material,clusters,summaries,max_pairs=0,max_segments_per_path=2)


if __name__=='__main__':unittest.main()
