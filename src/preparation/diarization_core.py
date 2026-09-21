"""Model-independent diarization validation, conservative alignment and fixture metrics."""
import itertools
import math
from collections import defaultdict


def validate_turns(turns, duration):
    for turn in turns:
        if not isinstance(turn.get('speaker'), str) or not turn['speaker']:
            raise ValueError('Speaker label missing.')
        if not all(type(turn.get(k)) in (int, float) and math.isfinite(turn[k]) for k in ('start', 'end')):
            raise ValueError('Invalid speaker interval.')
        if not 0 <= turn['start'] < turn['end'] <= duration + 1e-6:
            raise ValueError('Speaker interval outside audio.')
    return turns


def probability_turns(probabilities, duration, threshold=.5, minimum=.16, step=.08):
    """Independent per-speaker thresholds preserve simultaneous activity.

    Scores are model outputs, not calibrated confidence in a research identity.
    Short detected activity is retained with an uncertainty flag, never silently lost.
    """
    turns = []
    for speaker in range(4):
        start = None
        for frame in range(len(probabilities) + 1):
            active = frame < len(probabilities) and probabilities[frame][speaker] >= threshold and frame * step < duration
            if active and start is None:
                start = frame
            if start is not None and not active:
                end = min(frame * step, duration)
                if end > start * step:
                    turns.append({'start': round(start * step, 6), 'end': round(end, 6),
                        'speaker': f'SPEAKER_{speaker + 1:02}', 'short': end - start * step < minimum,
                        'mean_activity_score': float(sum(float(p[speaker]) for p in probabilities[start:frame]) / (frame - start))})
                start = None
    return validate_turns(sorted(turns, key=lambda x: (x['start'], x['speaker'])), duration)


def union_duration(intervals):
    total = 0.
    stop = -math.inf
    for start, end in sorted(intervals):
        total += max(0., end - max(start, stop))
        stop = max(stop, end)
    return total


def align_word(start, end, turns, minimum_fraction=.6):
    if end <= start:
        return {'speaker': None, 'reason': 'zero_duration', 'candidates': []}
    overlaps = defaultdict(list)
    short = set()
    for turn in turns:
        left, right = max(start, turn['start']), min(end, turn['end'])
        if right > left:
            overlaps[turn['speaker']].append((left, right))
            if turn.get('short'):
                short.add(turn['speaker'])
    ranked = sorted(((k, union_duration(v)) for k, v in overlaps.items()), key=lambda x: (-x[1], x[0]))
    candidates = [x[0] for x in ranked]
    if len(ranked) > 1:
        return {'speaker': None, 'reason': 'overlap_or_boundary', 'candidates': candidates}
    if not ranked or ranked[0][1] / (end - start) < minimum_fraction:
        return {'speaker': None, 'reason': 'insufficient_activity', 'candidates': candidates}
    if ranked[0][0] in short:
        return {'speaker': None, 'reason': 'short_activity', 'candidates': candidates}
    return {'speaker': ranked[0][0], 'reason': 'suggested', 'candidates': candidates}


def placement_metrics(reference, predicted, duration, step=.02, collar=.25):
    """Diagnostic against synthetic clip placement, NOT speech-activity gold DER.

    Permutation matching uses interior singleton reference frames. Pauses within clips
    remain reference activity, so misses are reported separately, not called accuracy.
    """
    labels = sorted({t['speaker'] for t in predicted})
    refs = sorted({t['speaker'] for t in reference})
    if len(labels) > 4 or len(refs) > 4:
        raise ValueError('Fixture matching bounded to four speakers.')
    frames = [(i + .5) * step for i in range(int(duration / step))]
    records = []
    for time in frames:
        real = {t['speaker'] for t in reference if t['start'] + collar <= time < t['end'] - collar}
        pred = {t['speaker'] for t in predicted if t['start'] <= time < t['end']}
        records.append((real, pred))
    choices = refs + [f'UNMATCHED_{i}' for i in range(max(0, len(labels) - len(refs)))]
    best, best_score = {}, -1
    for permutation in itertools.permutations(choices, len(labels)):
        mapping = dict(zip(labels, permutation))
        score = sum(len(r) == len(p) == 1 and next(iter(r)) == mapping[next(iter(p))] for r, p in records)
        if score > best_score:
            best, best_score = mapping, score
    counts = defaultdict(int)
    for real, pred in records:
        mapped = {best.get(s, s) for s in pred}
        if len(real) == 1:
            counts['reference_single_frames'] += 1
            if not pred: counts['missed_frames'] += 1
            elif len(pred) > 1: counts['extra_overlap_frames'] += 1
            elif mapped == real: counts['correct_single_frames'] += 1
            else: counts['wrong_single_frames'] += 1
        elif len(real) > 1:
            counts['reference_overlap_frames'] += 1
            if len(pred) > 1: counts['detected_overlap_frames'] += 1
            if mapped == real: counts['exact_overlap_frames'] += 1
    assigned = counts['correct_single_frames'] + counts['wrong_single_frames']
    return {'reference_kind': 'synthetic_clip_placement_not_human_speech_activity',
        'collar_seconds': collar, 'frame_step_seconds': step, 'optimal_fixture_label_mapping': best,
        'seconds': {k.removesuffix('_frames'): round(v * step, 3) for k, v in counts.items()},
        'matched_fraction_when_single_speaker_detected': counts['correct_single_frames'] / assigned if assigned else None,
        'note': 'Synthetic clip references contain pauses. Conditional label agreement excludes missed/overlap frames; not DER or real-interview quality.'}
