import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from overall_synthesis_core import build_overall_synthesis
from synthesis_countability import select_countable_findings
from thematic_synthesis_adapter import build_overall_synthesis_topics
from thematic_counts import count_topics
from test_thematic_memberships import fixture
from test_thematic_adapters import summary


PARAMS = {'model': 'synthetic', 'num_ctx': 32768, 'max_tokens': 512, 'partial_checkpoints': False}


def synthesis_fixture(*, reduced=False):
    material, clusters = fixture()
    summaries = summary(clusters)
    sources = {'First alias': summaries, 'Second alias': clusters}
    bindings = {'First alias': {'module_id': 'summarizer'}, 'Second alias': {'module_id': 'clusterer'}}
    upstream = {'summarizer': summaries, 'clusterer': clusters}
    def final(system, user, params):
        refs = json.loads(user)['verfuegbare_analytische_quellen']
        return json.dumps({'kernergebnisse': [
            {'thema': 'Planbarkeit', 'verdichtung': 'Planbare Arbeitszeiten werden als Hilfe beschrieben.', 'quellen': refs},
            {'thema': 'Verteilung', 'verdichtung': 'Gruppe A spricht häufiger über Planbarkeit als Gruppe B.', 'quellen': refs}],
            'uebergreifende_muster': [], 'spannungen_und_relativierungen': [],
            'methodische_einordnung': ['Keine Repräsentativität.'], 'gesamtsynthese': ''})
    with tempfile.TemporaryDirectory() as temp, patch('overall_synthesis_core.llm_overall_synthesis', side_effect=final), \
         patch('coding_validation_common.default_llm', return_value=json.dumps({'summary': 'Synthetische Verdichtung.'})):
        paths = {}
        for i, (label, source) in enumerate(sources.items()):
            path = Path(temp, str(i) + '.json'); path.write_text(json.dumps(source), encoding='utf-8'); paths[label] = path
        _, payload = build_overall_synthesis(paths, {**PARAMS, 'hierarchical_synthesis': {'force': reduced, 'batch_items': 2}},
                                            {'overall_synthesis': {'system': 'Synthetic', 'user': '{data}'}}, {})
    def classify(messages, params):
        candidate = json.loads(messages[1]['content'])['candidate']
        label = candidate['original_record']['thema']
        return json.dumps({'candidate_id': candidate['candidate_id'],
                           'classification': 'material_assertion' if label == 'Planbarkeit' else 'group_comparison',
                           'reason': 'Synthetisch festgelegte Klassifikation.'})
    selection = select_countable_findings(payload, PARAMS, llm=classify)
    return material, payload, sources, selection, bindings, upstream


class SynthesisAdapterTests(unittest.TestCase):
    def prepare(self, args):
        return build_overall_synthesis_topics(*args[:4], bindings=args[4], upstream_payloads=args[5])

    def test_classified_full_statement_gets_all_material_not_source_counts(self):
        for reduced in (False, True):
            with self.subTest(reduced=reduced):
                args = synthesis_fixture(reduced=reduced); before = copy.deepcopy(args)
                prepared = self.prepare(args)
                self.assertEqual(args, before)
                self.assertEqual(len(prepared['topics']), 1)
                self.assertEqual(prepared['topics'][0]['scope_unit_ids'], sorted(args[0]['units']))
                self.assertIsNone(prepared['assignments'])
                counted = count_topics(args[0], prepared['topics'], [])
                self.assertEqual(counted['topics'][0]['scope']['person_count'], 2)
                self.assertEqual(counted['topics'][0]['scope']['unit_count'], 3)
                self.assertIsNone(counted['topics'][0]['counts']['mentioned']['exact_person_count'])
                contexts = prepared['unassigned_context']['records']
                self.assertTrue(any(r.get('classification') == 'group_comparison' for r in contexts))
                self.assertTrue(any(r['section'] == 'methodische_einordnung' for r in contexts))
                self.assertTrue(any(r['section'] == 'gesamtsynthese' for r in contexts))
                link = next(iter(prepared['source_links'].values()))
                self.assertEqual(link['human_review_status'], 'not_reviewed')
                self.assertNotIn('segment_ids', link)

    def test_changed_inputs_or_selection_and_old_unbound_output_fail(self):
        for change in ('source', 'selection', 'old_output', 'missing_upstream'):
            with self.subTest(change=change):
                args = synthesis_fixture()
                if change == 'source':
                    args[2]['First alias']['final_summary'] = 'Different source'
                elif change == 'selection':
                    args[3]['decisions'][0]['reason'] = 'Changed reason'
                elif change == 'old_output':
                    del args[1]['source_projection_fingerprints']
                else:
                    del args[5]['clusterer']
                with self.assertRaises(ValueError):
                    self.prepare(args)


if __name__ == '__main__':
    unittest.main()
