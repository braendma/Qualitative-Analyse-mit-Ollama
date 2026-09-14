"""Pure diagnostic projections of real synthetic thematic adapter results."""
import copy
import json
import csv
import io
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from coding_validation_common import Segment
from diagnostic_sources import project_stage, make_snapshot, load_sources, load_snapshot
from runtime_support import atomic_json, file_hash
from coverage_core import analyze_coverage, render_coverage
from information_loss_core import analyze_information_loss, render_information_loss
from stability_core import analyze_stage_repetitions
from sensitivity_core import analyze_sensitivity
from thematic_execution import execute_perspective
from thematic_counts import count_topics
from test_thematic_memberships import fixture
from test_thematic_adapters import summary, swot
from test_thematic_execution import SyntheticBackend


class ThematicProjectionTests(unittest.TestCase):
    def setUp(self):
        self.material, self.clusters = fixture()
        self.segments = [Segment('s1','x','A','P1','u1'), Segment('s2','x','B','P1','u1'),
                         Segment('s3','y','A','P2','u2'), Segment('s4','z','B','P2','u3')]
        self.params = {'model':'synthetic','max_tokens':1500,'num_ctx':32000,
                       'partial_checkpoints':False,'parallel_workers':1}
        for name in ('analysis_work.update_progress', 'runtime_context.update_progress'):
            handle = patch(name); handle.start(); self.addCleanup(handle.stop)

    def payload(self, module='clusterer', mode='both'):
        original = self.clusters if module == 'clusterer' else summary(self.clusters) if module == 'summarizer' else swot(self.material, self.clusters)
        original = copy.deepcopy(original)
        extension = execute_perspective(module, mode, self.material, original, self.params,
                                        cluster_payload=self.clusters, llm=SyntheticBackend())
        return {**original, 'analysis_perspective':extension}

    def project(self, module, payload):
        return project_stage(module, payload, segments=self.segments)

    def compare(self, module, first, second):
        return analyze_stage_repetitions(self.segments, module,
            [{'sample_id':str(i),'status':'success','payload':value} for i,value in enumerate((first,second))])

    def test_old_projection_is_unchanged(self):
        value = {'clusters':[{'cluster_name':'Name','segments':['s1']}]}
        expected = {'records':[{'key':'clusters/0','kind':'cluster','scope':'input_association',
                    'comparison_context':[],'segment_ids':['s1'],'persons':[],'text':'Name','unresolved':[]}], 'warnings':[]}
        self.assertEqual(project_stage('clusterer', value), expected)
        self.assertEqual(self.project('clusterer', value), expected)

    def test_three_adapters_project_selected_modes_and_scalar_counts(self):
        for module in ('clusterer','summarizer','swot'):
            for mode in ('frequency','both'):
                value = self.payload(module, mode)
                before = copy.deepcopy(value)
                stage = self.project(module, value)
                thematic = [r for r in stage['records'] if r['scope']=='thematic_result']
                modes = {r['comparison_context'][-1] for r in thematic}
                self.assertEqual(modes, {'frequency','counts'} | ({'qualitative'} if mode=='both' else set()))
                for row in thematic:
                    self.assertEqual(row['segment_ids'], [])
                    self.assertEqual(row['persons'], [])
                    self.assertNotIn('assignments', row['text'])
                    self.assertNotIn('unit_ids', row['text'])
                    self.assertNotIn('person_ids', row['text'])
                self.assertEqual(before, value)

    def test_frequency_text_change_is_visible_while_old_candidates_stay_identical(self):
        first = self.payload('swot', 'frequency'); second = copy.deepcopy(first)
        second['analysis_perspective']['interpretations']['frequency'][0]['interpretation'] = 'A changed frequency-informed interpretation'
        self.assertEqual(first['swot'], second['swot'])
        result = self.compare('swot',first,second)
        self.assertEqual(result['comparison_status'], 'available')
        self.assertLess(result['pairs'][0]['projected_record_overlap']['value'],1)
        changed = [r for r in result['record_occurrences'] if r['kind']=='thematic_interpretation' and r['repeat_status']=='variable']
        self.assertEqual(len(changed),2)

    def test_valid_count_change_is_visible_without_changed_model_prose(self):
        first = self.payload('swot'); second = copy.deepcopy(first)
        ext = second['analysis_perspective']; counted = ext['counting']
        assignments = copy.deepcopy(counted['assignments']); assignments[0]['status'] = 'no_evidence'
        ext['counting'] = count_topics(self.material, counted['definitions'], assignments)
        result = self.compare('swot',first,second)
        self.assertLess(result['pairs'][0]['projected_record_overlap']['value'],1)
        changed = [r for r in result['record_occurrences'] if r['kind']=='thematic_counts' and r['repeat_status']=='variable']
        self.assertEqual(len(changed),2)

    def test_unknown_is_compared_as_unknown_not_zero_or_missing_theme(self):
        value = self.payload('swot')
        counted = value['analysis_perspective']['counting']
        assignments = copy.deepcopy(counted['assignments']); assignments[0]['status'] = 'unclear'
        value['analysis_perspective']['counting'] = count_topics(self.material, counted['definitions'], assignments)
        rows = [r for r in self.project('swot',value)['records'] if r['kind']=='thematic_counts']
        self.assertTrue(any(json.loads(r['text'])['counts']['mentioned']['exact_person_count'] is None for r in rows))
        self.assertTrue(any(json.loads(r['text'])['coverage']['status_counts']['unclear'] == 1 for r in rows))

    def test_scope_and_assignments_are_never_inflated_into_selected_evidence(self):
        value = self.payload('swot')
        old = project_stage('swot',{k:v for k,v in value.items() if k!='analysis_perspective'})
        new = self.project('swot',value)
        snapshots = []
        for stage in (old,new):
            stage['status']='available'
            snapshots.append(analyze_coverage(make_snapshot(self.segments,{'swot':stage}))['stages']['swot'])
        self.assertEqual(snapshots[0]['scopes'], snapshots[1]['scopes'])

    def test_cluster_membership_and_coassignment_do_not_count_extra_records(self):
        first = self.payload(); second = copy.deepcopy(first)
        second['analysis_perspective']['interpretations']['frequency'][0]['interpretation']='Changed'
        result = self.compare('clusterer',first,second)
        pair = result['pairs'][0]
        self.assertEqual(pair['cluster_membership_overlap']['value'],1)
        self.assertEqual(pair['coassignment_overlap']['value'],1)
        self.assertEqual(result['sample_details'][0]['coassignment']['pair_events'],1)
        self.assertLess(pair['projected_record_overlap']['value'],1)

    def test_sensitivity_sees_frequency_change_and_no_fake_empty_cluster(self):
        first = self.payload(); second = copy.deepcopy(first)
        second['analysis_perspective']['interpretations']['frequency'][0]['limitations']='New limitation'
        samples = [{'sample_id':f'{cid}-{i}','configuration_id':cid,'status':'success','payload':value}
                   for cid,value in (('baseline',first),('variant',second)) for i in range(2)]
        result = analyze_sensitivity(self.segments, [], 'clusterer',
                                     [{'configuration_id':'baseline'},{'configuration_id':'variant'}],samples)
        memberships = [r for r in result['findings'] if r['feature_type']=='cluster_membership']
        self.assertEqual(len(memberships),3)
        self.assertTrue(all(r['segment_ids'] for r in memberships))
        self.assertTrue(any(r['feature_type']=='exact_projection' and r.get('kind')=='thematic_interpretation' and r['observed_patterns_differ'] for r in result['findings']))

    def test_malformed_extensions_do_not_silently_fall_back_to_old_text(self):
        for change in ('null','module','mode','missing_mode','unknown_topic','duplicate_topic','source_link','candidate','scope','counts','qualitative','kind','origin'):
            value = self.payload('swot'); ext = value['analysis_perspective']
            if change=='null': value['analysis_perspective']=None
            if change=='module': ext['module_id']='summarizer'
            if change=='mode': ext['selected_mode']='qualitative'
            if change=='missing_mode': ext['interpretations'].pop('frequency')
            if change=='unknown_topic': ext['interpretations']['frequency'][0]['topic_id']='Unknown'
            if change=='duplicate_topic': ext['interpretations']['frequency'].append(copy.deepcopy(ext['interpretations']['frequency'][0]))
            if change=='source_link': next(iter(ext['source_links'].values()))['qualitative_text']='Changed source'
            if change=='candidate': ext['candidate_source_fingerprint']='0'*64
            if change=='scope': ext['counting']['definitions'][0]['scope_unit_ids'].append('unknown')
            if change=='counts': ext['counting']['topics'][0]['counts']['mentioned']['exact_person_count']=999
            if change=='qualitative': ext['interpretations']['qualitative'][0]['interpretation']='Changed source'
            if change=='kind': ext['counting']['definitions'][0]['kind']='explicit'
            if change=='origin': ext['assignment_origin']='selected_quotes'
            with self.subTest(change=change), self.assertRaises(ValueError): self.project('swot',value)

    def test_original_material_and_memberships_are_verified(self):
        value = self.payload()
        with self.assertRaises(ValueError): project_stage('clusterer',value)
        wrong = [Segment(s.segment_id,'changed',s.human_code,s.person,s.unit_id) for s in self.segments]
        with self.assertRaises(ValueError): project_stage('clusterer',value,segments=wrong)
        counted = value['analysis_perspective']['counting']; rows=copy.deepcopy(counted['assignments'])
        rows[0]['status']='opposed'
        value['analysis_perspective']['counting']=count_topics(self.material,counted['definitions'],rows)
        with self.assertRaises(ValueError): self.project('clusterer',value)

    def test_weighted_coverage_and_information_loss_render_without_false_missing_links(self):
        plain, weighted = {}, {}
        for module in ('clusterer','summarizer','swot'):
            value = self.payload(module)
            original = {key:item for key,item in value.items() if key!='analysis_perspective'}
            plain[module] = {'status':'available', **project_stage(module,original)}
            weighted[module] = {'status':'available', **self.project(module,value)}
        snapshots = [make_snapshot(self.segments, stages) for stages in (plain, weighted)]
        edges = [('clusterer','summarizer'),('summarizer','swot')]
        old, new = [analyze_information_loss(snapshot,edges) for snapshot in snapshots]
        self.assertEqual(old['input_to_clusters'], new['input_to_clusters'])
        self.assertEqual(new['input_to_clusters']['status'],'available')
        for before, after in zip(old['transitions'],new['transitions']):
            self.assertEqual(before['reference_comparison'],after['reference_comparison'])
            self.assertIsNotNone(after['reference_comparison'])
            self.assertEqual(before['review_items'],after['review_items'])
            self.assertGreater(after['non_reference_thematic_records']['source'],0)
            self.assertTrue(all(item['source']['scope']!='thematic_result' for item in after['review_items']))
        coverage = analyze_coverage(snapshots[1])
        coverage_md = render_coverage(coverage)
        loss_md = render_information_loss(new)
        self.assertIn('keine ausgewählten Belege', coverage_md)
        self.assertIn('keine Belegauswahl', loss_md)
        self.assertIn('nicht als fehlende Verknüpfungen', loss_md)
        self.assertEqual(new['processing_status'],'completed')
        self.assertEqual(coverage['processing_status'],'completed')

    def test_thematic_only_stage_does_not_claim_reference_coverage_or_loss(self):
        stage = self.project('clusterer',self.payload())
        stage['records'] = [row for row in stage['records'] if row['scope']=='thematic_result']
        stage['status']='available'
        snapshot = make_snapshot(self.segments,{'clusterer':stage,'summarizer':copy.deepcopy(stage)})
        result = analyze_information_loss(snapshot,[('clusterer','summarizer')])
        self.assertEqual(result['input_to_clusters']['status'],'not_measurable')
        self.assertIsNone(result['transitions'][0]['reference_comparison'])
        self.assertEqual(result['transitions'][0]['review_items'],[])
        self.assertIn('keine Belegauswahl',render_information_loss(result))

    def test_hash_verified_loader_and_snapshot_supply_real_material(self):
        value = self.payload()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = {'id':'clusterer','args':['--out-json','clusters.json'],'outputs':['clusters.json'],'depends_on':[]}
            columns = {'segment_id':'ID','segment':'Text','code':'Code','person':'Person','unit_id':'Passage'}
            config = {'pipeline':{'modules':[module]},'columns':columns}
            text = io.StringIO(); writer = csv.writer(text, delimiter=';', lineterminator='\n')
            writer.writerow(['ID','Text','Code','Person','Passage'])
            for row in self.segments:
                writer.writerow([row.segment_id,row.text,row.human_code,row.person,row.unit_id])
            (root/'input.csv').write_text(text.getvalue(),encoding='utf-8')
            atomic_json(root/'config.yaml', config)
            atomic_json(root/'clusters.json',value)
            manifest = {'completed_steps':['clusterer'],'output_hashes':{'clusters.json':file_hash(root/'clusters.json')},
                        'provenance':{'config_sha256':file_hash(root/'config.yaml'),'input_sha256':file_hash(root/'input.csv')}}
            atomic_json(root/'workflow_manifest.json',manifest)
            self.assertEqual(load_sources(root,config)['clusterer']['status'],'invalid')
            loaded = load_sources(root,config,segments=self.segments)['clusterer']
            self.assertEqual(loaded['status'],'available')
            snapshot = load_snapshot(root,root/'config.yaml',root/'input.csv')
            self.assertTrue(all(row['valid'] for row in snapshot['stages']['clusterer']['records']))
            self.assertTrue(any(row['kind']=='thematic_counts' for row in snapshot['stages']['clusterer']['records']))
            value['analysis_perspective']['interpretations']['frequency'][0]['interpretation']='Tampered file'
            atomic_json(root/'clusters.json',value)
            self.assertEqual(load_sources(root,config,segments=self.segments)['clusterer']['status'],'invalid')

    def test_malformed_sample_is_excluded_not_misrepresented_as_stable(self):
        first = self.payload(); second=copy.deepcopy(first)
        second['analysis_perspective']['counting']['basis_fingerprint']='changed'
        result=self.compare('clusterer',first,second)
        self.assertEqual(result['included_samples'],['0'])
        self.assertEqual(result['excluded_samples'],[{'sample_id':'1','reason':'invalid_artifact'}])
        self.assertEqual(result['comparison_status'],'not_computable')


if __name__=='__main__': unittest.main()
