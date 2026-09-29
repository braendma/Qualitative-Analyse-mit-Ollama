import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from interpretation_review import review_hints, count_explanation
from report_annotations import editable_fields


class InterpretationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((Path(__file__).parent / 'fixtures/interpretation_review.json').read_text(encoding='utf-8'))

    def test_eight_previously_reviewed_synthetic_cases(self):
        for case in self.cases:
            with self.subTest(case=case['case']):
                before = copy.deepcopy(case)
                hints = review_hints(case['text'], case['evidence'], case['row'])
                codes = {h['code'] for h in hints}
                if case['expected']:
                    self.assertTrue(set(case['expected']) <= codes, codes)
                else:
                    self.assertEqual(codes, set(), 'Explicit exclusion must not become a positive claim')
                self.assertEqual(case, before)

    def test_unseen_claims_and_explicit_exclusions(self):
        for text in ['Der Anteil belegt eine kausale Wirkung.',
                     'Unsere Häufigkeit zeigt die Wirksamkeit der Maßnahme.',
                     'Die Repräsentativität wird durch diesen Anteil bestätigt.']:
            self.assertIn('unsupported_inference', {h['code'] for h in review_hints(text)})
        for text in ['Der Anteil belegt keine kausale Wirkung.',
                     'Dies bestätigt weder Repräsentativität noch Kausalität.',
                     'Daraus folgt kein Nachweis der Wirksamkeit.',
                     'Die Wirkung wurde nicht nachgewiesen.',
                     'Der Befund zeigt, dass die Person die Maßnahme als wirksam wahrnimmt.',
                     'Das Material stützt die Einschätzung einer effektiven Reaktion im beschriebenen Fall.',
                     'Der Anteil zeigt die begrenzte Repräsentativität des Befunds.',
                     'complete: true bedeutet vollständige Bearbeitung, keine Validierung.',
                     'both bedeutet nicht, dass alle Personen das Thema nennen.',
                     'both bedeutet Stützung und Widerspruch zur selben Aussage.']:
            self.assertEqual(review_hints(text), [], text)

    def test_negation_candidates_need_bound_lexical_context(self):
        evidence = [{'id':'S1', 'text':'Der Drucker startet nicht auf dem Leihgerät.'}]
        hints = review_hints('Der Drucker startet auf dem Leihgerät.', evidence)
        self.assertEqual(hints[0]['code'], 'possible_negation_loss')
        self.assertEqual(hints[0]['evidence_ids'], ['S1'])
        for text in ['Der Drucker startet nicht auf dem Leihgerät.', 'Die Software startet am Notebook.']:
            self.assertEqual(review_hints(text, evidence), [])
        self.assertEqual(review_hints('Der Drucker startet auf dem Leihgerät.'), [])

    def test_computed_explanation_preserves_unknown_and_scope(self):
        row = copy.deepcopy(self.cases[4]['row'])
        row['counts']['supporting']['exact_person_count'] = None
        text = count_explanation(row)
        self.assertIn('beobachtet 1 Personen', text)
        self.assertIn('nicht bestimmbar Personen', text)
        self.assertIn('4 Personen', text)
        self.assertIn('keine direkte Zustimmung', text)
        self.assertIn('keine Gegenposition', text)

    def test_annotations_bind_hints_without_changing_content_or_review_identity(self):
        case = self.cases[2]
        row = copy.deepcopy(case['row']); row['topic_id'] = 'T'
        payload = {'analysis_perspective': {'counting': {'topics':[row]},
            'source_links': {'T': {'selected_evidence_segment_ids':['S']}},
            'interpretations': {'frequency':[{'topic_id':'T', 'interpretation':case['text']}]}}}
        before = copy.deepcopy(payload)
        field = editable_fields(case['text'], payload, {'S':'Unverändertes Originalzitat'})['0']
        self.assertIn('derived_not_explicit', {h['code'] for h in field['automatic_review_hints']})
        self.assertEqual(field['original'], case['text'])
        self.assertEqual(field['path'][-1], 'interpretation')
        self.assertIn('count_explanation', field)
        self.assertEqual(payload, before)
        # Added output explanations do not invalidate existing human edit history.
        payload['analysis_perspective'].pop('counting')
        self.assertEqual(field['source_sha256'], editable_fields(case['text'], payload, {'S':'Unverändertes Originalzitat'})['0']['source_sha256'])


if __name__ == '__main__':
    unittest.main()
