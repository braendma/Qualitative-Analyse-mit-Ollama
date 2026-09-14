"""Seven real thematic entrypoints; synthetic inputs and model transport only."""
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

from coding_validation_common import load_segments
from person_analysis_core import normalize_person_analysis
from runtime_support import atomic_json, file_hash
from thematic_material import load_counting_material
from thematic_pipeline import IMPLEMENTED, capability, prepare, finish
from test_thematic_pipeline import ROOT, setup, clean_environment
from test_thematic_adapters import swot
from test_thematic_meta_adapter import meta_from_source
from test_thematic_execution import SyntheticBackend


def extended_setup(root):
    path, cfg, clusters = setup(root)
    cfg['analysis_perspectives'] = {mid: 'both' for mid in IMPLEMENTED}
    for module in cfg['pipeline']['modules']:
        module['enabled'] = module['id'] in IMPLEMENTED
    for key, placeholder in {'meta_swot': '{clusters}', 'person_analysis': '{persons}',
                             'ambiguity_analysis': '{data}', 'person_comparison': '{persons}'}.items():
        cfg['prompts'][key] = {'system': key, 'user': placeholder}
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
    material = load_counting_material(path)
    source = swot(material, clusters)
    atomic_json(root/'swot_v1.json', source)
    texts = {sid: material['units'][row['unit_id']]['text'] for sid, row in material['segment_index'].items()}
    people = {}
    for person in material['persons']:
        ids = sorted(sid for sid, row in material['segment_index'].items()
                     if material['units'][row['unit_id']]['person'] == person)
        normalized = normalize_person_analysis({'zentrale_themen': [{'thema': 'Synthetisches Thema',
            'verdichtung': 'Künstlicher Befund', 'segment_ids': [ids[0]]}],
            'perspektiven': [], 'spannungsfelder': [], 'kontrastierende_aspekte': []}, set(ids), texts)
        people[person] = {'person': person, 'segment_ids': ids, **normalized}
    persons = {'created_at': 'synthetic-person-source', 'persons': people}
    atomic_json(root/'person_analysis_v1.json', persons)
    return path, cfg, clusters, source, persons


class ExtendedThematicBoundaryTests(unittest.TestCase):
    def test_partial_runner_context_cannot_fall_back_to_unverified_standalone_sources(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, clean_environment(), clear=True):
            root=Path(tmp);path,_,_,_,_=extended_setup(root)
            for partial in ({'WORKFLOW_RUN_DIR':str(root)},
                            {'WORKFLOW_INPUT_CSV':str(root/'input.csv')},
                            {'WORKFLOW_RUN_DIR':str(root),'WORKFLOW_INPUT_CSV':str(root/'input.csv')}):
                with patch.dict(os.environ,partial), self.assertRaisesRegex(ValueError,'vollständigen Eingabe- und Laufnachweis'):
                    prepare('meta_swot',path,swot_path=root/'swot_v1.json')

    def test_seven_builtins_have_capabilities_but_custom_scripts_do_not(self):
        self.assertEqual(set(IMPLEMENTED), {'clusterer', 'summarizer', 'swot', 'meta_swot',
                                           'person_analysis', 'ambiguity_analysis', 'person_comparison'})
        for mid in IMPLEMENTED:
            self.assertTrue(capability({'id': mid, 'script': mid+'.py'})['implemented'])
            self.assertFalse(capability({'id': mid, 'script': 'replacement.py'})['implemented'])

    def test_module_specific_sources_are_required_without_irrelevant_cluster_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, clean_environment(), clear=True):
            root=Path(tmp); path, _, _, _, _=extended_setup(root)
            cases = [('person_comparison', {'person_path': root/'person_analysis_v1.json'}),
                     ('meta_swot', {'swot_path': root/'swot_v1.json'}),
                     ('person_analysis', {'cluster_path': root/'clusters_output.json',
                        'idmap_path': root/'id_to_text.json', 'summary_path': root/'summary_v1.json'}),
                     ('ambiguity_analysis', {'idmap_path': root/'id_to_text.json',
                                            'person_path': root/'person_analysis_v1.json'})]
            for mid, args in cases:
                with self.subTest(module=mid):
                    self.assertEqual(prepare(mid, path, **args)['mode'], 'both')
                    for missing in args:
                        with self.assertRaises(ValueError):
                            prepare(mid, path, **{k:v for k,v in args.items() if k != missing})

    def test_foreign_person_or_missing_original_text_is_rejected_before_analysis(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, clean_environment(), clear=True):
            root=Path(tmp); path, _, _, _, people=extended_setup(root)
            args={'person_path':root/'person_analysis_v1.json','idmap_path':root/'id_to_text.json'}
            wrong=copy.deepcopy(people); first=next(iter(wrong['persons'])); wrong['persons'][first]['person']='Foreign'
            atomic_json(args['person_path'],wrong)
            with self.assertRaises(ValueError): prepare('ambiguity_analysis',path,**args)
            atomic_json(args['person_path'],people)
            atomic_json(args['idmap_path'],{})
            with self.assertRaisesRegex(ValueError,'Originaltext-Zuordnung'):
                prepare('ambiguity_analysis',path,**args)

    def test_meta_original_file_is_bound_before_and_after_extension(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, clean_environment(), clear=True):
            root=Path(tmp); path,cfg,_,source,_=extended_setup(root)
            prepared=prepare('meta_swot',path,swot_path=root/'swot_v1.json')
            md,result=finish(prepared,meta_from_source(source),'# Qualitative Ausgangsanalyse',cfg['llm'],llm=SyntheticBackend())
            self.assertEqual(result['analysis_perspective']['selected_mode'],'both')
            self.assertIn('Häufigkeitsinformierte Analyseperspektive',md)
            # Even a change solely in an upstream extension changes the file.
            # Removing it from candidate hashes must not bypass file provenance.
            source['analysis_perspective']={'changed':True}
            atomic_json(root/'swot_v1.json',source)
            llm=SyntheticBackend()
            with self.assertRaisesRegex(ValueError,'Vorstufen wurden'):
                finish(prepared,meta_from_source(source),'# Original',cfg['llm'],llm=llm)
            self.assertEqual(llm.assignment_calls+llm.interpretation_calls,0)

    def test_extra_assignment_prompts_and_context_bounds_cover_all_three_modules(self):
        from prompt_catalog import catalog
        from context_preflight import check_context
        from coding_validation_common import Segment
        with tempfile.TemporaryDirectory() as tmp:
            path,cfg,_,_,_=extended_setup(Path(tmp))
            modules=[m for m in cfg['pipeline']['modules'] if m['enabled']]
            entries={r['id']:r for r in catalog(cfg,modules)['modules']}
            for mid in ('meta_swot','person_analysis','ambiguity_analysis','person_comparison'):
                self.assertTrue(any(row['key']==mid+' / thematic_assignment' for row in entries[mid]['templates']))
                self.assertTrue(any(row['key']==mid+' / frequency_interpretation' for row in entries[mid]['templates']))
            long=Segment('s','Synthetic long original ' * 4000,'A','P','u')
            report=check_context(cfg,[long],{},[m for m in modules if m['id']!='clusterer'])
            self.assertTrue({'meta_swot','person_analysis','ambiguity_analysis','person_comparison'} <= {r['module'] for r in report['blocked']})


class ExtendedThematicProcessTests(unittest.TestCase):
    def test_seven_cli_modules_html_diagnostics_person_scopes_sources_and_resume(self):
        from diagnostic_sources import load_sources
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,cfg,_,_,_=extended_setup(root)
            for module in cfg['pipeline']['modules']:
                if module['id'] in ('coverage','information_loss'):
                    module['enabled']=True
            cfg['paths']['input_csv']='not-the-runner-input.csv'
            path.write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf-8')
            env={**clean_environment(),'PYTHONUTF8':'1','MPLBACKEND':'Agg','MOCK_AMBIGUITY_PAIRS':'1'}
            command=[sys.executable,str(ROOT/'tests/mock_pipeline.py'),'--config',str(path),
                     '--csv',str(root/'input.csv'),'--output-dir',str(root/'runs')]
            completed=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
            self.assertEqual(completed.returncode,0,(completed.stdout+completed.stderr)[-12000:])
            run=next((root/'runs').iterdir()); manifest=json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'],'success')
            self.assertEqual(set(manifest['completed_steps']),set(IMPLEMENTED)|{'coverage','information_loss'})
            for mid,name in [('meta_swot','meta_swot_v1.json'),('person_analysis','person_analysis_v1.json'),
                             ('ambiguity_analysis','ambiguity_analysis_v1.json'),
                             ('person_comparison','person_comparison_v1.json')]:
                payload=json.loads((run/name).read_text(encoding='utf-8'))
                counted=payload['analysis_perspective']['counting']
                self.assertTrue(counted['topics'])
                for topic in counted['topics']:
                    self.assertEqual(topic['counts']['mentioned']['exact_person_count'],12 if mid in ('meta_swot','person_comparison') else 1)
                    self.assertEqual(topic['scope']['person_count'],12 if mid in ('meta_swot','person_comparison') else 1)
            html=(run/'gesamtbericht.html').read_text(encoding='utf-8')
            self.assertIn('nicht die gemeinsame Nennung von A und B',html)
            self.assertIn('innerhalb dieses Falles',html)
            segments=load_segments(root/'input.csv',cfg['columns'])
            sources=load_sources(run,cfg,segments=segments)
            for mid in IMPLEMENTED:
                self.assertEqual(sources[mid]['status'],'available',sources[mid].get('reason'))
                self.assertTrue(any(r['kind']=='thematic_counts' for r in sources[mid]['records']))
            resumed=subprocess.run(command+['--resume',str(run)],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
            self.assertEqual(resumed.returncode,0,(resumed.stdout+resumed.stderr)[-5000:])
            # Downstream meta projection must reject a modified original SWOT;
            # its own successful file and recorded hashes have not changed.
            (run/'swot_v1.json').write_text('{}',encoding='utf-8')
            sources=load_sources(run,cfg,segments=segments)
            self.assertEqual(sources['meta_swot']['status'],'invalid')


if __name__=='__main__': unittest.main()
