import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from coding_validation_common import Segment
from diagnostic_sources import project_stage, load_sources, make_snapshot, declared_json
from runtime_support import atomic_json, file_hash


class DiagnosticSourcesTests(unittest.TestCase):
    def test_person_input_inventory_is_not_selected_evidence(self):
        payload = {'persons': {'P1': {'segment_ids': ['s1', 's2'],
            'zentrale_themen': [{'thema': 'Selected', 'segment_ids': ['s1', 's1']}],
            'perspektiven': [], 'spannungsfelder': [], 'kontrastierende_aspekte': [],
            'belege': [{'segment_id': 's2'}]}}}
        before = copy.deepcopy(payload)
        result = project_stage('person_analysis', payload)
        self.assertEqual(result['records'][0]['segment_ids'], ['s1'])
        self.assertEqual(payload, before)

    def test_meta_registry_only_resolves_referenced_findings(self):
        payload = {'finding_registry': {'F1': {'segment_ids': ['s1']}, 'F2': {'segment_ids': ['s2']}},
            'meta_swot': {'Stärken': {'uebergreifende_muster': [{'finding_ids': ['F1']}],
                                     'einzelbefunde': [{'finding_id': 'missing'}]}}}
        rows = project_stage('meta_swot', payload)['records']
        self.assertEqual(rows[0]['segment_ids'], ['s1'])
        self.assertEqual(rows[1]['unresolved'], ['missing'])

    def test_synthesis_graph_is_group_context_not_direct_evidence(self):
        payload = {'kernergebnisse': [{'thema': 'Test', 'quellen': ['N1', 'N1']}],
            'uebergreifende_muster': [], 'spannungen_und_relativierungen': [],
            'hierarchical_reduction': {'nodes': {'N1': {'input_ids': ['L1']}},
                'leaves': {'L1': {'source': 'SWOT', 'content': {'segment_ids': ['s1']}}}}}
        row = project_stage('overall_synthesis', payload)['records'][0]
        self.assertEqual(row['scope'], 'source_group')
        self.assertEqual(row['segment_ids'], ['s1'])
        self.assertEqual(row['source_refs'], ['N1'])
        payload['hierarchical_reduction']['nodes']['N1']['input_ids'] = ['N1']
        self.assertEqual(project_stage('overall_synthesis', payload)['records'][0]['unresolved'], ['N1'])

    def test_unknown_ids_and_people_are_not_usable(self):
        segments = [Segment('s1', 'Text', 'C', 'P1', 'u1')]
        stage = project_stage('person_analysis', {'persons': {'P2': {
            'zentrale_themen': [{'segment_ids': ['foreign']}], 'perspektiven': [],
            'spannungsfelder': [], 'kontrastierende_aspekte': []}}})
        stage['status'] = 'available'
        snap = make_snapshot(segments, {'person_analysis': stage})
        row = snap['stages']['person_analysis']['records'][0]
        self.assertFalse(row['valid'])
        self.assertEqual(row['unknown_segment_ids'], ['foreign'])
        self.assertEqual(row['unknown_persons'], ['P2'])
        self.assertNotIn('valid', stage['records'][0])

    def test_two_ambiguity_sides_and_person_only_negative_case(self):
        amb = project_stage('ambiguity_analysis', {'persons': {'P1': {'ambivalenzen': [{
            'segment_ids_a': ['s1'], 'segment_ids_b': ['s2']}]}}})
        self.assertEqual([r['kind'] for r in amb['records']], ['ambiguity_a', 'ambiguity_b'])
        neg = project_stage('contrast_analysis', {'dominante_muster': [],
            'negativfaelle': [{'person': 'P1', 'abweichung': 'Test'}],
            'spannungen_zwischen_typen': [], 'relativierungen': []})
        self.assertEqual(neg['records'][0]['scope'], 'person_reference')
        self.assertEqual(neg['records'][0]['segment_ids'], [])

    def test_missing_schema_and_failed_result_not_empty_success(self):
        for payload in ({}, {'clusters': [] , 'processing_status': 'failed'}, {'clusters': [None]}):
            with self.assertRaises(ValueError):
                project_stage('clusterer', payload)
        result = project_stage('clusterer', {'clusters': []})
        self.assertEqual(result['records'], [])

    def test_declared_filename_hash_and_completion_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            module = {'id': 'clusterer', 'args': ['--out-json', 'custom.json'],
                      'outputs': ['text_map.json', 'custom.json']}
            config = {'pipeline': {'modules': [module]}}
            atomic_json(directory / 'custom.json', {'clusters': [{'segments': ['s1']}]})
            atomic_json(directory / 'text_map.json', {'irrelevant': 's2'})
            self.assertEqual(load_sources(directory, config)['clusterer']['reason'], 'not_verified')
            manifest = {'completed_steps': ['clusterer'], 'output_hashes': {
                'custom.json': file_hash(directory / 'custom.json')}}
            atomic_json(directory / 'workflow_manifest.json', manifest)
            result = load_sources(directory, config)['clusterer']
            self.assertEqual(result['status'], 'available')
            self.assertEqual(result['artifact'], 'custom.json')
            atomic_json(directory / 'custom.json', {'clusters': []})
            self.assertEqual(load_sources(directory, config)['clusterer']['status'], 'invalid')
            module['enabled'] = False
            self.assertEqual(load_sources(directory, config)['clusterer']['reason'], 'disabled')

    def test_missing_file_and_path_escape_are_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            atomic_json(directory / 'workflow_manifest.json', {'completed_steps': ['clusterer']})
            for name in ('absent.json', '../outside.json'):
                config = {'pipeline': {'modules': [{'id': 'clusterer', 'outputs': [name]}]}}
                self.assertEqual(load_sources(directory, config)['clusterer']['status'], 'invalid')
        with self.assertRaises(ValueError):
            declared_json({'outputs': ['a.json', 'b.json']})

    def test_empty_and_complete_input_associations(self):
        payload = {'cluster_summaries': [{'segments': ['s1', 's2'], 'summary': 'Short.'}],
                   'final_summary': 'No exact references'}
        row = project_stage('summarizer', payload)['records'][0]
        self.assertEqual(row['scope'], 'input_association')
        self.assertEqual(row['segment_ids'], ['s1', 's2'])


if __name__ == '__main__':
    unittest.main()
