"""Synthesis diagnostics use actual configuration aliases and child artifacts."""
import copy
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from diagnostic_sources import project_stage, load_sources, make_snapshot, synthesis_contract_bindings
from runtime_support import atomic_json, file_hash
from stability_core import analyze_stage_repetitions
from stability_series import _thematic_upstreams
from thematic_execution import execute_perspective
from test_thematic_case_projection import original_segments
from test_thematic_execution import SyntheticBackend
from test_thematic_synthesis_adapter import synthesis_fixture


def projection_fixture(*, reduced=False):
    material, payload, sources, _, bindings, upstream = synthesis_fixture(reduced=reduced)
    modules = [{'id': mid, 'script': mid + '.py', 'enabled': True,
                'args': ['--out-json', mid + '.json'], 'outputs': [mid + '.json']}
               for mid in ('overall_synthesis', 'summarizer', 'clusterer')]
    modules[0]['args'] += ['--source-json', 'First alias=summarizer.json',
                           '--source-json', 'Second alias=clusterer.json']
    for binding in bindings.values():
        binding['artifact'] = binding['module_id'] + '.json'
    backend = SyntheticBackend()
    def llm(messages, params):
        data, _ = json.JSONDecoder().raw_decode(messages[1]['content'])
        if 'candidate' in data:
            item = data['candidate']
            return json.dumps({'candidate_id': item['candidate_id'],
                'classification': 'material_assertion' if item['original_record']['thema'] == 'Planbarkeit' else 'group_comparison',
                'reason': 'Synthetisch festgelegte Klassifikation.'})
        return backend(messages, params)
    extension = execute_perspective('overall_synthesis', 'both', material, payload,
        {'model': 'synthetic', 'num_ctx': 32768, 'max_tokens': 1500,
         'partial_checkpoints': False, 'parallel_workers': 1},
        source_payloads=sources, source_bindings=bindings, source_upstreams=upstream, llm=llm)
    contract = {'module': modules[0], 'modules': modules, 'directory': Path.cwd()}
    return material, {**payload, 'analysis_perspective': extension}, upstream, contract


class SynthesisProjectionTests(unittest.TestCase):
    def setUp(self):
        for name in ('analysis_work.update_progress', 'runtime_context.update_progress',
                     'thematic_interpretation.begin_phase'):
            handle = patch(name); handle.start(); self.addCleanup(handle.stop)

    def project(self, args):
        material, payload, upstream, contract = args
        return project_stage('overall_synthesis', payload, segments=original_segments(material),
                             upstream_payloads=upstream, source_contract=contract)

    def test_actual_reduced_and_unreduced_outputs_project_without_fake_evidence(self):
        for reduced in (False, True):
            args = projection_fixture(reduced=reduced); before = copy.deepcopy(args)
            result = self.project(args)
            rows = [row for row in result['records'] if row['scope'] == 'thematic_result']
            self.assertEqual({row['kind'] for row in rows},
                             {'thematic_interpretation', 'thematic_counts', 'thematic_selection'})
            self.assertTrue(all(not row['segment_ids'] and not row['persons'] for row in rows))
            decisions = [row for row in rows if row['kind'] == 'thematic_selection']
            self.assertTrue(any('group_comparison' in row['text'] for row in decisions))
            snap = make_snapshot(original_segments(args[0]), {'overall_synthesis': {**result, 'status': 'available'}})
            self.assertTrue(all(row['valid'] for row in snap['stages']['overall_synthesis']['records']))
            self.assertEqual(args, before)

    def test_missing_or_forged_contract_and_embedded_provenance_fail(self):
        original = projection_fixture()
        for case in ('missing', 'alias', 'binding', 'disabled', 'script', 'provenance', 'checked', 'transitive', 'selection', 'counts'):
            material, payload, upstream, contract = copy.deepcopy(original)
            extension = payload['analysis_perspective']
            if case == 'missing': contract = None
            if case == 'alias': contract['module']['args'][-1] = 'Forged alias=clusterer.json'
            if case == 'binding': extension['synthesis_source_bindings']['First alias']['module_id'] = 'clusterer'
            if case == 'disabled': contract['modules'][1]['enabled'] = False
            if case == 'script': contract['modules'][1]['script'] = 'other.py'
            if case == 'provenance': extension['synthesis_source_provenance']['source_labels'] = []
            if case == 'checked': extension['synthesis_checked_modules']['clusterer'] = '0' * 64
            if case == 'transitive': del upstream['clusterer']
            if case == 'selection': extension['synthesis_selection']['decisions'][0]['reason'] = 'Forged'
            if case == 'counts': extension['counting']['topics'][0]['scope']['person_count'] = 999
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.project((material, payload, upstream, contract))

    def test_no_extension_preserves_legacy_projection_without_contract(self):
        material, payload, _, _ = projection_fixture()
        payload.pop('analysis_perspective')
        self.assertEqual(project_stage('overall_synthesis', payload),
                         project_stage('overall_synthesis', payload, segments=original_segments(material)))

    def files(self, root, payload, upstream, contract):
        hashes = {}
        for mid, value in {'overall_synthesis': payload, **upstream}.items():
            name = mid + '.json'; atomic_json(root / name, value); hashes[name] = file_hash(root / name)
        manifest = {'completed_steps': ['overall_synthesis', *upstream], 'output_hashes': hashes}
        atomic_json(root / 'workflow_manifest.json', manifest)
        return manifest

    def test_loader_and_child_sources_verify_transitive_originals_independent_of_order(self):
        material, payload, upstream, contract = projection_fixture(reduced=True)
        # Only summaries selected would still require the original clusters.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = self.files(root, payload, upstream, contract)
            modules = contract['modules']; by_id = {m['id']: m for m in modules}
            checked = _thematic_upstreams(root, 'overall_synthesis', payload, by_id, manifest)
            self.assertEqual(checked, upstream)
            summary_only = copy.deepcopy(by_id)
            summary_only['overall_synthesis']['args'] = ['--out-json', 'overall_synthesis.json',
                '--source-json', 'First alias=summarizer.json']
            self.assertEqual(_thematic_upstreams(root, 'overall_synthesis', payload, summary_only, manifest), upstream)
            custom = copy.deepcopy(summary_only)
            custom['clusterer']['script'] = 'custom_clusterer.py'
            with self.assertRaises(ValueError):
                _thematic_upstreams(root, 'overall_synthesis', payload, custom, manifest)
            with self.assertRaises(ValueError):
                synthesis_contract_bindings({'module': custom['overall_synthesis'],
                    'modules': list(custom.values()), 'directory': root})
            del summary_only['clusterer']
            with self.assertRaises(ValueError):
                _thematic_upstreams(root, 'overall_synthesis', payload, summary_only, manifest)
            first = load_sources(root, {'pipeline': {'modules': modules}}, segments=original_segments(material))
            second = load_sources(root, {'pipeline': {'modules': list(reversed(modules))}}, segments=original_segments(material))
            self.assertEqual(first, second)
            self.assertEqual(first['overall_synthesis']['status'], 'available')
            for case in ('hash', 'completion', 'disabled', 'undeclared'):
                current = copy.deepcopy(manifest); declared = copy.deepcopy(by_id)
                if case == 'hash': current['output_hashes']['clusterer.json'] = '0' * 64
                if case == 'completion': current['completed_steps'].remove('clusterer')
                if case == 'disabled': declared['clusterer']['enabled'] = False
                if case == 'undeclared': del declared['clusterer']
                with self.subTest(case=case), self.assertRaises(ValueError):
                    _thematic_upstreams(root, 'overall_synthesis', payload, declared, current)
            atomic_json(root / 'clusterer.json', {**upstream['clusterer'], 'created_at': 'altered'})
            result = load_sources(root, {'pipeline': {'modules': modules}}, segments=original_segments(material))
            self.assertEqual(result['overall_synthesis']['status'], 'invalid')

    def test_stability_compares_frequency_and_rejects_missing_actual_contract(self):
        material, payload, upstream, contract = projection_fixture()
        altered = copy.deepcopy(payload)
        altered['analysis_perspective']['interpretations']['frequency'][0]['interpretation'] = 'Andere Gewichtung.'
        samples = [{'sample_id': str(i), 'status': 'success', 'payload': value,
                    'upstream_payloads': upstream, 'source_contract': contract}
                   for i, value in enumerate((payload, altered))]
        result = analyze_stage_repetitions(original_segments(material), 'overall_synthesis', samples)
        self.assertTrue(result['pairs'])
        self.assertTrue(any(row['repeat_status'] == 'variable' and row['kind'] == 'thematic_interpretation'
                            for row in result['record_occurrences']))
        samples[1] = {key: value for key, value in samples[1].items() if key != 'source_contract'}
        result = analyze_stage_repetitions(original_segments(material), 'overall_synthesis', samples)
        self.assertFalse(result['pairs'])

    def test_reclassified_context_reason_is_visible_without_changing_original_prose(self):
        from thematic_synthesis_adapter import build_overall_synthesis_topics
        from synthesis_countability import _hash
        material, payload, upstream, contract = projection_fixture()
        changed = copy.deepcopy(payload)
        extension = changed['analysis_perspective']
        selection = extension['synthesis_selection']
        decision = next(row for row in selection['decisions'] if row['classification'] == 'group_comparison')
        decision['reason'] = 'Andere nachvollziehbare Begründung für den ungezählten Gruppenvergleich.'
        selection['result_fingerprint'] = _hash({key: value for key, value in selection.items() if key != 'result_fingerprint'})
        bindings = extension['synthesis_source_bindings']
        sources = {label: upstream[row['module_id']] for label, row in bindings.items()}
        prepared = build_overall_synthesis_topics(material,
            {key: value for key, value in changed.items() if key != 'analysis_perspective'}, sources,
            selection, bindings=bindings, upstream_payloads=upstream)
        extension['candidate_source_fingerprint'] = prepared['source_fingerprint']
        extension['unassigned_context'] = prepared['unassigned_context']
        self.project((material, changed, upstream, contract))
        samples = [{'sample_id': str(i), 'status': 'success', 'payload': value,
                    'upstream_payloads': upstream, 'source_contract': contract}
                   for i, value in enumerate((payload, changed))]
        result = analyze_stage_repetitions(original_segments(material), 'overall_synthesis', samples)
        self.assertTrue(any(row['repeat_status'] == 'variable' and row['kind'] == 'thematic_selection'
                            for row in result['record_occurrences']))


if __name__ == '__main__':
    unittest.main()
