import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

from test_codebook_diagnostics import book, single, multi, verify
from test_stability_core import samples
from coding_validation_common import Segment
from stability_core import analyze_coding_repetitions
from sensitivity_core import analyze_sensitivity
from codebook_repetition_links import project_repetition_source, render_repetition_links
from codebook_diagnostics import analyze_snapshot
from test_codebook_diagnostic_loader import Workspace as LoaderWorkspace
from test_diagnostic_repetitions import Workspace, ROOT
from runtime_support import atomic_json, file_hash


def source(segments, codebook, *payloads, mid='blind_coding', mode='single_label'):
    comparison=analyze_coding_repetitions(segments,codebook,mid,samples(*payloads),label_mode=mode)
    comparison['provenance_status']='series_and_artifact_hashes_verified'
    return {'schema_version':1,'kind':'stability','processing_status':comparison['processing_status'],
            'comparisons':{mid:comparison}}


def sensitivity(segments, codebook, baseline, variant):
    configurations=[{'configuration_id':'baseline'},{'configuration_id':'variant'}]
    observations=[]
    for config, values in zip(configurations,(baseline,variant)):
        for i,payload in enumerate(values):
            observations.append({'sample_id':config['configuration_id']+str(i),
                'configuration_id':config['configuration_id'],'status':'success','payload':payload})
    comparison=analyze_sensitivity(segments,codebook,'blind_coding',configurations,observations)
    for within in comparison['within_configurations'].values():within['provenance_status']='series_and_artifact_hashes_verified'
    return {'schema_version':1,'kind':'sensitivity','processing_status':comparison['processing_status'],
        'comparisons':{'blind_coding':comparison},'configurations':configurations}


class RepetitionLinkTests(unittest.TestCase):
    def setUp(self):
        self.segments=[Segment('s1','Original <script> & Text','A','P1'),Segment('s2','Anderer Text','B','P2')]
        self.book=[book('A'),book('B')]

    def test_swapped_assignments_are_visible_despite_equal_total_frequencies(self):
        a,b=single(self.segments,['A','B']),single(self.segments,['B','A'])
        result=project_repetition_source(source(self.segments,self.book,a,b),'stability',self.segments,self.book,'single_label')
        row=result['modules'][0]['categories'][0]['within_configurations'][0]
        self.assertEqual((row['variable_units'],row['comparable_units']),(2,2))
        self.assertEqual([s['units'] for s in row['per_sample']],[1,1])
        report='\n'.join(render_repetition_links({'stability':{**result,'artifact':'custom.json'}}))
        self.assertIn('Original &lt;script&gt;',report)
        self.assertNotIn('<script>',report)

    def test_within_and_between_configuration_variation_are_separate(self):
        a,b=single(self.segments,['A','A']),single(self.segments,['B','B'])
        result=project_repetition_source(sensitivity(self.segments,self.book,[a,a],[b,b]),'sensitivity',self.segments,self.book,'single_label')
        row=result['modules'][0]['categories'][0]
        self.assertTrue(all(c['variable_units']==0 for c in row['within_configurations']))
        self.assertEqual((row['between_configuration_differing_units'],row['between_configuration_comparable_units']),(2,2))
        equal=project_repetition_source(sensitivity(self.segments,self.book,[a,b],[a,b]),'sensitivity',self.segments,self.book,'single_label')
        row=equal['modules'][0]['categories'][0]
        self.assertEqual(row['between_configuration_differing_units'],0)
        self.assertTrue(all(c['variable_units']==2 for c in row['within_configurations']))

    def test_abstention_and_technical_failure_are_not_code_absence(self):
        a=single(self.segments,['A','A']);abstain=single(self.segments,['unklar','unklar'])
        failed=copy.deepcopy(a)
        for row in failed['results']:row['processing_status']='failed'
        result=project_repetition_source(source(self.segments,self.book,a,abstain,failed),'stability',self.segments,self.book,'single_label')
        row=result['modules'][0]['categories'][0]['within_configurations'][0]
        self.assertEqual(row['comparable_units'],0)
        self.assertEqual(row['variable_units'],0)
        self.assertEqual([x['evaluated_units'] for x in row['per_sample']],[2,0,0])

    def test_multi_label_counts_one_passage_not_its_coding_rows(self):
        segments=[Segment('x','Gleich','A','P',unit_id='u'),Segment('y','Gleich','B','P',unit_id='u')]
        a=multi(segments,{'u':(['A'],'assigned')});b=multi(segments,{'u':(['B'],'assigned')})
        result=project_repetition_source(source(segments,self.book,a,b,mode='multi_label'),'stability',segments,self.book,'multi_label')
        self.assertEqual(result['modules'][0]['categories'][0]['within_configurations'][0]['variable_units'],1)
        self.assertEqual(result['modules'][0]['unit_kind'],'passage')

    def test_foreign_codes_persons_and_unbound_comparisons_are_rejected(self):
        a=single(self.segments,['A','B']);valid=source(self.segments,self.book,a,a)
        for field,value in [('person','foreign'),('segment_ids',['foreign'])]:
            bad=copy.deepcopy(valid);bad['comparisons']['blind_coding']['units'][0][field]=value
            with self.assertRaises(ValueError):project_repetition_source(bad,'stability',self.segments,self.book,'single_label')
        bad=copy.deepcopy(valid);bad['comparisons']['blind_coding']['units'][0]['observations']['repeat-0']['codes']=['foreign']
        with self.assertRaises(ValueError):project_repetition_source(bad,'stability',self.segments,self.book,'single_label')
        bad=copy.deepcopy(valid);bad['comparisons']['blind_coding']['provenance_status']='caller_must_verify'
        with self.assertRaises(ValueError):project_repetition_source(bad,'stability',self.segments,self.book,'single_label')
        self.assertEqual(project_repetition_source({'schema_version':1,'kind':'stability','comparisons':{}},'stability',self.segments,self.book,'single_label')['status'],'no_coding_comparison')

    def test_loader_uses_declared_current_bound_artifact_and_preserves_base_hints_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=LoaderWorkspace(Path(tmp));payload=source(w.segments,w.codes,single(w.segments,['A','B']),single(w.segments,['B','A']))
            payload['source_provenance']=dict(w.manifest['provenance'])
            w.cfg['pipeline']['modules'].append({'id':'stability','enabled':True,'args':['--out-json','alternate-repeat.json'],'outputs':['alternate-repeat.json']})
            w.config.write_text(yaml.safe_dump(w.cfg),encoding='utf-8')
            w.manifest['provenance']['config_sha256']=file_hash(w.config)
            w.manifest['completed_steps'].append('stability');w.manifest['module_status']['stability']='success'
            def write():
                atomic_json(w.root/'alternate-repeat.json',payload)
                w.manifest['output_hashes']['alternate-repeat.json']=file_hash(w.root/'alternate-repeat.json');w.save_manifest()
            write();result=analyze_snapshot(w.load())
            self.assertEqual(result['repetition_diagnostics']['stability']['status'],'available')
            payload['source_provenance']['input_sha256']='foreign';write()
            result=analyze_snapshot(w.load());self.assertEqual(result['processing_status'],'incomplete')
            self.assertEqual(result['repetition_diagnostics']['stability']['status'],'invalid')
            self.assertEqual(result['categories'][0]['human_units'],1)
            w.cfg['pipeline']['modules'][-1]['enabled']=False;w.config.write_text(yaml.safe_dump(w.cfg),encoding='utf-8')
            w.manifest['provenance']['config_sha256']=file_hash(w.config);w.save_manifest()
            self.assertEqual(analyze_snapshot(w.load())['processing_status'],'completed')


class RepetitionLinkIntegrationTests(unittest.TestCase):
    def test_both_series_finish_before_codebook_without_extra_model_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            diagnostics={'coverage','information_loss','stability','sensitivity','codebook_diagnostics'}
            selected={'clusterer','blind_coding',*diagnostics}
            for m in w.config['pipeline']['modules']:m['enabled']=m['id'] in selected
            w.config['diagnostics']={'stability':{'modules':['blind_coding'],'repetitions':2},
                'sensitivity':{'modules':['blind_coding'],'repetitions':2,'variants':[{'id':'warm','llm':{'temperature':.2}}]}}
            w.save();output=w.root/'runs'
            input_hashes={name:file_hash(w.root/name) for name in ('input.csv','book.csv','base.yaml')}
            command=[sys.executable,str(ROOT/'tests/mock_pipeline.py'),'--config',str(w.path),'--output-dir',str(output)]
            trace=w.root/'requests.jsonl'
            env={**os.environ,'PYTHONUTF8':'1','MOCK_RUNTIME_EVIDENCE':'1','MOCK_TRACE_PATH':str(trace)}
            done=subprocess.run(command,
                capture_output=True,text=True,encoding='utf-8',timeout=70,
                env=env)
            self.assertEqual(done.returncode,0,done.stderr[-3000:])
            run=next(output.iterdir());result=json.loads((run/'codebook_diagnostics.json').read_text(encoding='utf-8'))
            self.assertEqual(result['processing_status'],'completed')
            for kind in ('stability','sensitivity'):self.assertEqual(result['repetition_diagnostics'][kind]['status'],'available')
            manifest=json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'],'success')
            self.assertEqual(set(manifest['completed_steps']),selected)
            self.assertEqual(manifest['completed_steps'][-1],'codebook_diagnostics')
            self.assertEqual(result['model_calls'],0)
            html=(run/'gesamtbericht.html').read_text(encoding='utf-8')
            self.assertIn('Hinweise aus kontrollierten Wiederholungen',html)
            for mid in diagnostics:
                module=w.module(mid)
                self.assertEqual(manifest['module_status'][mid],'success')
                for name in module['outputs']:
                    self.assertEqual(file_hash(run/name),manifest['output_hashes'][name])
                    if name.endswith('.json'):
                        self.assertEqual(json.loads((run/name).read_text(encoding='utf-8'))['processing_status'],'completed')
                self.assertIn(module['report']['title'],html)
                self.assertIn(module['report']['title'],(run/'gesamtbericht.md').read_text(encoding='utf-8'))
            child_manifests=list(run.glob('_*repetitions/*/*/workflow_manifest.json'))
            self.assertEqual(len(child_manifests),6)
            self.assertEqual(len({json.loads(p.read_text(encoding='utf-8'))['run_id'] for p in child_manifests}),6)
            self.assertTrue((run/'_stability_repetitions').is_dir())
            self.assertTrue((run/'_sensitivity_repetitions').is_dir())
            requests=trace.read_bytes()
            resumed=subprocess.run(command+['--resume',str(run)],capture_output=True,text=True,
                encoding='utf-8',timeout=70,env=env)
            self.assertEqual(resumed.returncode,0,resumed.stderr[-3000:])
            self.assertEqual(trace.read_bytes(),requests,'Resume repeated completed model work')
            self.assertEqual({name:file_hash(w.root/name) for name in input_hashes},input_hashes)
            self.assertEqual(json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))['status'],'success')


if __name__=='__main__':unittest.main()
