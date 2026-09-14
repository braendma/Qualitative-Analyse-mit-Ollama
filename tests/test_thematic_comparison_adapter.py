"""Synthetic original comparison outputs and strict complete-source checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from person_comparison_core import normalize_comparison, build_person_comparison
from runtime_support import fingerprint
from thematic_comparison_adapter import build_person_comparison_topics
from thematic_counts import count_topics
from test_thematic_person_adapters import fixture as person_fixture


def comparison_fixture(person_count=2, *, reduced=False):
    """Return (material, source_person_payload, comparison_payload)."""
    material, source, _ = person_fixture(person_count)
    names = sorted(source['persons'])
    result = normalize_comparison({
        'gemeinsame_muster': [{'thema': 'Zeitgestaltung', 'verdichtung': 'Planbare Zeiten sind relevant.', 'personen': names[:1]}],
        'zentrale_unterschiede': [{'thema': 'Flexibilität', 'beschreibung': 'Verschiedene Bedürfnisse.',
            'personenpositionen': [{'person': names[0], 'position': 'Planbare Zeiten.'}]}],
        'typen': [{'typ_name': 'Planungsorientiert', 'beschreibung': 'Ein analytischer Typ.', 'personen': names[:1], 'merkmale': ['Planbarkeit']}],
        'nicht_zugeordnete_personen': [{'person': names[-1], 'begruendung': 'Keine eindeutige Zuordnung.'}],
        'gesamtvergleich': 'Gemeinsamkeiten und Unterschiede bleiben sichtbar.'}, names)
    receipt = {'used': reduced, 'source_sha256': fingerprint(source['persons'])}
    if reduced:
        summaries = {name: 'Künstliche Verdichtung für ' + name for name in names}
        receipt.update(method='per_person_hierarchical_reduction', target_bytes_per_person=1200, context=32768,
            budget_method='shared_final_prompt_with_soft_person_targets', note='Synthetische vollständige Einzelverdichtung.',
            actual_bytes_per_person={name: len(value.encode('utf-8')) for name, value in summaries.items()},
            sources={name: {'source_sha256': fingerprint(source['persons'][name]), 'source_person': name, 'summary': summaries[name]} for name in names})
    payload = {'created_at': 'synthetic-comparison', 'source_person_analysis_created_at': source['created_at'],
        'source_persons': names, 'input_reduction': receipt, **result}
    return material, source, payload


class ThematicComparisonAdapterTests(unittest.TestCase):
    def test_complete_twelve_person_scope_not_selected_person_references(self):
        material, source, payload = comparison_fixture(12)
        result = build_person_comparison_topics(material, payload, source)
        self.assertEqual(len(result['topics']), 1)
        topic = result['topics'][0]
        self.assertEqual(topic['scope_unit_ids'], sorted(material['units']))
        self.assertEqual(topic['kind'], 'derived')
        self.assertIsNone(result['assignments']); self.assertEqual(result['model_calls'], 0)
        counted = count_topics(material, result['topics'], [])['topics'][0]
        self.assertEqual(counted['scope']['person_count'], 12)
        self.assertIsNone(counted['counts']['mentioned']['exact_person_count'])
        self.assertEqual(result['source_links'][topic['topic_id']]['source_persons'], ['P01'])
        self.assertEqual(result['source_links'][topic['topic_id']]['selected_evidence_segment_ids'], [])

    def test_types_overlap_and_nonassigned_status_remain_unchanged_context(self):
        material, source, payload = comparison_fixture()
        payload['typen'].append({**payload['typen'][0], 'typ_name': 'Weiterer Typ'})
        payload['nicht_zugeordnete_personen'][0]['person'] = 'P01'
        result = build_person_comparison_topics(material, payload, source)
        for key in ('typen', 'zentrale_unterschiede', 'nicht_zugeordnete_personen', 'gesamtvergleich'):
            self.assertEqual(result['unassigned_context'][key], payload[key])
        self.assertEqual(len(result['topics']), 1)
        self.assertIn('Partition', result['unassigned_context']['counting_note'])

    def test_weighted_extensions_do_not_change_original_hashes_or_mutate_sources(self):
        material, source, payload = comparison_fixture(reduced=True)
        expected = build_person_comparison_topics(material, payload, source)
        source['analysis_perspective'] = {'text': 'private extra interpretation'}
        payload['analysis_perspective'] = {'text': 'additional interpretation'}
        before = copy.deepcopy((material, source, payload))
        actual = build_person_comparison_topics(material, payload, source)
        self.assertEqual(actual, expected); self.assertEqual((material, source, payload), before)
        actual['unassigned_context']['typen'].clear()
        actual['qualitative_source']['gemeinsame_muster'].clear()
        self.assertEqual((material, source, payload), before)

    def test_semantic_ids_stable_under_order_and_selected_reference_changes(self):
        material, source, payload = comparison_fixture()
        payload['gemeinsame_muster'].append({'thema': 'Zeitgestaltung', 'verdichtung': 'Spontane Zeitgestaltung ist relevant.', 'personen': ['P02']})
        expected = build_person_comparison_topics(material, payload, source)
        payload['gemeinsame_muster'].reverse(); payload['source_persons'].reverse()
        payload['gemeinsame_muster'][0]['personen'] = ['P01', 'P02']
        actual = build_person_comparison_topics(material, payload, source)
        self.assertEqual(actual['topics'], expected['topics'])
        self.assertEqual(len(actual['topics']), 2)

    def test_duplicate_identical_common_finding_rejected(self):
        material, source, payload = comparison_fixture()
        payload['gemeinsame_muster'].append(copy.deepcopy(payload['gemeinsame_muster'][0]))
        with self.assertRaises(ValueError): build_person_comparison_topics(material, payload, source)

    def test_all_sections_reject_foreign_references_including_uncounted_context(self):
        mutations = [lambda p: p['source_persons'].append('foreign'),
            lambda p: p['gemeinsame_muster'][0]['personen'].append('foreign'),
            lambda p: p['zentrale_unterschiede'][0]['personenpositionen'][0].update(person='foreign'),
            lambda p: p['typen'][0]['personen'].append('foreign'),
            lambda p: p['nicht_zugeordnete_personen'][0].update(person='foreign')]
        for mutate in mutations:
            material, source, payload = comparison_fixture()
            mutate(payload)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                build_person_comparison_topics(material, payload, source)

    def test_full_original_person_source_and_receipt_required(self):
        for key in ('person_basis', 'missing_person', 'foreign_quote', 'changed_definition', 'missing_receipt', 'missing_comparison_person', 'wrong_timestamp'):
            material, source, payload = comparison_fixture()
            if key == 'person_basis': material['person_basis'] = 'unconfirmed'
            if key == 'missing_person': del source['persons']['P02']
            if key == 'foreign_quote': source['persons']['P01']['belege'][0]['zitat'] = 'changed'
            if key == 'changed_definition': source['persons']['P01']['gesamtverdichtung'] = 'changed original'
            if key == 'missing_receipt': del payload['input_reduction']
            if key == 'missing_comparison_person': payload['source_persons'].pop()
            if key == 'wrong_timestamp': payload['source_person_analysis_created_at'] = 'foreign'
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_person_comparison_topics(material, payload, source)

    def test_reduced_receipt_checks_every_person_hash_identity_and_utf8_size(self):
        for key in ('global_hash', 'missing', 'person', 'hash', 'size', 'summary', 'method'):
            material, source, payload = comparison_fixture(reduced=True)
            receipt = payload['input_reduction']
            if key == 'global_hash': receipt['source_sha256'] = 'wrong'
            if key == 'missing': del receipt['sources']['P02']
            if key == 'person': receipt['sources']['P02']['source_person'] = 'P01'
            if key == 'hash': receipt['sources']['P02']['source_sha256'] = 'wrong'
            if key == 'size': receipt['actual_bytes_per_person']['P02'] += 1
            if key == 'summary': receipt['sources']['P02']['summary'] = ''
            if key == 'method': receipt['method'] = 'unverified'
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_person_comparison_topics(material, payload, source)

    def test_invalid_context_schema_rejected_instead_of_ignored(self):
        for section in ('typen', 'zentrale_unterschiede', 'nicht_zugeordnete_personen', 'gemeinsame_muster'):
            material, source, payload = comparison_fixture()
            payload[section][0]['unknown_persons'] = ['foreign']
            with self.subTest(section=section), self.assertRaises(ValueError):
                build_person_comparison_topics(material, payload, source)

    def test_empty_common_results_keep_context_without_inventing_topics(self):
        material, source, payload = comparison_fixture()
        payload['gemeinsame_muster'] = []
        result = build_person_comparison_topics(material, payload, source)
        self.assertEqual(result['topics'], [])
        self.assertTrue(result['unassigned_context']['typen'])

    def test_actual_core_output_with_and_without_reduction(self):
        for reduced in (False, True):
            material, source, expected = comparison_fixture()
            if reduced:
                for row in source['persons'].values(): row['gesamtverdichtung'] = 'Langer synthetischer Kontext. ' * 2000
            response = {key: expected[key] for key in ('gemeinsame_muster', 'zentrale_unterschiede', 'typen', 'nicht_zugeordnete_personen', 'gesamtvergleich')}
            with tempfile.TemporaryDirectory() as temp, \
                 patch('person_comparison_core.llm_person_comparison', return_value=json.dumps(response)), \
                 patch('comparison_reduction.reduce_prompt', return_value='Eine kurze künstliche Personenverdichtung.') as reduce:
                path = Path(temp) / 'persons.json'; path.write_text(json.dumps(source), encoding='utf-8')
                before = path.read_bytes()
                _, payload = build_person_comparison(path,
                    {'model': 'synthetic', 'num_ctx': 8000 if reduced else 32768, 'max_tokens': 128, 'parallel_workers': 1, 'partial_checkpoints': False},
                    {'person_comparison': {'system': 'Synthetic', 'user': '{persons}'}}, {})
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(payload['input_reduction']['used'], reduced)
                self.assertEqual(reduce.call_count, 2 if reduced else 0)
                result = build_person_comparison_topics(material, payload, source)
                self.assertEqual(len(result['topics']), 1)
                self.assertEqual(result['source_person_fingerprint'], fingerprint(source))


if __name__ == '__main__': unittest.main()
