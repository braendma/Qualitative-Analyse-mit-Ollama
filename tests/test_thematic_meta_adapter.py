"""Pure synthetic Meta-SWOT sources, including an actual core output contract."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from meta_swot_core import flatten_findings, build_meta_swot
from thematic_adapters import DIMENSIONS
from thematic_meta_adapter import build_meta_swot_topics
from thematic_counts import count_topics
from test_thematic_memberships import fixture
from test_thematic_adapters import swot


def meta_from_source(source, *, cross=True):
    by_dimension = flatten_findings(source)
    sections = {}; cross_count = 0
    for dimension in DIMENSIONS:
        rows = by_dimension[dimension]
        sources = sorted({row['source_id'] for row in rows})
        patterns, singles = [], []
        if cross and len(sources) >= 2:
            patterns = [{'thema':'Gemeinsames Meta-Thema','verdichtung':'Eine zusammengefasste analytische Möglichkeit.',
                         'finding_ids':[row['finding_id'] for row in rows],
                         'quellen':sources,'anzahl_quellen':len(sources)}]
            cross_count += len(rows)
        else:
            singles = [{'finding_id':row['finding_id'],'thema':row['thema'],'verdichtung':row['analyse'],
                        'quelle':row['source_id'],'segment_ids':list(row['segment_ids'])} for row in rows]
        sections[dimension] = {'uebergreifende_muster':patterns,'einzelbefunde':singles,
                               'statistik':{'befunde':len(rows),'quellbereiche':len(sources),
                                            'in_mehrquellenmustern':len(rows) if patterns else 0}}
    registry = {row['finding_id']:row for rows in by_dimension.values() for row in rows}
    return {'created_at':'synthetic-meta','source_swot_created_at':source.get('created_at'),
            'source_units':list(source['swot']),'source_unit_count':len(source['swot']),
            'finding_count':len(registry),'findings_in_cross_source_patterns':cross_count,
            'finding_registry':registry,'meta_swot':sections}


def meta_fixture():
    """Return (material, original_swot_payload, original_meta_swot_payload)."""
    material, clusters = fixture()
    source = swot(material,clusters)
    source['created_at']='synthetic-source'
    return material,source,meta_from_source(source)


class ThematicMetaAdapterTests(unittest.TestCase):
    def test_full_original_scope_not_only_selected_references(self):
        material,source,payload=meta_fixture()
        result=build_meta_swot_topics(material,payload,source)
        self.assertIsNone(result['assignments'])
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(result['assignment_origin'],'requires_full_thematic_assignment')
        self.assertEqual(len(result['topics']),1)
        topic=result['topics'][0]; link=result['source_links'][topic['topic_id']]
        self.assertEqual(topic['scope_unit_ids'],sorted(material['units']))
        self.assertEqual(topic['kind'],'derived')
        self.assertEqual(len(link['source_code_paths']),2)
        self.assertEqual(set(link['selected_evidence_segment_ids']),{'s1','s2'})
        self.assertEqual(len(topic['scope_unit_ids']),3)
        self.assertTrue(topic['inclusion'] and topic['exclusion'])

    def test_two_sources_one_person_and_overlapping_passage_are_not_summed(self):
        material,source,payload=meta_fixture()
        result=build_meta_swot_topics(material,payload,source); topic=result['topics'][0]
        cells=[{'topic_id':topic['topic_id'],'unit_id':uid,
                'status':'supported' if uid=='passage:u1' else 'no_evidence'} for uid in topic['scope_unit_ids']]
        count=count_topics(material,result['topics'],cells)['topics'][0]
        self.assertEqual(count['counts']['mentioned']['exact_person_count'],1)
        self.assertEqual(count['counts']['mentioned']['exact_passage_count'],1)
        self.assertEqual(count['scope']['person_count'],2)
        self.assertEqual(payload['meta_swot']['Chancen']['uebergreifende_muster'][0]['anzahl_quellen'],2)

    def test_single_findings_also_need_full_assignment_not_seeded_quotes(self):
        material,source,_=meta_fixture(); payload=meta_from_source(source,cross=False)
        result=build_meta_swot_topics(material,payload,source)
        self.assertEqual(len(result['topics']),2)
        self.assertIsNone(result['assignments'])
        self.assertTrue(all(topic['scope_unit_ids']==sorted(material['units']) for topic in result['topics']))
        counted=count_topics(material,result['topics'],[])
        self.assertTrue(all(row['counts']['mentioned']['exact_person_count'] is None for row in counted['topics']))

    def test_reordering_source_registry_patterns_preserves_semantic_topic_ids(self):
        material,source,_=meta_fixture()
        for group in source['swot'].values():
            group['Chancen'].append({**copy.deepcopy(group['Chancen'][0]),'thema':'Weiterer Befund','analyse':'Andere Idee.'})
        for cross in (True,False):
            original=meta_from_source(source,cross=cross)
            reordered=copy.deepcopy(source)
            reordered['swot']=dict(reversed(list(reordered['swot'].items())))
            for group in reordered['swot'].values(): group['Chancen'].reverse()
            moved=meta_from_source(reordered,cross=cross)
            moved['finding_registry']=dict(reversed(list(moved['finding_registry'].items())))
            moved['meta_swot']['Chancen']['einzelbefunde'].reverse()
            left=build_meta_swot_topics(material,original,source)
            right=build_meta_swot_topics(material,moved,reordered)
            self.assertEqual(left['topics'],right['topics'])
            self.assertEqual(set(left['source_links']),set(right['source_links']))

    def test_real_meta_core_payload_validates_without_schema_reconstruction(self):
        material,source,_=meta_fixture()
        def fake(system,user,params):
            rows=json.loads(user)
            return json.dumps({'cluster':[{'thema':'Ein echtes Core-Muster','verdichtung':'Synthetische Verdichtung',
                                            'finding_ids':[row['finding_id'] for row in rows]}]})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.json';path.write_text(json.dumps(source),encoding='utf-8')
            params={'model':'synthetic','num_ctx':32000,'max_tokens':1500,'parallel_workers':1,'partial_checkpoints':False}
            with patch('meta_swot_core.llm_meta_swot',fake), patch('meta_swot_core.update_progress'), patch('meta_batches.update_progress'):
                markdown,payload=build_meta_swot(str(path),params,{'meta_swot':{'system':'Meta','user':'{clusters}'}},{})
            result=build_meta_swot_topics(material,payload,source)
        self.assertEqual(len(result['topics']),1)
        self.assertIn('input_batching',payload['meta_swot']['Chancen'])
        self.assertIn('Synthetische Verdichtung',result['topics'][0]['definition'])
        self.assertTrue(markdown)

    def test_manipulated_registry_missing_references_and_statistics_fail(self):
        material,source,payload=meta_fixture()
        for change in ('registry_text','registry_source','registry_quote','registry_missing','unknown','duplicate','dimension',
                       'source_list','source_count','finding_count','cross_count','dimension_count','pattern_sources','pattern_count','empty_analysis','incomplete','extra_reference'):
            value=copy.deepcopy(payload); row=value['meta_swot']['Chancen']['uebergreifende_muster'][0]
            first=next(iter(value['finding_registry'].values()))
            if change=='registry_text':first['analyse']='Invented'
            if change=='registry_source':first['source_id']='B'
            if change=='registry_quote':first['segment_ids']=['s3']
            if change=='registry_missing':value['finding_registry'].pop(next(iter(value['finding_registry'])))
            if change=='unknown':row['finding_ids'][0]='MISSING'
            if change=='duplicate':row['finding_ids'].append(row['finding_ids'][0])
            if change=='dimension':value['meta_swot']['Stärken']['uebergreifende_muster']=[copy.deepcopy(row)]
            if change=='source_list':value['source_units']=['A']
            if change=='source_count':value['source_unit_count']=True
            if change=='finding_count':value['finding_count']=999
            if change=='cross_count':value['findings_in_cross_source_patterns']=999
            if change=='dimension_count':value['meta_swot']['Chancen']['statistik']['befunde']=1
            if change=='pattern_sources':row['quellen']=['A']
            if change=='pattern_count':row['anzahl_quellen']=9
            if change=='empty_analysis':row['verdichtung']=''
            if change=='incomplete':value['meta_swot']['Chancen']['uebergreifende_muster']=[]
            if change=='extra_reference':row['segment_ids']=['unknown']
            with self.subTest(change=change),self.assertRaises(ValueError):build_meta_swot_topics(material,value,source)

    def test_duplicate_or_cross_reused_findings_do_not_pass_partition_check(self):
        material,source,payload=meta_fixture()
        value=copy.deepcopy(payload)
        value['meta_swot']['Chancen']['uebergreifende_muster']*=2
        with self.assertRaises(ValueError):build_meta_swot_topics(material,value,source)
        value=copy.deepcopy(payload)
        single=meta_from_source(source,cross=False)['meta_swot']['Chancen']['einzelbefunde'][0]
        value['meta_swot']['Chancen']['einzelbefunde'].append(single)
        with self.assertRaises(ValueError):build_meta_swot_topics(material,value,source)

    def test_manipulated_original_source_is_rejected_even_with_rebuilt_registry(self):
        material,source,_=meta_fixture()
        for change in ('quote','person','foreign','code','partial'):
            value=copy.deepcopy(source)
            if change=='quote':value['swot']['A']['Chancen'][0]['zitate'][0]['text']='Invented text'
            if change=='person':value['segment_metadata']['s1']['person']='P2'
            if change=='foreign':value['swot']['A']['Chancen'][0]['segment_ids']=['unknown']
            if change=='code':value['swot']['A']['code_path']='B'
            if change=='partial':value['swot'].pop('B')
            with self.subTest(change=change),self.assertRaises(ValueError):build_meta_swot_topics(material,meta_from_source(value),value)

    def test_single_finding_must_preserve_its_source_text_and_references(self):
        material,source,_=meta_fixture()
        for field,new_value in (('thema','Invented'),('verdichtung','Invented'),('quelle','UNKNOWN'),('segment_ids',['s3'])):
            payload=meta_from_source(source,cross=False)
            payload['meta_swot']['Chancen']['einzelbefunde'][0][field]=new_value
            with self.subTest(field=field),self.assertRaises(ValueError):build_meta_swot_topics(material,payload,source)

    def test_long_definition_immutability_and_weighted_fields_do_not_change_candidates(self):
        material,source,payload=meta_fixture()
        payload['meta_swot']['Chancen']['uebergreifende_muster'][0]['verdichtung']='Ä 😀 vollständige Definition\n'*10000
        before=copy.deepcopy((material,source,payload))
        result=build_meta_swot_topics(material,payload,source)
        self.assertEqual((material,source,payload),before)
        self.assertIn(payload['meta_swot']['Chancen']['uebergreifende_muster'][0]['verdichtung'],result['topics'][0]['definition'])
        source['analysis_perspective']={'unrelated':'upstream weighted text'}
        payload['analysis_perspective']={'unrelated':'prior weighted result'}
        self.assertEqual(result,build_meta_swot_topics(material,payload,source))
        result['qualitative_source']['meta_swot'].clear()
        self.assertTrue(payload['meta_swot'])

    def test_empty_dimensions_are_complete_and_no_false_topics_are_created(self):
        material,source,_=meta_fixture()
        for group in source['swot'].values():group['Chancen']=[]
        result=build_meta_swot_topics(material,meta_from_source(source),source)
        self.assertEqual(result['topics'],[])
        self.assertEqual(result['source_links'],{})
        self.assertIsNone(result['assignments'])


if __name__=='__main__':unittest.main()
