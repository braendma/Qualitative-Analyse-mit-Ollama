"""Human speaker correction and explicit person mapping, separate from inference."""
import copy
import uuid
import llm_review as review
from workspace_store import empty_project, validate_project


def source_words(packet):
    words = []
    for segment in packet.get('segments', []):
        if not segment.get('words'):
            raise ValueError('Speaker review requires ASR word timestamps.')
        for word in segment['words']:
            words.append({**word, 'asr_segment_id': str(segment['id'])})
    review.require(words, 'No word-timed transcript in this speaker result.')
    return words


def original_text(words, first, last):
    return ''.join(w['word'] for w in words[first:last]).strip()


def make_draft(packet):
    words = source_words(packet)
    groups = []
    for i, word in enumerate(words):
        key = (word.get('speaker'), word.get('reason'), word['asr_segment_id'])
        if i and key == previous:
            groups[-1]['last'] = i + 1
            groups[-1]['text'] = original_text(words, groups[-1]['first'], i + 1)
        else:
            groups.append({'id': str(uuid.uuid4()), 'first': i, 'last': i + 1,
                'text': word['word'].strip(), 'speaker': word.get('speaker'), 'person': '', 'exclude': False})
        previous = key
    return {'schema': 1, 'kind': 'speaker_review', 'packet_sha256': review.fingerprint(packet), 'groups': groups}


def validate_draft(packet, draft):
    words = source_words(packet)
    review.require(draft.get('kind') == 'speaker_review' and draft.get('packet_sha256') == review.fingerprint(packet), 'Sprecherentwurf gehört zu anderer Quelle.')
    review.require(isinstance(draft.get('groups'), list) and draft['groups'], 'Abschnitte fehlen.')
    seen = set()
    next_word = 0
    for group in draft['groups']:
        review.nonempty(group.get('id'), 'Abschnitt-ID', 120)
        review.require(group['id'] not in seen, 'Doppelte Abschnitt-ID.')
        seen.add(group['id'])
        review.require(type(group.get('first')) is int and type(group.get('last')) is int and group['first'] == next_word and next_word < group['last'] <= len(words), 'Wörter fehlen, sind doppelt oder umgeordnet.')
        next_word = group['last']
        review.nonempty(group.get('text'), 'Abschnitttext', 200000)
        review.require(group.get('speaker') is None or isinstance(group['speaker'], str) and 0 < len(group['speaker'].strip()) <= 120, 'Sprecherlabel ungültig.')
        review.require(isinstance(group.get('person'), str) and len(group['person']) <= 120 and type(group.get('exclude')) is bool, 'Person/Exportauswahl ungültig.')
    review.require(next_word == len(words), 'Nicht alle Wörter erhalten.')
    return draft


def finish(packet, draft, reviewer, confirmed):
    validate_draft(packet, draft)
    review.require(confirmed is True, 'Audio, Text und Personenzuordnung ausdrücklich bestätigen.')
    words = source_words(packet)
    segments = []
    people = []
    for i, group in enumerate(draft['groups'], 1):
        if not group['exclude']:
            review.require(group['speaker'] and group['person'].strip(), 'Unbekannte Sprecher/fehlende Personen zuerst prüfen oder Abschnitt ausdrücklich ausschließen.')
        selected = words[group['first']:group['last']]
        segments.append({'id': str(i), 'start': min(w['start'] for w in selected),
            'end': max(w['end'] for w in selected), 'text': group['text'], 'speaker': group['speaker']})
        people.append({'segment_id': str(i), 'person': group['person'].strip(), 'exclude': group['exclude']})
    transcript = review.approve_transcript({'segments': segments, 'speaker_source_sha256': review.fingerprint(packet)}, reviewer)
    transcript['person_assignments'] = people
    transcript['person_mapping_confirmed'] = True
    transcript['review']['person_assignments_sha256'] = review.fingerprint(people)
    transcript['speaker_review_source_sha256'] = review.fingerprint(packet)
    transcript['source_word_ranges'] = [{'segment_id':str(i+1),'first':g['first'],'last':g['last']} for i,g in enumerate(draft['groups'])]
    transcript['review']['source_word_ranges_sha256'] = review.fingerprint(transcript['source_word_ranges'])
    project = empty_project()
    project['documents'].append({'id': str(uuid.uuid4()), 'title': 'Geprüftes Sprechertranskript',
        'transcript_sha256': review.fingerprint(transcript), 'transcript_confirmed': True,
        'segments': [{**s, 'person': p['person'], 'exclude': p['exclude']} for s, p in zip(segments, people)]})
    project['history'].append({'at': review.now(), 'action': 'Text und Sprecher/Personen ausdrücklich geprüft', 'reviewer': reviewer})
    validate_project(project)
    return {'transcript': transcript, 'project': project}
