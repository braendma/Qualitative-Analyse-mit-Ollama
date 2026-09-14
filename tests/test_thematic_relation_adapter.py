"""Semantic relation topics use real core/normalizer sources and full scopes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coding_validation_common import Segment
from thematic_material import build_material
from thematic_counts import count_topics
from relation_analysis_core import normalize_relations, build_relation_analysis
from thematic_relation_adapter import build_relation_topics
from test_relation_selection import relation_fixture as selection_fixture, _payload, _inputs


def relation_fixture():
    """Return (material, clusters, summaries, validated real-normalized relation)."""
    material, clusters, summaries = selection_fixture()
    return material, clusters, summaries, _payload(material, clusters, summaries)


def build(values):
    material, clusters, summaries, payload = values
    return build_relation_topics(material, payload, clusters, summaries)


class ThematicRelationAdapterTests(unittest.TestCase):
    def test_candidate_examples_do_not_limit_complete_semantic_scope(self):
        values=relation_fixture();material=values[0];result=build(values)
        self.assertEqual(len(result['topics']),1)
        topic=result['topics'][0];link=result['source_links'][topic['topic_id']]
        self.assertEqual(topic['scope_unit_ids'],sorted(material['units']))
        self.assertEqual(topic['kind'],'derived');self.assertIsNone(result['assignments'])
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(link['selected_evidence_segment_ids'],['A1','B1'])
        self.assertEqual(link['source_evidence_person_ids'],['P1'])
        counted=count_topics(material,result['topics'],[])['topics'][0]
        self.assertEqual(counted['scope']['person_count'],3)
        self.assertIsNone(counted['counts']['mentioned']['exact_person_count'])

    def test_code_cooccurrence_is_complete_separate_and_not_assignment_evidence(self):
        result=build(relation_fixture())
        self.assertEqual(len(result['code_cooccurrence']['pairs']),3)
        self.assertEqual(len(result['topics']),1)
        self.assertEqual(result['code_cooccurrence']['count_basis'],'existing_code_path_assignments')
        self.assertTrue(all('code_cooccurrence' not in row for row in result['source_links'].values()))
        self.assertIsNone(result['assignments'])
        self.assertIn('keine',result['methodological_note'])

    def test_cross_person_evidence_and_incomplete_assertions_remain_context(self):
        for mode in ('across','incomplete'):
            material,clusters,summaries,payload=relation_fixture()
            if mode=='across':payload=_payload(material,clusters,summaries,across=True)
            else:payload['beziehungen'][0]['beschreibung']=''
            result=build_relation_topics(material,payload,clusters,summaries)
            self.assertEqual(result['topics'],[])
            record=result['unassigned_context']['records'][0]
            self.assertEqual(record['reason'],'cross_person_evidence' if mode=='across' else 'incomplete_candidate')
            self.assertEqual(record['record'],payload['beziehungen'][0])
            self.assertIsNone(result['assignments'])
            self.assertEqual(result['code_cooccurrence']['scope']['person_count'],3)

    def test_same_title_distinct_relations_and_order_independent_semantic_ids(self):
        material,clusters,summaries=selection_fixture()
        payload=_payload(material,clusters,summaries,max_pairs=0)
        texts,_,pairs,_=_inputs(material,clusters,summaries,max_pairs=0)
        raw=[{'pair_id':pair['pair_id'],'thema':'Gleicher Titel','beschreibung':'Vollständige Behauptung ' + pair['pfad_b'],
            'beziehungstyp':'wird_miteinander_verknuepft','segment_ids_a':[pair['segmente_a'][0]['id']],
            'segment_ids_b':[pair['segmente_b'][0]['id']]} for pair in pairs]
        payload.update(normalize_relations({'beziehungen':raw,'gesamteinordnung':'Original.'},{p['pair_id']:p for p in pairs},texts))
        payload['candidate_pair_count_with_relation']=len(raw)
        payload['candidate_pair_count_without_validated_relation']=0
        expected=build_relation_topics(material,payload,clusters,summaries)
        self.assertEqual(len(expected['topics']),3)
        payload['beziehungen'].reverse()
        for index,row in enumerate(payload['beziehungen'],1):row['relation_id']=f'REL{index:04d}'
        actual=build_relation_topics(material,payload,clusters,summaries)
        self.assertEqual(expected['topics'],actual['topics'])
        self.assertNotEqual(expected['source_fingerprint'],actual['source_fingerprint'])

    def test_relation_type_is_semantic_identity_not_automatic_causal_direction(self):
        values=relation_fixture();before=build(values)
        values[-1]['beziehungen'][0]['beziehungstyp']='wird_als_folge_beschrieben'
        after=build(values)
        self.assertNotEqual(before['topics'][0]['topic_id'],after['topics'][0]['topic_id'])
        self.assertIn('keine Wirkungsrichtung',after['topics'][0]['exclusion'])
        self.assertIn('kein Kausalnachweis',after['topics'][0]['inclusion'])
        self.assertIn('nicht A und B gemeinsam',after['topics'][0]['exclusion'])

    def test_changed_selected_examples_preserve_candidate_identity(self):
        values=relation_fixture();before=build(values)
        material,clusters,summaries,payload=values
        row=payload['beziehungen'][0]
        row.update(segment_ids_a=['A2'],segment_ids_b=['B2'],beidseitig_belegte_personen=['P2'])
        row['belege_a']=[{'segment_id':'A2','text':'A second person'}]
        row['belege_b']=[{'segment_id':'B2','text':'B second person'}]
        after=build(values)
        self.assertEqual(before['topics'],after['topics'])
        self.assertNotEqual(before['source_links'],after['source_links'])

    def test_corrupt_selection_or_side_never_becomes_uncounted_soft_failure(self):
        for mode in ('receipt','quote','person','missingreceipt'):
            values=relation_fixture();payload=values[-1]
            payload['beziehungen'][0]['beschreibung']=''
            if mode=='receipt':payload['selection_provenance']['parameters']['max_segments_per_path']=1
            if mode=='quote':payload['beziehungen'][0]['belege_a'][0]['text']='changed'
            if mode=='person':payload['beziehungen'][0]['beidseitig_belegte_personen']=['P3']
            if mode=='missingreceipt':del payload['selection_provenance']
            with self.subTest(mode=mode),self.assertRaises(ValueError):build(values)

    def test_missing_passage_ids_keep_exact_passage_metrics_unknown(self):
        material,clusters,summaries=selection_fixture()
        rows=[Segment(sid,material['units'][entry['unit_id']]['text'],entry['code_path'],
            material['units'][entry['unit_id']]['person'],None) for sid,entry in material['segment_index'].items()]
        material=build_material(rows,person_basis='confirmed')
        for value in clusters['segment_metadata'].values():value['unit_id']=None
        payload=_payload(material,clusters,summaries)
        result=build_relation_topics(material,payload,clusters,summaries)
        self.assertIsNone(result['code_cooccurrence']['scope']['exact_passage_count'])
        counted=count_topics(material,result['topics'],[{'topic_id':result['topics'][0]['topic_id'],'unit_id':uid,'status':'supported'} for uid in material['units']])['topics'][0]
        self.assertIsNone(counted['counts']['mentioned']['exact_passage_count'])
        self.assertEqual(counted['counts']['mentioned']['exact_person_count'],3)

    def test_extensions_and_mutable_return_do_not_change_original_sources(self):
        values=relation_fixture();expected=build(values)
        for value in values[1:]:value['analysis_perspective']={'text':'Additional weighted output '*200}
        before=copy.deepcopy(values)
        result=build(values)
        self.assertEqual(result,expected);self.assertEqual(values,before)
        result['qualitative_source']['beziehungen'].clear()
        result['source_links'][result['topics'][0]['topic_id']]['selected_evidence_segment_ids'].clear()
        result['unassigned_context']['selection_summary'].clear()
        self.assertEqual(values,before)

    def test_actual_confirmed_core_output_is_accepted(self):
        material,clusters,summaries=selection_fixture();texts,_,_,_=_inputs(material,clusters,summaries)
        def model(system,user,params):
            pair=json.loads(user)['kandidaten'][0]
            return json.dumps({'beziehungen':[{'pair_id':pair['pair_id'],'thema':'Verknüpfung',
                'beschreibung':'Planbarkeit und persönliche Gestaltung werden miteinander verknüpft.',
                'beziehungstyp':'wird_miteinander_verknuepft','segment_ids_a':[pair['segmente_a'][0]['id']],
                'segment_ids_b':[pair['segmente_b'][0]['id']]}],'gesamteinordnung':'Synthetischer Kontext.'})
        with tempfile.TemporaryDirectory() as temp,patch('relation_analysis_core._llm',side_effect=model):
            paths=[]
            for name,value in (('clusters',clusters),('texts',texts),('summary',summaries)):
                path=Path(temp)/(name+'.json');path.write_text(json.dumps(value),encoding='utf-8');paths.append(path)
            _,payload=build_relation_analysis(*paths,{'model':'synthetic','num_ctx':32768,'max_tokens':1024,'partial_checkpoints':False},
                {'relation_analysis':{'system':'Synthetic','user':'{data}'}},{},max_pairs=1,max_segments_per_path=2,material=material)
            self.assertEqual(len(build_relation_topics(material,payload,clusters,summaries)['topics']),1)


if __name__=='__main__':unittest.main()
