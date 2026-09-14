import copy
from contextlib import chdir
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

from thematic_pipeline import prepare, finish, IMPLEMENTED
from test_thematic_extended_pipeline import extended_setup
from test_thematic_pipeline import ROOT, clean_environment
from test_thematic_synthesis_execution import SynthesisBackend
from overall_synthesis_core import build_overall_synthesis


def setup_sources(root):
    path, cfg, *_ = extended_setup(root)
    cfg['analysis_perspectives'] = {mid: 'qualitative' for mid in IMPLEMENTED}
    cfg['analysis_perspectives']['overall_synthesis'] = 'both'
    sources = {'First alias': 'summary_v1.json', 'Second alias': 'clusters_output.json'}
    module = next(m for m in cfg['pipeline']['modules'] if m['id'] == 'overall_synthesis')
    module['args'] = ['--config', '{config}', '--source-json=First alias=summary_v1.json',
                      '--source-json', 'Second alias=clusters_output.json', '--out-json', 'overall_synthesis_v1.json']
    module['depends_on'] = ['clusterer', 'summarizer']
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
    return path, cfg, sources


class SynthesisBoundaryTests(unittest.TestCase):
    def test_prepare_binds_actual_sources_and_finish_rejects_changed_file(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, clean_environment(), clear=True):
            root = Path(temp); path, cfg, sources = setup_sources(root)
            with chdir(root):
                prepared = prepare('overall_synthesis', path, source_paths=sources)
                self.assertEqual(set(prepared['source_upstreams']), {'clusterer', 'summarizer'})
                self.assertEqual(prepared['source_bindings']['First alias']['module_id'], 'summarizer')
                (root/'summary_v1.json').write_text('{}', encoding='utf-8')
                llm = SynthesisBackend()
                with self.assertRaisesRegex(ValueError, 'Vorstufen wurden'):
                    finish(prepared, {}, '# Original', cfg['llm'], llm=llm)
                self.assertEqual(llm.selection_calls, 0)

    def test_wrong_alias_foreign_file_or_missing_upstream_fails_before_core(self):
        for change in ('alias', 'file', 'upstream'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, clean_environment(), clear=True):
                root = Path(temp); path, cfg, sources = setup_sources(root)
                if change == 'alias': sources['Changed alias'] = sources.pop('First alias')
                elif change == 'file': sources['First alias'] = 'unknown.json'
                else: (root/'clusters_output.json').write_text('{}', encoding='utf-8')
                with chdir(root), self.assertRaises(ValueError):
                    prepare('overall_synthesis', path, source_paths=sources)

    def test_relation_only_prepares_provenance_when_synthesis_really_uses_it(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, clean_environment(), clear=True):
            root = Path(temp); path, cfg, _ = setup_sources(root)
            args = {'cluster_path': root/'clusters_output.json', 'idmap_path': root/'id_to_text.json',
                    'summary_path': root/'summary_v1.json'}
            with chdir(root):
                self.assertIsNone(prepare('relation_analysis', path, **args))
                synth = next(m for m in cfg['pipeline']['modules'] if m['id'] == 'overall_synthesis')
                synth['args'] += ['--source-json', 'Relation=relation_analysis_v1.json']
                path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
                prepared = prepare('relation_analysis', path, **args)
                self.assertEqual(prepared['mode'], 'qualitative')
                self.assertEqual(prepared['material']['counts']['persons'], 12)
                llm = SynthesisBackend()
                original = {'untouched': True}
                self.assertEqual(finish(prepared, original, '# Original', cfg['llm'], llm=llm), ('# Original', original))
                self.assertEqual(llm.selection_calls + llm.assignment_calls + llm.interpretation_calls, 0)

    def test_synthesis_only_frequency_real_cli_including_qualitative_relation_audit_and_resume(self):
        from diagnostic_sources import load_sources
        from coding_validation_common import load_segments
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path, cfg, *_ = extended_setup(root)
            cfg['analysis_perspectives'] = {mid: 'qualitative' for mid in IMPLEMENTED}
            cfg['analysis_perspectives']['overall_synthesis'] = 'both'
            for module in cfg['pipeline']['modules']:
                if module['id'] == 'evidence_audit': module['enabled'] = True
                if module['id'] == 'overall_synthesis':
                    module['depends_on'].append('evidence_audit')
                    module['args'] += ['--source-json', 'Audit=evidence_audit_v1.json']
            cfg['prompts']['evidence_audit'] = {'system': 'evidence_audit', 'user': '{data}'}
            path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
            env = {**clean_environment(), 'PYTHONUTF8': '1', 'MPLBACKEND': 'Agg',
                   'MOCK_AMBIGUITY_PAIRS': '1', 'MOCK_CONTRAST_PATTERNS': '1'}
            command = [sys.executable, str(ROOT/'tests/mock_pipeline.py'), '--config', str(path),
                       '--csv', str(root/'input.csv'), '--output-dir', str(root/'runs')]
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)
            self.assertEqual(result.returncode, 0, (result.stdout+result.stderr)[-15000:])
            run = next((root/'runs').iterdir())
            relation = json.loads((run/'relation_analysis_v1.json').read_text(encoding='utf-8'))
            self.assertNotIn('analysis_perspective', relation)
            self.assertEqual(relation['selection_provenance']['verification_level'], 'confirmed_original_material')
            synthesis = json.loads((run/'overall_synthesis_v1.json').read_text(encoding='utf-8'))
            self.assertEqual(synthesis['analysis_perspective']['counting']['topics'][0]['scope']['person_count'], 12)
            self.assertIn('nicht menschlich bestätigt', (run/'gesamtbericht.html').read_text(encoding='utf-8'))
            sources = load_sources(run, cfg, segments=load_segments(root/'input.csv', cfg['columns']))
            self.assertEqual(sources['overall_synthesis']['status'], 'available', sources['overall_synthesis'].get('reason'))
            resumed = subprocess.run(command+['--resume', str(run)], cwd=root, env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)
            self.assertEqual(resumed.returncode, 0, (resumed.stdout+resumed.stderr)[-5000:])


if __name__ == '__main__': unittest.main()
