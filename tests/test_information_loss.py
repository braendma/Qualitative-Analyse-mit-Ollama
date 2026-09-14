from pathlib import Path
import copy
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from coding_validation_common import Segment
from diagnostic_sources import make_snapshot, dependency_edges, project_stage
from information_loss_core import analyze_information_loss, render_information_loss
from information_loss_analysis import main as loss_main
from runtime_support import atomic_json, file_hash


def row(key, ids, text='', kind='finding', scope='direct', persons=()):
    return {'key': key, 'segment_ids': ids, 'text': text, 'kind': kind, 'scope': scope,
            'persons': list(persons), 'unresolved': []}


def stage(*rows):
    return {'status': 'available', 'warnings': [], 'records': list(rows)}


def snapshot(before, after, **extra):
    return make_snapshot([Segment('s1', 'gleich', 'A', 'P1', 'u1'),
                          Segment('s2', 'gleich', 'B', 'P1', 'u1'),
                          Segment('s3', 'anders', 'C', 'P2', 'u2')],
                         {'swot': before, 'meta_swot': after, **extra})


def diagnose(snap):
    return analyze_information_loss(snap, [('swot', 'meta_swot')])


class InformationLossTests(unittest.TestCase):
    def test_multiple_codes_do_not_turn_row_change_into_lost_material(self):
        snap = snapshot(stage(row('b', ['s1', 's3'])), stage(row('a', ['s2'])))
        original = copy.deepcopy(snap)
        edge = diagnose(snap)['transitions'][0]
        refs = edge['reference_comparison']
        self.assertEqual(refs['coding_rows_no_longer_referenced'], ['s1', 's3'])
        self.assertEqual(refs['material_units_no_longer_referenced'], [['s3']])
        self.assertEqual(refs['material_units_referenced_in_both'], 1)
        self.assertEqual(edge['persons_no_longer_referenced'], ['P2'])
        self.assertEqual(refs['person_shares'][0]['before'], .5)
        self.assertEqual(refs['person_shares'][0]['after'], 1)
        self.assertEqual(snap, original)

    def test_reference_retention_never_implies_semantic_retention(self):
        result = diagnose(snapshot(stage(row('b', ['s1'], 'Vielleicht ist das teilweise hilfreich.')),
                                   stage(row('a', ['s1'], 'Das ist immer eindeutig hilfreich.'))))
        review = result['transitions'][0]['review_items'][0]
        self.assertIn('uncertainty_words_not_found_in_candidates', review['flags'])
        self.assertIn('assertive_words_added_in_candidates', review['flags'])
        self.assertEqual(review['source_uncertainty_words'], ['teilweise', 'vielleicht'])
        text = render_information_loss(result)
        self.assertIn('keinen Bedeutungserhalt', text)
        self.assertIn('keine Fehlerquote', text)
        self.assertNotIn('loss_score', result)
        self.assertEqual(result['model_calls'], 0)

    def test_negation_and_lexical_equivalents_remain_manual_review(self):
        result = diagnose(snapshot(stage(row('b', ['s1'], 'Möglicherweise passend.')),
                                   stage(row('a', ['s1'], 'Nicht alle sehen es so; es ist eventuell passend.'))))
        # Deliberate limitations: negation and synonyms must not be presented as proven strengthening.
        text = render_information_loss(result)
        self.assertIn('auch Negation, Zitat und Gegenposition prüfen', text)
        self.assertIn('andere Formulierungen können dieselbe Unsicherheit ausdrücken', text)

    def test_long_unicode_text_and_many_candidates_use_full_text_but_bounded_previews(self):
        long = ('Übermäßig langer Prüftext; 🧪\n' * 40000) + ' möglicherweise'
        targets = [row(f'target/{i:03}', ['s1'], long if i == 59 else 'kurz') for i in range(60)]
        result = diagnose(snapshot(stage(row('b', ['s1'], long)), stage(*targets)))
        review = result['transitions'][0]['review_items'][0]
        self.assertNotIn('uncertainty_words_not_found_in_candidates', review['flags'])
        self.assertEqual(review['candidate_uncertainty_words'], ['möglicherweise'])
        self.assertTrue(review['source']['preview_truncated'])
        self.assertEqual(len(review['source']['text_preview']), 1200)
        self.assertEqual(review['candidate_previews_omitted'], 10)
        self.assertEqual(len(review['candidates']), 50)
        self.assertIn('Vorschau gekürzt', render_information_loss(result))
        self.assertIn('Weitere 10 Kandidaten', render_information_loss(result))

    def test_person_only_and_unlinked_groups_never_fabricate_segment_loss(self):
        for target in (row('a', [], scope='person_reference', persons=['P1']),
                       row('a', [], scope='source_group')):
            edge = diagnose(snapshot(stage(row('b', ['s1'])), stage(target)))['transitions'][0]
            self.assertIsNone(edge['reference_comparison'])
            self.assertIn('nicht bestimmbar', edge['reference_comparison_note'])

    def test_no_implicit_linear_chain_between_parallel_branches(self):
        snap = snapshot(stage(row('b', ['s1'])), stage(row('a', ['s1'])),
                        relation_analysis=stage(row('r', ['s3'])))
        result = diagnose(snap)
        self.assertEqual([(e['source'], e['target']) for e in result['transitions']], [('swot', 'meta_swot')])
        self.assertEqual(result, analyze_information_loss(snap, [('swot', 'meta_swot')] * 2))
        with self.assertRaisesRegex(ValueError, 'eigene Nachfolgestufe'):
            analyze_information_loss(snap, [('swot', 'swot')])

    def test_failed_invalid_and_disabled_are_distinct_from_empty_completed(self):
        for target, expected in (({'status': 'unavailable', 'reason': 'failed', 'records': []}, 'incomplete'),
                                 ({'status': 'unavailable', 'reason': 'disabled', 'records': []}, 'completed'),
                                 (stage(row('bad', ['unknown'])), 'incomplete')):
            result = diagnose(snapshot(stage(row('b', ['s1'])), target))
            self.assertEqual(result['processing_status'], expected)
            self.assertEqual(result['transitions'][0]['status'], 'not_measurable')
        empty = diagnose(snapshot(stage(row('b', ['s1'])), stage()))['transitions'][0]
        self.assertEqual(empty['reference_comparison']['material_units_no_longer_referenced'], [['s1', 's2']])
        self.assertIsNone(empty['reference_comparison']['person_shares'][0]['after'])

    def test_counterpositions_remain_reviewable_even_when_both_sides_keep_references(self):
        result = diagnose(snapshot(stage(row('b/a', ['s1'], 'einerseits', kind='ambiguity_a'),
                                         row('b/b', ['s3'], 'andererseits', kind='ambiguity_b')),
                                   stage(row('a', ['s1', 's3'], 'Zusammenfassung'))))
        reviews = result['transitions'][0]['review_items']
        self.assertEqual(len(reviews), 2)
        for review in reviews:
            self.assertIn('check_counterposition_or_ambivalence_in_context', review['flags'])
            self.assertIn('multiple_origins_check_distinct_positions', review['flags'])
            self.assertEqual(review['largest_shared_origin_count'], 2)
        self.assertEqual(result['transitions'][0]['reference_comparison']['material_units_no_longer_referenced'], [])

    def test_html_and_markdown_in_data_are_escaped(self):
        result = diagnose(snapshot(stage(row('<script>x</script>', ['s1'], '<b>Vielleicht</b> [Link](evil)')),
                                   stage(row('a', ['s1'], 'immer'))))
        rendered = render_information_loss(result)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<b>', rendered)
        self.assertIn('&lt;b&gt;', rendered)
        self.assertIn('\\[Link\\]', rendered)

    def test_edges_follow_saved_input_contract_including_custom_names(self):
        cfg = {'pipeline': {'modules': [
            {'id': 'swot', 'outputs': ['custom.json'], 'args': ['--out-json', 'custom.json']},
            {'id': 'meta_swot', 'depends_on': ['swot'], 'outputs': ['meta.json'],
             'args': ['--swot-json', 'custom.json', '--out-json', 'meta.json']},
            {'id': 'overall_synthesis', 'depends_on': ['swot', 'meta_swot'],
             'args': ['--source-json', 'Meta=meta.json']}]}}
        self.assertEqual(dependency_edges(cfg), [('meta_swot', 'overall_synthesis'), ('swot', 'meta_swot')])
        # Scheduling dependency without consumed artifact is not semantic lineage.
        cfg['pipeline']['modules'][1]['args'][1] = 'different.json'
        self.assertEqual(dependency_edges(cfg), [('meta_swot', 'overall_synthesis')])
        cfg['pipeline']['modules'][1]['enabled'] = False
        self.assertEqual(dependency_edges(cfg), [])

    def test_input_cluster_boundary_and_projected_position_explanations(self):
        snap = snapshot(stage(), stage(), clusterer=stage(row('cluster', ['s2'], scope='input_association')))
        result = diagnose(snap)
        self.assertEqual(result['input_to_clusters']['unreferenced_coding_rows'], ['s1', 's3'])
        self.assertEqual(result['input_to_clusters']['unreferenced_material_units'], [['s3']])
        projected=project_stage('person_comparison', {
            'gemeinsame_muster': [], 'typen': [],
            'zentrale_unterschiede': [{'thema':'Wahl', 'beschreibung':'Verschieden',
                'personenpositionen':[{'person':'P1','position':'Vielleicht möglich'}, {'person':'P2','position':'Unklar'}]}],
            'nicht_zugeordnete_personen': [{'person':'P1','begruendung':'Möglicherweise ungeeignet'}]})
        self.assertIn('P1: Vielleicht möglich',projected['records'][0]['text'])
        self.assertIn('P2: Unklar',projected['records'][0]['text'])
        self.assertEqual(projected['records'][1]['text'],'Möglicherweise ungeeignet')

    def test_cli_partial_retry_checks_hashes_and_preserves_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, config, manifest_path = root/'input.csv', root/'config.yaml', root/'workflow_manifest.json'
            source.write_text('ID;Person;Code;Text\ns1;P1;A;Vielleicht hilfreich\n', encoding='utf-8')
            modules = [
                {'id': 'swot', 'enabled': True, 'args': ['--out-json', 'swot.json'], 'outputs': ['swot.json']},
                {'id': 'meta_swot', 'enabled': True, 'depends_on': ['swot'],
                 'args': ['--swot-json', 'swot.json', '--out-json', 'meta.json'], 'outputs': ['meta.json']}]
            config.write_text(yaml.safe_dump({'columns': {'segment_id': 'ID', 'person': 'Person', 'code': 'Code', 'segment': 'Text'},
                                             'pipeline': {'modules': modules}}), encoding='utf-8')
            atomic_json(root/'swot.json', {'swot': {'unit': {'Stärken': [{'aussage': 'Vielleicht hilfreich', 'segment_ids': ['s1']}],
                                                         'Schwächen': [], 'Chancen': [], 'Risiken': []}}})
            atomic_json(root/'meta.json', {'finding_registry': {}, 'meta_swot': {'Stärken': {
                'uebergreifende_muster': [{'aussage': 'Immer hilfreich', 'segment_ids': ['s1']}], 'einzelbefunde': []}}})
            manifest = {'run_id': 'synthetic-test', 'completed_steps': ['swot'],
                        'module_status': {'swot': 'completed', 'meta_swot': 'failed'},
                        'output_hashes': {'swot.json': file_hash(root/'swot.json')},
                        'provenance': {'input_sha256': file_hash(source), 'config_sha256': file_hash(config)}}
            atomic_json(manifest_path, manifest)
            outputs = [root/'information_loss.json', root/'information_loss.md']
            args = ['--config', str(config), '--input-csv', str(source), '--run-dir', str(root),
                    '--out-json', str(outputs[0]), '--out-md', str(outputs[1])]
            protected_before = {p: p.read_bytes() for p in (source, config, root/'swot.json', root/'meta.json')}
            loss_main(args)
            self.assertEqual(json.loads(outputs[0].read_text())['processing_status'], 'incomplete')
            manifest['completed_steps'].append('meta_swot')
            manifest['module_status'].update(meta_swot='completed', information_loss='running')
            manifest['output_hashes']['meta.json'] = file_hash(root/'meta.json')
            atomic_json(manifest_path, manifest)
            with patch.dict(os.environ, {'WORKFLOW_RUN_ID': 'synthetic-test', 'WORKFLOW_MODULE': 'information_loss'}):
                loss_main(args)
            result = json.loads(outputs[0].read_text())
            self.assertEqual(result['processing_status'], 'completed')
            self.assertEqual(len(result['transitions'][0]['review_items']), 1)
            self.assertEqual(result['source_artifacts']['meta_swot']['sha256'], file_hash(root/'meta.json'))
            self.assertIn('Zwischenprodukte: swot.json → meta.json', outputs[1].read_text(encoding='utf-8'))
            for path, content in protected_before.items():
                self.assertEqual(path.read_bytes(), content)
            with self.assertRaisesRegex(ValueError, 'existiert bereits'):
                loss_main(args)
            # Changing a saved source without refreshing its manifest must invalidate the diagnosis.
            (root/'meta.json').write_text('{}', encoding='utf-8')
            fresh = args[:-4] + ['--out-json', str(root/'fresh.json'), '--out-md', str(root/'fresh.md')]
            loss_main(fresh)
            self.assertEqual(json.loads((root/'fresh.json').read_text())['processing_status'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
