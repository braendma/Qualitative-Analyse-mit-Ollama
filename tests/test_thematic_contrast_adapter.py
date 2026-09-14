"""Synthetic complete-source contrast fixtures with actual normalization/core runs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contrast_analysis_core import normalize_contrast, build_contrast_analysis
from runtime_support import fingerprint
from thematic_contrast_adapter import build_contrast_topics
from thematic_counts import count_topics
from test_thematic_comparison_adapter import comparison_fixture


def contrast_fixture(person_count=2, *, reduced=False):
    """Return (material, person_payload, comparison_payload, contrast_payload)."""
    material, source, comparison = comparison_fixture(person_count, reduced=reduced)
    names = sorted(source['persons'])
    normalized = normalize_contrast({
        'dominante_muster': [{'muster': 'Planbarkeit', 'beschreibung': 'Planbare Arbeitszeiten helfen.', 'getragen_von': names[:1]}],
        'negativfaelle': [{'person': names[-1], 'bezugs_muster': 'Planbarkeit', 'abweichung': 'Spontane Gestaltung wird bevorzugt.', 'begruendung': 'Situationsbezogene Präferenz.'}],
        'spannungen_zwischen_typen': [{'typen': ['Planungsorientiert'], 'beschreibung': 'Mögliche Unterschiede.'}],
        'relativierungen': [{'aussage': 'Keine Repräsentativität.', 'bedeutung': 'Grenzen der Studie.'}],
        'gesamteinordnung': 'Seltene Gegenfälle bleiben sichtbar.'}, names, ['Planungsorientiert'])
    reduction = {'used': False}
    if reduced:
        projected = {key: value for key, value in comparison.items() if key not in
                     ('input_reduction', 'created_at', 'source_person_analysis_created_at')}
        reduction = {'used': True, 'parts': 1, 'note': 'Synthetischer vollständiger Quellenumfang.',
            'comparison': {'used': False, 'source_sha256': fingerprint(projected)},
            'persons': {name: {'used': True, 'source_sha256': fingerprint(source['persons'][name]),
                'summary': comparison['input_reduction']['sources'][name]['summary'],
                'reused_comparison_summary': True} for name in names}}
    payload = {'created_at': 'synthetic-contrast', 'source_person_analysis_created_at': source['created_at'],
        'source_person_comparison_created_at': comparison['created_at'], 'input_reduction': reduction, **normalized}
    return material, source, comparison, payload


def build(values):
    material, source, comparison, payload = values
    return build_contrast_topics(material, payload, source, comparison)


class ThematicContrastAdapterTests(unittest.TestCase):
    def test_twelve_people_global_and_complete_individual_scopes(self):
        values = contrast_fixture(12); material = values[0]
        result = build(values)
        self.assertIsNone(result['assignments']); self.assertEqual(result['model_calls'], 0)
        self.assertEqual(len(result['topics']), 2)
        counts = {row['topic_id']: row for row in count_topics(material, result['topics'], [])['topics']}
        for topic in result['topics']:
            link = result['source_links'][topic['topic_id']]
            if link['scope_kind'] == 'global_pattern':
                self.assertEqual(topic['scope_unit_ids'], sorted(material['units']))
                self.assertEqual(counts[topic['topic_id']]['scope']['person_count'], 12)
                self.assertEqual(len(link['countercase_topic_ids']), 1)
            else:
                self.assertEqual(link['person'], 'P12')
                self.assertEqual(counts[topic['topic_id']]['scope']['person_count'], 1)
                self.assertEqual(len(topic['scope_unit_ids']), 2)
                self.assertIn('Planbare Arbeitszeiten helfen.', topic['definition'])
                self.assertIn(topic['topic_id'], result['source_links'][link['pattern_topic_id']]['countercase_topic_ids'])

    def test_global_and_case_types_stay_distinct_in_single_person_study(self):
        result = build(contrast_fixture(1))
        self.assertEqual(result['topics'][0]['scope_unit_ids'], result['topics'][1]['scope_unit_ids'])
        self.assertEqual({row['scope_kind'] for row in result['source_links'].values()}, {'global_pattern', 'individual_countercase'})

    def test_exact_duplicate_patterns_and_cases_preserve_all_records_once(self):
        values = contrast_fixture(); payload = values[-1]
        payload['dominante_muster'].append({**payload['dominante_muster'][0], 'getragen_von': ['P02']})
        payload['negativfaelle'].append(copy.deepcopy(payload['negativfaelle'][0]))
        result = build(values)
        self.assertEqual(len(result['topics']), 2)
        for row in result['source_links'].values():
            self.assertEqual(row['source_record_indices'], [0, 1])
            self.assertEqual(len(row['source_records']), 2)
            self.assertNotIn('batch_id', row)
        payload['dominante_muster'].reverse()
        self.assertEqual(build(values)['topics'], result['topics'])

    def test_same_title_different_definitions_does_not_guess_countercase_binding(self):
        values = contrast_fixture(); payload = values[-1]
        payload['dominante_muster'].append({**payload['dominante_muster'][0], 'beschreibung': 'Eine andere vollständige Aussage.'})
        result = build(values)
        self.assertEqual(len(result['topics']), 2)
        self.assertEqual({row['scope_kind'] for row in result['source_links'].values()}, {'global_pattern'})
        self.assertIn('ambiguous_pattern_reference', [row['reason'] for row in result['unassigned_context']['records']])
        self.assertTrue(all(row['countercase_topic_ids'] == [] for row in result['source_links'].values()))

    def test_unresolved_text_and_empty_candidates_remain_context_not_zero(self):
        for reference in ('planbarkeit', 'Zeitgestaltung', '', 'Planbarkeit.'):
            values = contrast_fixture(); values[-1]['negativfaelle'][0]['bezugs_muster'] = reference
            result = build(values)
            self.assertEqual(len(result['topics']), 1)
            record = next(row for row in result['unassigned_context']['records'] if row['section'] == 'negativfaelle')
            self.assertEqual(record['reason'], 'incomplete_candidate' if not reference else 'unresolved_pattern_reference')
            self.assertEqual(record['record']['bezugs_muster'], reference)
        values = contrast_fixture(); values[-1]['dominante_muster'][0]['beschreibung'] = ''
        values[-1]['negativfaelle'][0]['abweichung'] = ''
        self.assertEqual(build(values)['topics'], [])

    def test_empty_case_reason_is_valid_and_no_polarity_is_seeded(self):
        values = contrast_fixture(); values[-1]['negativfaelle'][0]['begruendung'] = ''
        result = build(values)
        self.assertEqual(len(result['topics']), 2)
        self.assertIsNone(result['assignments'])

    def test_foreign_references_fail_even_for_uncounted_or_incomplete_findings(self):
        for kind in ('pattern', 'case', 'type', 'source'):
            values = contrast_fixture(); payload = values[-1]
            if kind == 'pattern': payload['dominante_muster'][0].update(beschreibung='', getragen_von=['foreign'])
            if kind == 'case': payload['negativfaelle'][0].update(bezugs_muster='unknown', person='foreign')
            if kind == 'type': payload['spannungen_zwischen_typen'][0]['typen'] = ['foreign']
            if kind == 'source': values[1]['persons']['P01']['gesamtverdichtung'] = 'changed'
            with self.subTest(kind=kind), self.assertRaises(ValueError): build(values)

    def test_ambiguous_type_is_context_not_membership(self):
        values = contrast_fixture(); comparison = values[2]
        comparison['typen'].append({**comparison['typen'][0], 'beschreibung': 'Eine andere Typdefinition.'})
        result = build(values)
        self.assertIn('ambiguous_type_reference', [row['reason'] for row in result['unassigned_context']['records']])
        self.assertEqual(len(result['topics']), 2)

    def test_reduced_receipts_bind_exact_projection_every_person_and_reuse(self):
        for kind in ('parts', 'missing_person', 'comparison_hash', 'person_hash', 'reuse_summary', 'false_reuse', 'timestamp'):
            values = contrast_fixture(reduced=True); payload = values[-1]; receipt = payload['input_reduction']
            if kind == 'parts': receipt['parts'] = True
            if kind == 'missing_person': del receipt['persons']['P02']
            if kind == 'comparison_hash': receipt['comparison']['source_sha256'] = fingerprint(values[2])
            if kind == 'person_hash': receipt['persons']['P02']['source_sha256'] = 'wrong'
            if kind == 'reuse_summary': receipt['persons']['P02']['summary'] += 'changed'
            if kind == 'false_reuse': receipt['persons']['P02']['reused_comparison_summary'] = False
            if kind == 'timestamp': payload['source_person_comparison_created_at'] = 'foreign'
            with self.subTest(kind=kind), self.assertRaises(ValueError): build(values)

    def test_fresh_compact_receipts_support_reduced_and_unreduced_person_inputs(self):
        values = contrast_fixture(reduced=True); receipt = values[-1]['input_reduction']
        receipt['persons']['P01'] = {'used': False, 'source_sha256': fingerprint(values[1]['persons']['P01'])}
        receipt['persons']['P02'] = {'used': True, 'source_sha256': fingerprint(values[1]['persons']['P02']), 'summary': 'Fresh compact context.', 'note': 'Synthetic.'}
        receipt['comparison'].update(used=True, summary='Vollständiger synthetischer Vergleich.', note='Synthetic.')
        self.assertEqual(len(build(values)['topics']), 2)

    def test_extensions_removed_and_mutable_return_does_not_touch_sources(self):
        values = contrast_fixture(reduced=True); expected = build(values)
        for value in values[1:]: value['analysis_perspective'] = {'text': 'Additional weighted output ' * 1000}
        before = copy.deepcopy(values)
        result = build(values)
        self.assertEqual(result, expected); self.assertEqual(values, before)
        result['source_links'][result['topics'][0]['topic_id']]['source_records'].clear()
        result['unassigned_context']['records'].clear(); result['qualitative_source']['negativfaelle'].clear()
        self.assertEqual(values, before)

    def test_actual_core_unreduced_fresh_reduced_and_reused_reduced(self):
        for mode in ('unreduced', 'fresh', 'reused'):
            values = contrast_fixture(reduced=mode == 'reused')
            material, source, comparison, expected = values
            if mode != 'unreduced':
                for person in source['persons']: source['persons'][person]['gesamtverdichtung'] = 'Langer synthetischer Originalkontext. ' * 1000
                comparison['input_reduction']['source_sha256'] = fingerprint(source['persons'])
                for person, receipt in comparison['input_reduction'].get('sources', {}).items():
                    receipt['source_sha256'] = fingerprint(source['persons'][person])
            response = {key: expected[key] for key in ('dominante_muster', 'negativfaelle', 'spannungen_zwischen_typen', 'relativierungen', 'gesamteinordnung')}
            with tempfile.TemporaryDirectory() as temp, \
                 patch('contrast_analysis_core.llm_contrast_analysis', return_value=json.dumps(response)), \
                 patch('analysis_context.reduce_prompt', return_value='Vollständiger kurzer synthetischer Hintergrund.'):
                root = Path(temp); a = root/'persons.json'; b = root/'comparison.json'
                a.write_text(json.dumps(source), encoding='utf-8'); b.write_text(json.dumps(comparison), encoding='utf-8')
                before = (a.read_bytes(), b.read_bytes())
                _, payload = build_contrast_analysis(a, b,
                    {'model': 'synthetic', 'num_ctx': 8000 if mode != 'unreduced' else 32768,
                     'max_tokens': 512, 'partial_checkpoints': False, 'parallel_workers': 1},
                    {'contrast_analysis': {'system': 'Synthetic', 'user': '{data}'}}, {})
                self.assertEqual((a.read_bytes(), b.read_bytes()), before)
                self.assertEqual(payload['input_reduction']['used'], mode != 'unreduced')
                if mode != 'unreduced':
                    self.assertEqual([r.get('reused_comparison_summary', False) for r in payload['input_reduction']['persons'].values()], [mode == 'reused'] * 2)
                result = build_contrast_topics(material, payload, source, comparison)
                self.assertEqual(len(result['topics']), 2)


if __name__ == '__main__': unittest.main()
