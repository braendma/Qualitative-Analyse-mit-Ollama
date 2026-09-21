import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
from diarization_core import align_word, probability_turns, placement_metrics, validate_turns
from sortformer_features import extract_features, mel_filterbank
from sortformer_streaming import compress_cache
from speaker_review import make_draft, validate_draft, finish
from workspace_store import ProjectStore


def packet():
    return {'audio_sha256': 'synthetic', 'duration': 2, 'turns': [], 'segments': [
        {'id': 1, 'text': 'Hallo Welt', 'start': 0, 'end': 2, 'words': [
            {'word': 'Hallo', 'start': 0, 'end': 1, 'speaker': 'SPEAKER_01', 'reason': 'suggested'},
            {'word': ' Welt', 'start': 1, 'end': 2, 'speaker': None, 'reason': 'overlap_or_boundary'}]}]}


class DiarizationTests(unittest.TestCase):
    def test_overlap_boundary_short_and_missing_are_unknown(self):
        turns = [{'start': 0, 'end': 1, 'speaker': 'A'}, {'start': .8, 'end': 2, 'speaker': 'B'}]
        self.assertEqual(align_word(.1, .7, turns)['speaker'], 'A')
        self.assertIsNone(align_word(.7, .9, turns)['speaker'])
        self.assertIsNone(align_word(.9, 1.1, turns)['speaker'])
        self.assertIsNone(align_word(2, 3, turns)['speaker'])
        self.assertIsNone(align_word(1, 1, turns)['speaker'])
        self.assertIsNone(align_word(.01, .06, [{'start': 0, 'end': .08, 'speaker': 'A', 'short': True}])['speaker'])

    def test_duplicate_turns_do_not_inflate_coverage(self):
        turn = {'start': 0, 'end': .4, 'speaker': 'A'}
        self.assertIsNone(align_word(0, 1, [turn, turn])['speaker'])

    def test_probabilities_retain_overlap_short_activity_and_bound_audio(self):
        turns = probability_turns([[.9, .8, 0, 0], [.9, 0, 0, 0]], .13)
        self.assertEqual({t['speaker'] for t in turns}, {'SPEAKER_01', 'SPEAKER_02'})
        self.assertTrue(all(t['short'] for t in turns))
        self.assertLessEqual(max(t['end'] for t in turns), .13)
        with self.assertRaises(ValueError): validate_turns([{'speaker': 'A', 'start': float('nan'), 'end': 1}], 2)

    def test_feature_frontend_finite_short_silence_shapes_and_mel(self):
        features, lengths = extract_features(np.zeros(320, dtype=np.float32))
        self.assertEqual(features.shape, (1, 80, 16))
        self.assertEqual(lengths.tolist(), [2])
        self.assertTrue(np.isfinite(features).all())
        self.assertEqual(extract_features(np.zeros(320, dtype=np.float32), streaming=True).shape, (1, 3, 128))
        self.assertEqual(mel_filterbank(128).shape, (128, 257))
        with self.assertRaises(ValueError): extract_features(np.zeros(100))
        with self.assertRaises(ValueError): extract_features(np.full(320, np.nan))

    def test_cache_compression_is_bounded_and_finite(self):
        rng = np.random.default_rng(2)
        embeddings = rng.normal(size=(312, 512)).astype(np.float32)
        probabilities = np.zeros((312, 4), np.float32)
        probabilities[np.arange(312), np.arange(312) % 3] = .98
        cache, scores = compress_cache(embeddings, probabilities, np.zeros(512, np.float32))
        self.assertEqual(cache.shape, (188, 512))
        self.assertEqual(scores.shape, (188, 4))
        self.assertTrue(np.isfinite(cache).all())

    def test_metrics_permutation_and_misses_are_reported_separately(self):
        reference = [{'start': 0, 'end': 1, 'speaker': 'person1'}, {'start': 1, 'end': 2, 'speaker': 'person2'}]
        prediction = [{'start': 0, 'end': .5, 'speaker': 'B'}, {'start': 1, 'end': 2, 'speaker': 'A'}]
        result = placement_metrics(reference, prediction, 2, collar=0)
        self.assertEqual(result['matched_fraction_when_single_speaker_detected'], 1)
        self.assertEqual(result['seconds']['missed'], .5)
        self.assertIn('not_human', result['reference_kind'])

    def test_speaker_labels_never_auto_confirm_persons(self):
        p = packet()
        draft = make_draft(p)
        self.assertTrue(all(g['person'] == '' for g in draft['groups']))
        with self.assertRaises(ValueError): finish(p, draft, 'Tester', True)
        for group in draft['groups']:
            group.update(person='P01', speaker='Korrigierter Sprecher')
        with self.assertRaises(ValueError): finish(p, draft, 'Tester', False)
        result = finish(p, draft, 'Tester', True)
        self.assertTrue(result['transcript']['person_mapping_confirmed'])
        self.assertEqual(result['project']['documents'][0]['segments'][0]['person'], 'P01')

    def test_source_partition_and_binding_protect_words(self):
        p = packet()
        original = make_draft(p)
        bad = copy.deepcopy(original)
        bad['groups'][0]['last'] = 2
        with self.assertRaises(ValueError): validate_draft(p, bad)
        bad = copy.deepcopy(original)
        bad['packet_sha256'] = 'other'
        with self.assertRaises(ValueError): validate_draft(p, bad)
        original['groups'][1]['exclude'] = True
        original['groups'][0]['person'] = 'P01'
        result = finish(p, original, 'Tester', True)
        self.assertTrue(result['project']['documents'][0]['segments'][1]['exclude'])
        self.assertEqual(len(result['project']['documents'][0]['segments']), 2)

    def test_review_autosave_conflict_and_reload(self):
        p = packet()
        draft = make_draft(p)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'speaker.json'
            create = lambda: ProjectStore(path, validator=lambda v: validate_draft(p, v), initial=draft)
            store = create()
            draft['groups'][0]['person'] = 'P01'
            store.save(draft, 0, 'review1')
            self.assertEqual(create().get()['project'], draft)
            with self.assertRaisesRegex(ValueError, 'Speicherkonflikt'): store.save(draft, 0, 'stale')


if __name__ == '__main__': unittest.main()
