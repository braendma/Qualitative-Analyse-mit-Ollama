"""Case-level thematic diagnostics with actual, verified original upstream files."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from coding_validation_common import Segment
from diagnostic_sources import project_stage, load_sources, make_snapshot
from stability_core import analyze_stage_repetitions
from stability_series import _thematic_upstreams
from sensitivity_core import analyze_sensitivity
from thematic_execution import execute_perspective
from thematic_counts import count_topics
from runtime_support import atomic_json, file_hash
from test_thematic_meta_adapter import meta_fixture
from test_thematic_person_adapters import fixture as person_fixture
from test_thematic_execution import SyntheticBackend


def original_segments(material):
    result=[]
    for sid, row in material['segment_index'].items():
        unit=material['units'][row['unit_id']]
        passage=row['unit_id'][len('passage:'):] if unit['kind']=='passage' else None
        result.append(Segment(sid,unit['text'],row['code_path'],unit['person'],passage))
    return result


class ThematicCaseProjectionTests(unittest.TestCase):
    def setUp(self):
        self.params={'model':'synthetic','num_ctx':32000,'max_tokens':1500,
                     'parallel_workers':1,'partial_checkpoints':False}
        for name in ('analysis_work.update_progress','runtime_context.update_progress','thematic_interpretation.begin_phase'):
            handle=patch(name);handle.start();self.addCleanup(handle.stop)

    def fixture(self,module,mode='both',weighted_upstream=False):
        if module=='meta_swot':
            material,source,payload=meta_fixture(); upstream={'swot':source}; kwargs={'swot_payload':source}
        elif module=='person_comparison':
            from test_thematic_comparison_adapter import comparison_fixture
            material,source,payload=comparison_fixture(); upstream={'person_analysis':source}; kwargs={'person_payload':source}
        else:
            material,persons,ambiguity=person_fixture()
            payload=persons if module=='person_analysis' else ambiguity
            upstream={} if module=='person_analysis' else {'person_analysis':persons}
            kwargs={} if module=='person_analysis' else {'person_payload':persons}
        if weighted_upstream:
            for mid,source in upstream.items():
                source['analysis_perspective']=execute_perspective(mid,'both',material,source,self.params,llm=SyntheticBackend())
        extension=execute_perspective(module,mode,material,payload,self.params,llm=SyntheticBackend(),**kwargs)
        return material,{**payload,'analysis_perspective':extension},upstream

    def test_comparison_basis_must_match_actual_module_and_is_required_for_new_case_results(self):
        for module in ('meta_swot','person_analysis','ambiguity_analysis','person_comparison'):
            material,payload,upstream=self.fixture(module)
            expected='all_fixed_topics' if module in ('meta_swot','person_comparison') else 'same_person_scope'
            self.assertEqual(payload['analysis_perspective']['interpretation_comparison_basis'],expected)
            for wrong in (None,'wrong','all_fixed_topics' if expected=='same_person_scope' else 'same_person_scope'):
                value=copy.deepcopy(payload)
                if wrong is None:value['analysis_perspective'].pop('interpretation_comparison_basis')
                else:value['analysis_perspective']['interpretation_comparison_basis']=wrong
                with self.subTest(module=module,basis=wrong),self.assertRaises(ValueError):
                    project_stage(module,value,segments=original_segments(material),upstream_payloads=upstream)

    def test_legacy_first_three_modules_default_to_complete_fixed_topic_register(self):
        from test_thematic_memberships import fixture
        from test_thematic_adapters import summary, swot
        material,clusters=fixture()
        for module in ('clusterer','summarizer','swot'):
            source=clusters if module=='clusterer' else summary(clusters) if module=='summarizer' else swot(material,clusters)
            extension=execute_perspective(module,'frequency',material,source,self.params,cluster_payload=clusters,llm=SyntheticBackend())
            current={**source,'analysis_perspective':extension}
            legacy=copy.deepcopy(current);legacy['analysis_perspective'].pop('interpretation_comparison_basis')
            self.assertEqual(project_stage(module,current,segments=original_segments(material)),
                             project_stage(module,legacy,segments=original_segments(material)))
            current['analysis_perspective']['interpretation_comparison_basis']='same_person_scope'
            with self.assertRaises(ValueError):project_stage(module,current,segments=original_segments(material))

    def test_all_three_project_named_interpretations_and_recomputed_counts(self):
        for module in ('meta_swot','person_analysis','ambiguity_analysis','person_comparison'):
            for mode in ('frequency','both'):
                material,payload,upstream=self.fixture(module,mode)
                before=copy.deepcopy((material,payload,upstream))
                stage=project_stage(module,payload,segments=original_segments(material),upstream_payloads=upstream)
                thematic=[row for row in stage['records'] if row['scope']=='thematic_result']
                self.assertTrue(thematic)
                self.assertEqual({r['comparison_context'][-1] for r in thematic},
                                 {'frequency','counts'} | ({'qualitative'} if mode=='both' else set()))
                for row in thematic:
                    self.assertEqual(row['segment_ids'],[])
                    self.assertEqual(row['persons'],[])
                    self.assertNotIn('unit_ids',row['text'])
                    self.assertNotIn('assignments',row['text'])
                self.assertEqual(before,(material,payload,upstream))

    def test_missing_original_sources_cannot_be_rebuilt_from_selected_registry(self):
        for module in ('meta_swot','ambiguity_analysis','person_comparison'):
            material,payload,_=self.fixture(module)
            with self.subTest(module=module),self.assertRaises(ValueError):
                project_stage(module,payload,segments=original_segments(material))

    def test_changed_upstream_text_and_person_scopes_are_rejected(self):
        for module in ('meta_swot','ambiguity_analysis','person_comparison'):
            material,payload,upstream=self.fixture(module)
            if module=='meta_swot':upstream['swot']['swot']['A']['Chancen'][0]['analyse']='Changed original'
            else:upstream['person_analysis']['persons']['P01']['segment_ids'].pop()
            with self.subTest(module=module),self.assertRaises(ValueError):
                project_stage(module,payload,segments=original_segments(material),upstream_payloads=upstream)

    def test_weighted_upstream_fields_do_not_replace_original_candidate_basis(self):
        for module in ('meta_swot','ambiguity_analysis','person_comparison'):
            material,payload,upstream=self.fixture(module,weighted_upstream=True)
            baseline=project_stage(module,payload,segments=original_segments(material),upstream_payloads=upstream)
            for source in upstream.values():
                source['analysis_perspective']['interpretations']['frequency'][0]['interpretation']='Changed weighted interpretation only'
            again=project_stage(module,payload,segments=original_segments(material),upstream_payloads=upstream)
            self.assertEqual(baseline,again)

    def test_two_pass_loading_is_independent_of_declared_module_order(self):
        for module in ('meta_swot','ambiguity_analysis','person_comparison'):
            material,payload,upstream=self.fixture(module,weighted_upstream=True)
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); modules=[]; hashes={}
                for mid,value in {module:payload,**upstream}.items():
                    name=mid+'.json';atomic_json(root/name,value);hashes[name]=file_hash(root/name)
                    modules.append({'id':mid,'args':['--out-json',name],'outputs':[name]})
                manifest={'completed_steps':[m['id'] for m in modules],'output_hashes':hashes}
                atomic_json(root/'workflow_manifest.json',manifest)
                first=load_sources(root,{'pipeline':{'modules':modules}},segments=original_segments(material))
                second=load_sources(root,{'pipeline':{'modules':list(reversed(modules))}},segments=original_segments(material))
                self.assertEqual(first,second)
                self.assertTrue(all(v['status']=='available' for v in first.values()))
                self.assertTrue(all('payload' not in v for v in first.values()))
                snap=make_snapshot(original_segments(material),first)
                self.assertTrue(all(r['valid'] for stage in snap['stages'].values() for r in stage['records']))

    def test_child_run_manifest_hash_and_completion_are_required_for_upstream(self):
        for module in ('meta_swot','ambiguity_analysis','person_comparison'):
            material,payload,upstream=self.fixture(module)
            mid=next(iter(upstream));source=upstream[mid]
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);name=mid+'.json';atomic_json(root/name,source)
                by_id={mid:{'id':mid,'args':['--out-json',name],'outputs':[name]}}
                manifest={'completed_steps':[mid],'output_hashes':{name:file_hash(root/name)}}
                checked=_thematic_upstreams(root,module,payload,by_id,manifest)
                self.assertEqual(checked,upstream)
                for case in ('missing','hash','disabled','not_completed','undeclared'):
                    altered=copy.deepcopy(manifest);modules=copy.deepcopy(by_id)
                    if case=='missing':modules[mid]['outputs']=['absent.json'];modules[mid]['args']=['--out-json','absent.json']
                    if case=='hash':altered['output_hashes'][name]='0'*64
                    if case=='disabled':modules[mid]['enabled']=False
                    if case=='not_completed':altered['completed_steps']=[]
                    if case=='undeclared':modules={}
                    with self.subTest(module=module,case=case),self.assertRaises(ValueError):
                        _thematic_upstreams(root,module,payload,modules,altered)
                # A legacy unweighted output requests no new source contract.
                self.assertEqual(_thematic_upstreams(root,module,{}, {},{}),{})

    def test_invalid_upstream_file_marks_dependent_projection_invalid(self):
        material,payload,upstream=self.fixture('meta_swot')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);modules=[];hashes={}
            for mid,value in {'meta_swot':payload,**upstream}.items():
                name=mid+'.json';atomic_json(root/name,value);hashes[name]=file_hash(root/name)
                modules.append({'id':mid,'outputs':[name]})
            atomic_json(root/'workflow_manifest.json',{'completed_steps':['meta_swot','swot'],'output_hashes':hashes})
            changed=copy.deepcopy(upstream['swot']);changed['created_at']='Changed file';atomic_json(root/'swot.json',changed)
            result=load_sources(root,{'pipeline':{'modules':modules}},segments=original_segments(material))
            self.assertEqual(result['swot']['status'],'invalid')
            self.assertEqual(result['meta_swot']['status'],'invalid')
            self.assertEqual(result['meta_swot']['records'],[])

    def test_stability_uses_each_samples_own_original_sources(self):
        for module in ('meta_swot','person_analysis','ambiguity_analysis','person_comparison'):
            material,payload,upstream=self.fixture(module)
            changed=copy.deepcopy(payload)
            changed['analysis_perspective']['interpretations']['frequency'][0]['interpretation']='Different frequency text'
            samples=[{'sample_id':str(i),'status':'success','payload':value,'upstream_payloads':copy.deepcopy(upstream)}
                     for i,value in enumerate((payload,changed))]
            result=analyze_stage_repetitions(original_segments(material),module,samples)
            self.assertEqual(result['included_samples'],['0','1'])
            self.assertLess(result['pairs'][0]['projected_record_overlap']['value'],1)
            if upstream:
                samples[1].pop('upstream_payloads')
                result=analyze_stage_repetitions(original_segments(material),module,samples)
                self.assertEqual(result['included_samples'],['0'])
                self.assertEqual(result['excluded_samples'],[{'sample_id':'1','reason':'invalid_artifact'}])

    def test_unknown_side_metrics_and_opposite_sides_remain_distinct(self):
        material,payload,upstream=self.fixture('ambiguity_analysis')
        counted=payload['analysis_perspective']['counting'];assignments=copy.deepcopy(counted['assignments'])
        for row in assignments:
            if row['topic_id'].endswith('_A'):row['status']='unclear'
        payload['analysis_perspective']['counting']=count_topics(material,counted['definitions'],assignments)
        stage=project_stage('ambiguity_analysis',payload,segments=original_segments(material),upstream_payloads=upstream)
        counts=[(r['comparison_context'][1],json.loads(r['text'])) for r in stage['records'] if r['kind']=='thematic_counts']
        for tid,count in counts:
            self.assertEqual(count['scope']['person_count'],1)
            if tid.endswith('_A'):self.assertIsNone(count['counts']['mentioned']['exact_person_count'])
            else:self.assertEqual(count['counts']['mentioned']['exact_person_count'],1)

    def test_sensitivity_keeps_same_sample_upstreams_and_new_frequency_features(self):
        material,payload,upstream=self.fixture('meta_swot');changed=copy.deepcopy(payload)
        changed['analysis_perspective']['interpretations']['frequency'][0]['limitations']='New limitation'
        samples=[{'sample_id':f'{cid}-{i}','configuration_id':cid,'status':'success','payload':value,'upstream_payloads':upstream}
                 for cid,value in (('baseline',payload),('variant',changed)) for i in range(2)]
        result=analyze_sensitivity(original_segments(material),[],'meta_swot',
                                  [{'configuration_id':'baseline'},{'configuration_id':'variant'}],samples)
        self.assertTrue(any(r['feature_type']=='exact_projection' and r.get('kind')=='thematic_interpretation' and r['observed_patterns_differ']
                            for r in result['findings']))


if __name__=='__main__':unittest.main()
