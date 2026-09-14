"""Complete original findings, strict model decisions and no silent exclusions."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from overall_synthesis_core import normalize_overall_synthesis
from synthesis_countability import (CLASSIFICATIONS, CONTRACT, finding_registry,
                                    select_countable_findings, validate_selection)
from thematic_counts import _hash


def synthesis_fixture():
    entries = [
        ('Material', 'Planbare Arbeitszeiten werden als Hilfe für die Vereinbarkeit beschrieben.'),
        ('Menge', 'Planbarkeit wird häufiger als Einkommen genannt.'),
        ('Gruppe', 'Berufserfahrene gewichten Planbarkeit stärker als andere Studierende.'),
        ('Methode', 'Die drei Analysen stimmen bei Planbarkeit überein.'),
        ('Kausal', 'Planbarkeit verursacht höhere Studienzufriedenheit.'),
        ('Gemischt', 'Planbare Zeiten helfen; außerdem bevorzugt die Mehrheit diesen Beruf.')]
    payload = normalize_overall_synthesis({'kernergebnisse': [
        {'thema': title, 'verdichtung': text, 'quellen': ['Analyse A']} for title, text in entries],
        'uebergreifende_muster': [], 'spannungen_und_relativierungen': [],
        'methodische_einordnung': ['Die Stichprobe ist begrenzt.']}, ['Analyse A'])
    payload.update(created_at='synthetic-synthesis', source_labels=['Analyse A'],
        source_created_at={'Analyse A': 'synthetic-source'}, hierarchical_reduction={'used': False})
    return payload


class Classifier:
    choices = dict(zip(('Material', 'Menge', 'Gruppe', 'Methode', 'Kausal', 'Gemischt'), CLASSIFICATIONS))

    def __init__(self):
        self.calls = []
        self.fail_at = None

    def __call__(self, messages, params):
        self.calls.append(copy.deepcopy((messages, params)))
        if self.fail_at == len(self.calls):
            raise RuntimeError('Synthetic interrupted classification')
        candidate = json.loads(messages[1]['content'])['candidate']
        return json.dumps({'candidate_id': candidate['candidate_id'],
            'classification': self.choices[candidate['original_record']['thema']],
            'reason': 'Synthetische modellseitige Einordnung der vollständigen Aussage.'})


class SynthesisCountabilityTests(unittest.TestCase):
    def setUp(self):
        self.params = {'model': 'synthetic', 'num_ctx': 32768, 'max_tokens': 1000,
                       'parallel_workers': 1, 'partial_checkpoints': False}
        for name in ('analysis_work.update_progress', 'runtime_context.update_progress', 'synthesis_countability.begin_phase'):
            handle = patch(name); handle.start(); self.addCleanup(handle.stop)

    def test_real_normalized_originals_partition_all_six_classes(self):
        payload = synthesis_fixture(); original = copy.deepcopy(payload); llm = Classifier()
        receipt = select_countable_findings(payload, self.params, llm=llm)
        selected = validate_selection(payload, receipt)
        self.assertEqual(payload, original)
        self.assertEqual(len(llm.calls), 6)
        self.assertEqual({row['classification'] for row in receipt['decisions']}, set(CLASSIFICATIONS))
        self.assertEqual(len(selected['selected']), 1)
        self.assertEqual(selected['selected'][0]['original_record'], payload['kernergebnisse'][0])
        self.assertEqual(len(selected['context']), 7)  # Five model exclusions + method + composed summary.
        self.assertEqual(receipt['human_review_status'], 'not_reviewed')
        self.assertEqual(receipt['selection_origin'], 'model_classification')
        self.assertEqual(receipt['classification_contract'], CONTRACT)
        self.assertTrue(all('material_assertion' != row.get('classification') for row in selected['context']))

    def test_prompts_keep_full_claim_and_sources_without_raw_material_or_rewrites(self):
        payload = synthesis_fixture(); llm = Classifier()
        payload['source_created_at']['Analyse A'] = 'SYNTHETIC_NOT_RAW_MATERIAL'
        select_countable_findings(payload, self.params, llm=llm)
        for messages, params in llm.calls:
            value = json.loads(messages[1]['content']); candidate = value['candidate']
            self.assertIn(candidate['original_record'], payload['kernergebnisse'])
            self.assertIn(candidate['original_record']['verdichtung'], candidate['definition'])
            self.assertEqual(candidate['source_references'], ['Analyse A'])
            self.assertNotIn('SYNTHETIC_NOT_RAW_MATERIAL', messages[1]['content'])
            schema = params['response_schema']
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(schema['properties']['candidate_id']['enum'], [candidate['candidate_id']])
            self.assertEqual(set(schema['properties']['classification']['enum']), set(CLASSIFICATIONS))

    def test_fixed_empty_method_and_composed_context_never_request_classification(self):
        payload = synthesis_fixture()
        payload['kernergebnisse'] = [{'thema': 'Unvollständig', 'verdichtung': '', 'quellen': ['Analyse A']}]
        llm = Classifier(); receipt = select_countable_findings(payload, self.params, llm=llm)
        self.assertEqual(llm.calls, [])
        self.assertEqual(receipt['decisions'], [])
        result = validate_selection(payload, receipt)
        self.assertEqual(result['selected'], [])
        self.assertEqual({row['reason'] for row in result['context']},
                         {'incomplete_candidate', 'methodical_context', 'composed_summary_context'})
        self.assertTrue(all(row['selection_origin'] == 'fixed_context' for row in result['context']))

    def test_every_normalized_finding_section_keeps_original_fields(self):
        payload = synthesis_fixture()
        row = payload['kernergebnisse'][0]
        payload['uebergreifende_muster'] = [copy.deepcopy(row)]
        payload['spannungen_und_relativierungen'] = [{'aussage': 'Eine Gegenposition.',
            'einordnung': 'Ein vollständiger künstlicher Kontext.', 'quellen': ['Analyse A']}]
        registry = finding_registry(payload)
        self.assertEqual(len(registry['candidates']), 8)
        self.assertEqual({row['section'] for row in registry['candidates']},
                         {'kernergebnisse', 'uebergreifende_muster', 'spannungen_und_relativierungen'})
        self.assertEqual(len({row['candidate_id'] for row in registry['candidates']}), 8)

    def test_unknown_source_and_duplicate_findings_fail_before_calls(self):
        for change in ('foreign_source', 'empty_source', 'duplicate', 'missing_section', 'extra_record_field'):
            payload = synthesis_fixture(); llm = Classifier()
            if change == 'foreign_source': payload['kernergebnisse'][0]['quellen'] = ['FOREIGN_PRIVATE_LABEL']
            if change == 'empty_source': payload['kernergebnisse'][0]['quellen'] = []
            if change == 'duplicate': payload['kernergebnisse'].append(copy.deepcopy(payload['kernergebnisse'][0]))
            if change == 'missing_section': payload.pop('uebergreifende_muster')
            if change == 'extra_record_field': payload['kernergebnisse'][0]['new_claim'] = 'Do not accept'
            with self.subTest(change=change), self.assertRaises(ValueError) as caught:
                select_countable_findings(payload, self.params, llm=llm)
            self.assertEqual(llm.calls, [])
            self.assertNotIn('FOREIGN_PRIVATE_LABEL', str(caught.exception))

    def test_reduced_references_must_be_final_nodes_not_labels_or_leaves(self):
        payload = synthesis_fixture(); payload['hierarchical_reduction'] = {'used': True, 'final_node_ids': ['Nfinal']}
        for row in payload['kernergebnisse']: row['quellen'] = ['Nfinal']
        self.assertEqual(len(finding_registry(payload)['candidates']), 6)
        for reference in ('Analyse A', 'Lleaf', 'Nother'):
            bad = copy.deepcopy(payload); bad['kernergebnisse'][0]['quellen'] = [reference]
            with self.assertRaises(ValueError): finding_registry(bad)

    def test_exactly_one_format_repair_preserves_original_user_message(self):
        payload = synthesis_fixture(); payload['kernergebnisse'] = payload['kernergebnisse'][:1]
        llm = Classifier(); seen = []
        def backend(messages, params):
            seen.append(copy.deepcopy(messages))
            return '{bad' if len(seen) == 1 else llm(messages, params)
        receipt = select_countable_findings(payload, self.params, llm=backend)
        self.assertEqual(len(receipt['decisions']), 1)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0][1], seen[1][1])
        self.assertNotIn('{bad', json.dumps(seen[1]))
        self.assertEqual(len(seen[1]), 3)

    def test_unknown_class_wrong_id_missing_reason_rewrite_and_duplicate_keys_never_become_exclusions(self):
        payload = synthesis_fixture(); payload['kernergebnisse'] = payload['kernergebnisse'][:1]
        for kind in ('class', 'id', 'reason', 'rewrite', 'duplicate'):
            calls = []
            def backend(messages, params):
                calls.append(1)
                cid = json.loads(messages[1]['content'])['candidate']['candidate_id']
                row = {'candidate_id': cid, 'classification': 'material_assertion', 'reason': 'Grund'}
                if kind == 'class': row['classification'] = 'anything'
                if kind == 'id': row['candidate_id'] = 'foreign'
                if kind == 'reason': row['reason'] = ' '
                if kind == 'rewrite': row['rewritten_claim'] = 'A new claim'
                if kind == 'duplicate': return json.dumps(row)[:-1] + ',"classification":"mixed_or_unclear"}'
                return json.dumps(row)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                select_countable_findings(payload, self.params, llm=backend)
            self.assertEqual(len(calls), 2)

    def test_all_original_and_correction_prompts_preflight_before_any_model_call(self):
        payload = synthesis_fixture(); payload['kernergebnisse'][1]['verdichtung'] = 'Langer künstlicher Satz. ' * 10000
        llm = Classifier()
        with self.assertRaises(Exception) as caught: select_countable_findings(payload, self.params, llm=llm)
        self.assertIn('context', type(caught.exception).__name__.lower())
        self.assertEqual(llm.calls, [])

    def test_changed_originals_or_saved_decisions_fail_pure_replay(self):
        payload = synthesis_fixture(); receipt = select_countable_findings(payload, self.params, llm=Classifier())
        for change in ('original', 'source', 'registry', 'missing', 'duplicate', 'review', 'hash', 'schema'):
            source = copy.deepcopy(payload); saved = copy.deepcopy(receipt)
            if change == 'original': source['kernergebnisse'][0]['verdichtung'] += ' changed'
            if change == 'source': source['source_created_at']['Analyse A'] = 'changed'
            if change == 'registry': saved['candidate_registry_fingerprint'] = '0' * 64
            if change == 'missing': saved['decisions'].pop()
            if change == 'duplicate': saved['decisions'][1] = copy.deepcopy(saved['decisions'][0])
            if change == 'review': saved['human_review_status'] = 'confirmed'
            if change == 'hash': saved['result_fingerprint'] = '0' * 64
            if change == 'schema': saved['schema_version'] = True
            if change != 'hash': saved['result_fingerprint'] = _hash({k: v for k, v in saved.items() if k != 'result_fingerprint'})
            with self.subTest(change=change), self.assertRaises(ValueError): validate_selection(source, saved)

    def test_weighted_extension_ignored_and_returns_do_not_mutate_inputs(self):
        payload = synthesis_fixture(); baseline = select_countable_findings(payload, self.params, llm=Classifier())
        payload['analysis_perspective'] = {'arbitrary': 'Additional interpretation' * 1000}
        receipt = select_countable_findings(payload, self.params, llm=Classifier())
        self.assertEqual(receipt, baseline)
        selected = validate_selection(payload, receipt)
        selected['selected'][0]['original_record']['verdichtung'] = 'mutated copy'
        self.assertNotEqual(payload['kernergebnisse'][0]['verdichtung'], 'mutated copy')

    def test_cached_answers_are_revalidated_not_trusted(self):
        with patch('synthesis_countability.analyze_items', return_value=[{'classification': 'material_assertion'}] * 6):
            with self.assertRaises(ValueError): select_countable_findings(synthesis_fixture(), self.params, llm=Classifier())

    def test_actual_checkpoint_resume_reuses_only_completed_original_tasks(self):
        # Run with shared sources frozen, like the existing thematic checkpoint tests.
        with tempfile.TemporaryDirectory() as tmp:
            params = {**self.params, 'partial_checkpoints': True, 'partial_checkpoint_dir': tmp}
            payload = synthesis_fixture(); llm = Classifier(); llm.fail_at = 2
            with self.assertRaisesRegex(RuntimeError, 'Synthetic interrupted'):
                select_countable_findings(payload, params, llm=llm)
            llm.fail_at = None
            receipt = select_countable_findings(payload, params, llm=llm)
            self.assertEqual(len(llm.calls), 7)  # One accepted + one failed + five remaining.
            self.assertEqual(len(validate_selection(payload, receipt)['selected']), 1)
            select_countable_findings(payload, params, llm=llm)
            self.assertEqual(len(llm.calls), 7)


if __name__ == '__main__':
    unittest.main()
