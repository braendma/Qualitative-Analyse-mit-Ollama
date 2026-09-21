"""Conservative word-to-speaker overlap assignment; never invent identities."""
from collections import defaultdict


def assign(start, end, turns, minimum_fraction=.6):
    if end <= start:
        return None
    overlaps = defaultdict(float)
    for turn in turns:
        overlap = max(0., min(end, turn['end']) - max(start, turn['start']))
        if overlap:
            overlaps[turn['speaker']] += overlap
    ranked = sorted(overlaps.items(), key=lambda x: x[1], reverse=True)
    if not ranked or ranked[0][1] / (end-start) < minimum_fraction:
        return None
    if len(ranked) > 1 and ranked[1][1] > 0:
        # Overlap or a boundary inside one word remains uncertain.
        return None
    return ranked[0][0]


def merge(transcript, turns):
    result = []
    for segment in transcript['segments']:
        for word in segment['words']:
            result.append({**word, 'speaker': assign(word['start'], word['end'], turns)})
    return {'words': result, 'person_mapping_confirmed': False,
            'note': 'Speaker labels are suggestions. Overlapping/boundary words stay unassigned.'}
