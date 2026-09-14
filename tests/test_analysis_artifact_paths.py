"""Managed run artifacts stay bound to their run even with another process cwd."""
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import matplotlib
matplotlib.use('Agg')
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from filesystem_paths import canonical_path, io_path
from runtime_support import artifact_reference


SOURCE = Path(__file__).resolve().parents[1] / 'src'
IMPORT_LOGS = ('clusterer', 'summarizer', 'swot', 'meta_swot', 'person_analysis',
               'person_comparison', 'contrast_analysis', 'relation_analysis',
               'ambiguity_analysis', 'overall_synthesis', 'evidence_audit')


def load_entry(name):
    spec = importlib.util.spec_from_file_location('_artifact_test_' + name, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AnalysisArtifactPathTests(unittest.TestCase):
    def test_import_log_handlers_bind_to_run_and_keep_standalone_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            for root in ('', tmp):
                for name in IMPORT_LOGS:
                    with self.subTest(root=bool(root), module=name), \
                         patch.dict(os.environ, {'WORKFLOW_RUN_DIR': root}), \
                         patch('logging.FileHandler') as handler, patch('logging.basicConfig'):
                        load_entry(name)
                        requested = handler.call_args.args[0]
                        if root:
                            self.assertEqual(canonical_path(requested), Path(root).resolve() / (name + '_debug.log'))
                        else:
                            self.assertEqual(requested, Path(name + '_debug.log'))

    def test_configurable_logs_keep_absolute_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'; root.mkdir()
            absolute = Path(tmp) / 'selected.log'
            for name in ('code_verification', 'blind_coding', 'coding_agreement'):
                module = load_entry(name)
                for value, expected in [('custom.log', root / 'custom.log'), (str(absolute), absolute)]:
                    with self.subTest(module=name, value=value), \
                         patch.dict(os.environ, {'WORKFLOW_RUN_DIR': str(root)}), \
                         patch('logging.FileHandler') as handler, patch('logging.basicConfig'):
                        module.configure_logging(value)
                        self.assertEqual(canonical_path(handler.call_args.args[0]), expected.resolve())

    def test_raw_audit_and_checkpoint_defaults_and_explicit_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = root / 'run'; run.mkdir()
            config = root / 'config.yaml'
            for name, function in [('code_verification', 'verify_segments'), ('blind_coding', 'blind_code_segments')]:
                module = load_entry(name)
                for enabled, checkpoint in [(True, None), (False, None), (False, str(root / 'explicit.json'))]:
                    config.write_text(json.dumps({'coding_validation': {
                        'log_raw_llm_output': enabled, 'checkpoint': enabled}}), encoding='utf-8')
                    with self.subTest(module=name, enabled=enabled, override=checkpoint), ExitStack() as stack:
                        stack.enter_context(patch.dict(os.environ, {'WORKFLOW_RUN_DIR': str(run)}))
                        for attr in ('configure_logging', 'atomic_json', 'atomic_text'):
                            stack.enter_context(patch.object(module, attr))
                        stack.enter_context(patch.object(module, 'load_segments', return_value=[]))
                        stack.enter_context(patch.object(module, 'load_codebook', return_value=([], {})))
                        stack.enter_context(patch.object(module, 'resolve_config_path', return_value=root / 'book.csv'))
                        execute = stack.enter_context(patch.object(module, function, return_value=('', {})))
                        args = ['--config', str(config)] + (['--checkpoint', checkpoint] if checkpoint else [])
                        module.main.__wrapped__(args)
                        kwargs = execute.call_args.kwargs
                        if enabled:
                            self.assertEqual(canonical_path(kwargs['raw_log_path']), canonical_path(run / (name + '_raw.jsonl')))
                        else:
                            self.assertIsNone(kwargs['raw_log_path'])
                        if checkpoint or enabled:
                            self.assertEqual(canonical_path(kwargs['checkpoint_path']),
                                             canonical_path(Path(checkpoint) if checkpoint else run / (name + '_checkpoint.json')))
                        else:
                            self.assertIsNone(kwargs['checkpoint_path'])

    def test_plot_reference_is_relative_and_html_embeds_svg_from_subdirectory(self):
        from plot_core import plot_clusters
        from html_report import build_html_report
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WORKFLOW_RUN_DIR': tmp}):
            root = Path(tmp); plots = root / 'plots'; plots.mkdir()
            frame = pd.DataFrame([{'_SegmentID': 'SYN-1', 'Dokumentname': 'SYN-P01'}])
            ref = plot_clusters('Synthetic', 'Factor', [{'cluster_name': 'Finding', 'segments': ['SYN-1']}],
                                frame, out_dir=io_path(plots))
            self.assertEqual(ref, 'plots/Synthetic_Factor_clusterdiagramm.png')
            self.assertTrue((root / ref).is_file())
            self.assertTrue((root / ref).with_suffix('.svg').is_file())
            (root / 'report.md').write_text(f'![Plot]({ref})\n', encoding='utf-8')
            report = build_html_report(root, [{'id': 'clusterer', 'name': 'Cluster', 'report': {'markdown': 'report.md'}}], 'synthetic')
            data = json.loads(re.search('id="report-data">(.*?)</script>', report.read_text(encoding='utf-8'), re.S)[1])
            self.assertTrue(data['images'])
            self.assertTrue(all(image.startswith('data:image/svg+xml;base64,') for image in data['images'].values()))
            self.assertFalse(data['warnings'])

    def test_agreement_keeps_subdirectory_in_managed_report_and_standalone_basename(self):
        from coding_agreement_core import calculate_agreement
        with tempfile.TemporaryDirectory() as tmp:
            path = io_path(Path(tmp) / 'plots' / 'confusion.png')
            for root, expected in [(tmp, 'plots/confusion.png'), ('', 'confusion.png')]:
                with self.subTest(managed=bool(root)), patch.dict(os.environ, {'WORKFLOW_RUN_DIR': root}), \
                     patch('coding_agreement_core.save_confusion_png', return_value=True):
                    md, output = calculate_agreement([], [], {'results': []}, {'results': []}, confusion_png=path)
                    self.assertEqual(output['confusion_png'], expected)
                    self.assertIn('](' + expected + ')', md)

    def test_artifact_reference_preserves_outside_target_and_standalone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'; root.mkdir()
            external = Path(tmp) / 'external.png'
            with patch.dict(os.environ, {'WORKFLOW_RUN_DIR': str(root)}):
                self.assertEqual(artifact_reference(str(external)), str(external))
            with patch.dict(os.environ, {'WORKFLOW_RUN_DIR': ''}):
                self.assertEqual(artifact_reference('plots/example.png'), 'plots/example.png')

    def test_relation_receipt_binds_absolute_source_against_run_not_process_cwd(self):
        from thematic_pipeline import _relation_receipt_needed
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WORKFLOW_RUN_DIR': tmp}):
            config = {'pipeline': {'modules': [
                {'id': 'relation_analysis', 'script': 'relation_analysis.py', 'outputs': ['relation.json']},
                {'id': 'overall_synthesis', 'script': 'overall_synthesis.py',
                 'args': ['--source-json', 'Relation=' + str(io_path(Path(tmp) / 'relation.json'))]}
            ]}}
            self.assertTrue(_relation_receipt_needed(config, {'overall_synthesis': 'frequency'}))


if __name__ == '__main__':
    unittest.main()
