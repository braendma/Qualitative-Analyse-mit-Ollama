"""Real entrypoints, project saving and source-bound opt-in preparation."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

from thematic_material import load_counting_material
from thematic_pipeline import modes, capability, prepare, finish
from runtime_support import atomic_json, file_hash
from test_thematic_material import workspace
from test_thematic_adapters import summary
from test_thematic_execution import SyntheticBackend

ROOT = Path(__file__).resolve().parents[1]


def setup(root, mode='both'):
    path, cfg = workspace(root)
    defaults = yaml.safe_load((ROOT/'config/config_v2.yaml').read_text(encoding='utf-8'))
    for key in ('llm', 'prompts', 'pipeline', 'coding_agreement', 'context'):
        cfg[key] = defaults[key]
    cfg['llm'].update(model='mock', max_tokens=2048, num_ctx=32768, partial_checkpoints=False)
    cfg['context'] = {}
    cfg['analysis_perspectives'] = {m:mode for m in ('clusterer','summarizer','swot')}
    for module in cfg['pipeline']['modules']:
        module['enabled'] = module['id'] in cfg['analysis_perspectives']
    for key, placeholder in {'cluster_analysis':'{segments}', 'cluster_summary':'{clusters}',
                             'category_summary':'{subcats}', 'swot_analysis':'{clusters}'}.items():
        cfg['prompts'][key] = {'system':key, 'user':placeholder}
    path.write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf-8')
    material = load_counting_material(path)
    clusters = {'processing_status':'completed', 'clusters':[{'code_path':'A', 'cluster_name':'Synthetic',
                'definition':'Gemeinsame künstliche Gruppe', 'segments':sorted(material['segment_index'])}],
                'segment_metadata':{sid:{'person':material['units'][row['unit_id']]['person'],
                                        'unit_id':row['unit_id'][len('passage:'):]}
                                    for sid,row in material['segment_index'].items()}}
    mapping = {sid:material['units'][row['unit_id']]['text'] for sid,row in material['segment_index'].items()}
    atomic_json(root/'clusters_output.json',clusters)
    atomic_json(root/'id_to_text.json',mapping)
    atomic_json(root/'summary_v1.json',summary(clusters))
    return path,cfg,clusters


def clean_environment():
    return {k:v for k,v in os.environ.items() if not k.startswith(('WORKFLOW_', 'MOCK_'))}


class ThematicPipelineBoundaryTests(unittest.TestCase):
    def test_capability_cannot_be_enabled_by_config_or_reused_custom_script_id(self):
        self.assertTrue(capability({'id':'swot','script':'swot.py'})['implemented'])
        self.assertFalse(capability({'id':'swot','script':'custom.py'})['implemented'])
        with self.assertRaises(ValueError):
            modes({'analysis_perspectives':{'swot':'both'}, 'pipeline':{'modules':[{'id':'swot','script':'custom.py'}]}})
        with self.assertRaises(ValueError):
            modes({'analysis_perspectives':{'overall_synthesis':'both'}, 'implemented_modules':['overall_synthesis']})

    def test_default_does_not_require_new_person_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,clean_environment(),clear=True):
            path,cfg,_=setup(Path(tmp),'qualitative');cfg.pop('person_identity')
            path.write_text(yaml.safe_dump(cfg),encoding='utf-8')
            self.assertIsNone(prepare('clusterer',path))
            cfg['analysis_perspectives']['clusterer']='both'
            path.write_text(yaml.safe_dump(cfg),encoding='utf-8')
            with self.assertRaises(ValueError):prepare('clusterer',path)

    def test_idmap_and_source_validation_happen_before_model_work(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,clean_environment(),clear=True):
            root=Path(tmp);path,_,_=setup(root)
            args={'cluster_path':root/'clusters_output.json','idmap_path':root/'id_to_text.json'}
            self.assertEqual(prepare('summarizer',path,**args)['mode'],'both')
            mapping=json.loads(args['idmap_path'].read_text());mapping.pop(next(iter(mapping)))
            atomic_json(args['idmap_path'],mapping)
            with self.assertRaisesRegex(ValueError,'Originaltext-Zuordnung'):prepare('summarizer',path,**args)

    def test_manifest_requires_same_source_input_and_complete_predecessor(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,clean_environment(),clear=True):
            root=Path(tmp);path,cfg,_=setup(root)
            args={'cluster_path':root/'clusters_output.json','idmap_path':root/'id_to_text.json'}
            cfg['paths']['input_csv']='missing-configured-input.csv'
            path.write_text(yaml.safe_dump(cfg),encoding='utf-8')
            manifest={'fingerprint':'synthetic-run','provenance':{'config_sha256':file_hash(path),
                'input_sha256':file_hash(root/'input.csv'),'codebook_sha256':file_hash(root/'book.csv')},
                'completed_steps':['clusterer'], 'output_hashes':{name:file_hash(root/name)
                    for name in ('clusters_output.json','id_to_text.json')}}
            atomic_json(root/'workflow_manifest.json',manifest)
            os.environ.update(WORKFLOW_FINGERPRINT='synthetic-run',WORKFLOW_RUN_DIR=str(root),WORKFLOW_INPUT_CSV=str(root/'input.csv'))
            prepared=prepare('summarizer',path,**args)
            self.assertEqual(prepared['material']['counts']['persons'],12)
            manifest['completed_steps']=[];atomic_json(root/'workflow_manifest.json',manifest)
            with self.assertRaises(ValueError):prepare('summarizer',path,**args)
            (root/'workflow_manifest.json').unlink()
            with self.assertRaises(FileNotFoundError):prepare('summarizer',path,**args)

    def test_changed_source_blocks_final_output_and_unchanged_candidates_survive(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,clean_environment(),clear=True):
            root=Path(tmp);path,cfg,clusters=setup(root)
            prepared=prepare('clusterer',path)
            original=copy.deepcopy(clusters)
            md,result=finish(prepared,clusters,'# Original',cfg['llm'],llm=SyntheticBackend())
            self.assertEqual(clusters,original)
            self.assertEqual(result['clusters'],original['clusters'])
            self.assertIn('Häufigkeitsinformierte Analyseperspektive',md)
            (root/'input.csv').write_bytes((root/'input.csv').read_bytes()+b'\n')
            with self.assertRaises(ValueError):finish(prepared,clusters,'# Original',cfg['llm'],llm=SyntheticBackend())

    def test_app_preserves_modes_validation_effort_and_rejects_unsupported_values(self):
        from local_app import App
        from test_local_app import settings
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetic',True)['id'];opts=settings(app)
            opts['analysis_perspectives']={'summarizer':'both','swot':'frequency'}
            checked=app.save(pid,opts)
            project=app.project(pid)
            cfg=yaml.safe_load((app.project_dir(pid)/'revisions'/project['revision']/'config.yaml').read_text(encoding='utf-8'))
            self.assertEqual(cfg['analysis_perspectives'],opts['analysis_perspectives'])
            self.assertEqual(checked['effort']['analysis_perspectives']['shared_assignment_bases'],1)
            bad=copy.deepcopy(opts);bad['analysis_perspectives']['overall_synthesis']='both'
            with self.assertRaises(ValueError):app.save(pid,bad)
            self.assertEqual(app.project(pid)['revision'],project['revision'])

    def test_prompt_catalog_and_preflight_show_real_additional_instructions(self):
        from prompt_catalog import catalog
        from context_preflight import check_context
        with tempfile.TemporaryDirectory() as tmp:
            _,cfg,_=setup(Path(tmp))
            modules=[m for m in cfg['pipeline']['modules'] if m['enabled']]
            prompts=catalog(cfg,modules)
            swot=next(m for m in prompts['modules'] if m['id']=='swot')
            self.assertTrue(any(t['key']=='swot / thematic_assignment' for t in swot['templates']))
            self.assertTrue(any(t['key']=='swot / frequency_interpretation' for t in swot['templates']))
            report=check_context(cfg,[],{},modules)
            self.assertTrue(any('Zählregister' in note for note in report['warnings']))


class ThematicPipelineProcessTests(unittest.TestCase):
    def test_real_three_module_clis_runner_html_provenance_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,cfg,_=setup(root)
            # Exercise runner CSV override: stored config path intentionally absent.
            for module in cfg['pipeline']['modules']:
                if module['id'] in ('coverage', 'information_loss'):
                    module['enabled'] = True
            cfg['paths']['input_csv']='different-input.csv'
            path.write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf-8')
            env={**clean_environment(),'MPLBACKEND':'Agg','PYTHONUTF8':'1'}
            command=[sys.executable,str(ROOT/'tests/mock_pipeline.py'),'--config',str(path),
                     '--csv',str(root/'input.csv'),'--output-dir',str(root/'runs')]
            result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=100)
            self.assertEqual(result.returncode,0,(result.stdout+result.stderr)[-10000:])
            run=next((root/'runs').iterdir());manifest=json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'],'success')
            self.assertEqual(set(manifest['completed_steps']),{'clusterer','summarizer','swot','coverage','information_loss'})
            for name in ('clusters_output.json','summary_v1.json','swot_v1.json'):
                payload=json.loads((run/name).read_text(encoding='utf-8'))
                self.assertEqual(payload['analysis_perspective']['selected_mode'],'both')
                self.assertTrue(all(t['counts']['mentioned']['exact_person_count']==12
                                    for t in payload['analysis_perspective']['counting']['topics']))
            self.assertIn('Häufigkeitsinformierte Analyseperspektive',(run/'gesamtbericht.html').read_text(encoding='utf-8'))
            resumed=subprocess.run(command+['--resume',str(run)],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=100)
            self.assertEqual(resumed.returncode,0,(resumed.stdout+resumed.stderr)[-5000:])


if __name__=='__main__':unittest.main()
