"""Continuous transcript editing; original ASR timings stay immutable."""
import difflib
from collections import Counter
import math
import re
import secrets
from pathlib import Path
import llm_review as r
from workspace_store import ProjectStore, atomic_write, empty_project, validate_project


def tokens(text):
    return list(re.finditer(r'\S+', text))


def utf16(text):
    return len(text.encode('utf-16-le')) // 2


def align(document, text):
    """Only unchanged ASR tokens receive word timings; edits get a seek anchor."""
    original = []
    for segment in document['segments']:
        word_items = segment.get('words') or []
        expanded = [(m.group(), w if len(tokens(w['word'])) == 1 else {}) for w in word_items for m in tokens(w['word'])]
        raw = tokens(segment['text'])
        exact = [m.group() for m in raw] == [w[0] for w in expanded]
        for i, item in enumerate(raw):
            w = expanded[i][1] if exact else {}
            start, end = w.get('start'), w.get('end')
            timed = all(type(v) in (int, float) and math.isfinite(v) for v in (start, end)) and 0 <= start <= end
            original.append({'text': item.group(), 'source_token_index':len(original), 'segment_id': str(segment['id']),
                             'speaker':w.get('speaker'),'speaker_label':w.get('speaker_label',''),
                             'person':w.get('person',''),'person_confirmed':w.get('person_confirmed',False),'exclude':w.get('exclude',False),
                             'start': start if timed else segment['start'],
                             'end': end if timed else segment['end'], 'exact': timed})
    edited = tokens(text)
    r.require(original and len(edited) <= 20000, 'Transkript enthält keine Ausgangswörter oder zu viele Wörter.')
    before_count, after_count = Counter(w['text'] for w in original), Counter(m.group() for m in edited)
    mapping = {}
    for kind, a, b, c, d in difflib.SequenceMatcher(None, [w['text'] for w in original], [m.group() for m in edited], autojunk=len(original)>4000).get_opcodes():
        for i in range(c, d):
            if kind == 'equal':
                mapping[i] = {**original[a+i-c]}
                if before_count[mapping[i]['text']] != after_count[mapping[i]['text']]:
                    mapping[i]['exact'] = False
            else:
                anchor = original[min(a, len(original)-1)]
                mapping[i] = {**anchor, 'exact': False,'person_confirmed':False,'nearby_before':max(0,a-1),'nearby_after':min(a,len(original)-1)}
    result = []
    offset16 = 0
    previous = 0
    for i, match in enumerate(edited):
        offset16 += utf16(text[previous:match.start()])
        end16 = offset16 + utf16(match.group())
        entry = mapping[i]
        result.append({**entry, 'anchor': entry['start'],'anchor_end':entry['end'], 'start': entry['start'] if entry['exact'] else None,
                       'end': entry['end'] if entry['exact'] else None, 'text': match.group(), 'from': offset16, 'to': end16,
                       'char_start': match.start(), 'char_end': match.end()})
        previous = match.end()
        offset16 = end16
    return result


class ContinuousReview:
    def __init__(self, session):
        self.session = session
        self.store = None
        self.source = None
        self.binding = None
        self.person_binding = None
        self.receipt = session.output.parent / (session.output.name + '_Abschluss.json')

    def ensure(self):
        run = r.read(self.session.output / 'run.json')
        r.require(run.get('status') == 'completed', 'Transkription ist noch nicht abgeschlossen.')
        r.require(run.get('identity', {}).get('audio_sha256') == self.session.audio_hash, 'Aufnahme und ASR-Ergebnis passen nicht zusammen.')
        r.require(run.get('outputs', {}).get('transcript.json') == self.session.file_hash(self.session.output / 'transcript.json'), 'ASR-Ergebnis-Prüfsumme stimmt nicht. Original und Entwurf erhalten.')
        if self.store is not None:
            r.require(r.fingerprint(r.read(self.session.output / 'transcript.json')) == self.binding, 'ASR-Original wurde verändert. Textprüfung unterbrochen; Original und Entwurf erhalten.')
            r.require(r.fingerprint(self.session.data['edits']) == self.legacy_binding, 'Segmentkorrekturen wurden parallel verändert. Entwurf sichern und Zuordnung prüfen.')
            from reading_speakers import source
            _, current_binding, _ = source(self.session,r.read(self.session.output/'transcript.json'))
            r.require(current_binding==self.person_binding,'Sprecherzuordnung wurde geändert. Entwurf sichern und neu laden.')
            return
        s = self.session
        r.require(r.read(s.output / 'run.json')['status'] == 'completed', 'Transkription ist noch nicht abgeschlossen.')
        raw = r.read(s.output / 'transcript.json')
        self.binding = r.fingerprint(raw)
        from reading_speakers import source
        self.source,self.person_binding,self.speaker_info=source(s,raw)
        r.segments(self.source)
        self.original_words=align(self.source,' '.join(segment['text'] for segment in self.source['segments']))
        self.legacy_binding = r.fingerprint(s.data['edits'])
        # Preserve existing segment-editor corrections on first opening.
        state = s.state()
        r.require(not any(x['conflict'] for x in state['segments']), 'Vorhandene Segmentkorrekturen zuerst gegen das Original prüfen.')
        initial_text=s.reading_carry if isinstance(getattr(s,'reading_carry',None),str) else ' '.join(x['display_text'] for x in state['segments'])
        if initial_text:
            aligned=align(self.source,initial_text);breaks=[];last=None;unknown_start=None
            for word in aligned:
                key=(('person',word['person'],word['exclude']) if word['person'] else ('speaker',word['speaker'],word['exclude']) if word['speaker'] else None)
                if key is None:
                    if unknown_start is None:unknown_start=word['char_start']
                    continue
                if last is not None and key!=last:breaks.append(unknown_start if unknown_start is not None else word['char_start'])
                last=key;unknown_start=None
            for offset in reversed(breaks):initial_text=initial_text[:offset].rstrip()+'\n\n'+initial_text[offset:]
        from reading_people import initial_people,validate as validate_people
        initial = {'people':initial_people(self.original_words),'speaker_overrides':[],'text': initial_text, 'source_sha256': self.binding, 'legacy_sha256': self.legacy_binding,'person_source_sha256':self.person_binding}
        def validate(value):
            r.require(value.get('source_sha256') == self.binding, 'Text gehört zu einem anderen ASR-Ergebnis.')
            r.require(value.get('legacy_sha256') == self.legacy_binding, 'Frühere Segmentkorrekturen wurden verändert. Entwurf sichern und Zuordnung prüfen.')
            r.require(value.get('person_source_sha256')==self.person_binding,'Sprecherquelle hat sich geändert; alten Entwurf sichern.')
            r.require(isinstance(value.get('text'),str) and len(value['text'])<=2000000, 'Transkript muss Text mit höchstens 2 Millionen Zeichen sein.')
            validate_people(value,self.original_words)
        suffix=('_'+self.person_binding[:12]) if self.person_binding else ''
        self.store = ProjectStore(s.output.parent / (s.output.name + '_Lesetext'+suffix+'.json'), validator=validate, initial=initial)

    def state(self):
        s = self.session
        base = s.state()
        progress = r.read(s.output / 'progress.json') if (s.output / 'progress.json').exists() else {}
        result = {k: base[k] for k in ('status', 'title', 'error', 'workspace_key', 'audio_available','job_phase','speaker_warning')}
        result['progress'] = progress
        if base['status'] == 'completed' and not r.read(s.output / 'transcript.json').get('segments'):
            result.update(status='empty', error='Keine Sprache erkannt. Ergebnis bleibt erhalten; andere Aufnahme wählen.')
            return result
        if base['status'] == 'completed':
            self.ensure()
            saved = self.store.get()
            result.update(saved)
            result['words'] = self.words(saved['project'])
            result['source_words']=self.original_words
            from reading_people import initial_people
            result['people']=saved['project'].get('people',initial_people(self.original_words))
            result['speaker_info']=self.speaker_info
            result['person_source_sha256']=self.person_binding
            result['approved'] = self.is_approved()
            if result['approved']:
                result['approved_filename'] = r.read(self.receipt)['filename']
        return result

    def words(self,project):
        from reading_people import apply
        return apply(align(self.source,project['text']),project,self.original_words)

    def save(self, payload):
        self.ensure()
        self.store.save(payload['project'], payload['revision'], payload['mutation_id'])
        return self.state()

    def is_approved(self):
        if not self.receipt.exists():
            return False
        receipt = r.read(self.receipt)
        current = self.store.get()
        target=self.receipt.parent / receipt.get('filename','')
        coding_target=self.receipt.parent/receipt['coding_filename'] if receipt.get('coding_filename') else None
        coding_intact=coding_target is None or (coding_target.is_file() and receipt.get('coding_file_sha256')==self.session.file_hash(coding_target))
        return coding_intact and receipt.get('project_sha256') == r.fingerprint(current['project']) and receipt.get('revision') == current['revision'] and target.is_file() and receipt.get('file_sha256') == self.session.file_hash(target)

    def finish(self, payload):
        self.ensure()
        saved = self.store.get()
        r.require(payload.get('revision') == saved['revision'], 'Text wurde inzwischen geändert. Aktuellen Stand erneut prüfen.')
        r.require(payload.get('confirmed') is True, 'Prüfung gegen die Aufnahme ausdrücklich bestätigen.')
        text = saved['project']['text']
        r.nonempty(text,'Transkript vor Abschluss',2000000)
        words = self.words(saved['project'])
        originals = {str(s['id']): s for s in self.source['segments']}
        groups = []
        for word in words:
            key=(word['segment_id'],word['speaker'],word['person'],word['exclude'])
            if not groups or groups[-1]['key'] != key:
                groups.append({'id': word['segment_id'], 'a': word['char_start'], 'b': word['char_end'],'key':key,'word':word,'last_word':word,'person_confirmed':word['person_confirmed']})
            else:
                groups[-1]['b'] = word['char_end']
                groups[-1]['last_word'] = word
                groups[-1]['person_confirmed'] = groups[-1]['person_confirmed'] and word['person_confirmed']
        segments = []
        for number, group in enumerate(groups, 1):
            old = originals[group['id']]
            segments.append({'id': str(number), 'text': text[group['a']:group['b']],
                             'start': group['word']['anchor'], 'end': max(group['word']['anchor'],group['last_word']['end'] if group['last_word']['end'] is not None else group['last_word']['anchor_end']), 'speaker': group['word']['speaker']})
        result = r.approve_transcript({'segments': segments}, payload.get('reviewer'))
        result.update(continuous_text=text, asr_source_sha256=self.binding,
                      source_audio_sha256=self.session.audio_hash,
                      source_person_assignments=self.source.get('person_assignments', []),
                      source_person_mapping_confirmed=self.source.get('person_mapping_confirmed', False),
                      person_source_sha256=self.person_binding,
                      person_assignments=[{'segment_id':str(i+1),'person':g['word']['person'],'exclude':g['word']['exclude'],'source_confirmed':g['person_confirmed']} for i,g in enumerate(groups)],
                      source_segments=[{'segment_id':str(i+1),'source_segment_id':group['id'],'first_source_token':group['word']['source_token_index'],'last_source_token_exclusive':group['last_word']['source_token_index']+1,'start_approximate':not group['word']['exact'],'end_approximate':not group['last_word']['exact']} for i,group in enumerate(groups)],
                      reading_people=saved['project'].get('people',[]),reading_speaker_overrides=saved['project'].get('speaker_overrides',[]),
                      correction_history=self.session.data['history'],
                      timing_note='Originale ASR-Zeiten. Geänderter Text erhält keine neuen Wortzeitstempel.',
                      reading_revision=saved['revision'])
        result['review']['person_assignments_sha256']=r.fingerprint(result['person_assignments'])
        target = self.session.output.parent / (self.session.output.name + '_Geprueft_' + secrets.token_hex(4) + '.json')
        atomic_write(target, result)
        import uuid
        project=empty_project()
        project['documents'].append({'id':str(uuid.uuid4()),'title':self.session.audio.name if self.session.audio else 'Geprüfter Lesetext','transcript_sha256':r.fingerprint(result),'transcript_confirmed':True,'transcript_filename':target.name,'transcript_file_sha256':self.session.file_hash(target),'source_audio_sha256':self.session.audio_hash,'source_audio_name':self.session.audio.name if self.session.audio else None,'asr_source_sha256':self.binding,'reading_revision':saved['revision'],'reading_people':result['reading_people'],'reading_speaker_overrides':result['reading_speaker_overrides'],'person_source_sha256':self.person_binding,'segments':[{**segment,'person':person['person'] if person['source_confirmed'] else '', 'exclude':person['exclude'],'source_person_suggestion':person['person'],'source_person_confirmed':person['source_confirmed'],'source_segment_id':source['source_segment_id']} for segment,person,source in zip(segments,result['person_assignments'],result['source_segments'])]})
        project['history'].append({'at':r.now(),'action':'Geprüften Lesetext als neues Codierprojekt übernommen; unsichere Personen erneut prüfen','reviewer':payload.get('reviewer')})
        validate_project(project)
        coding_target=target.with_name(target.stem+'_Codierprojekt.json');atomic_write(coding_target,project)
        atomic_write(self.receipt, {'project_sha256': r.fingerprint(saved['project']), 'revision': saved['revision'],
                                    'filename': target.name, 'file_sha256':self.session.file_hash(target),'coding_filename':coding_target.name,'coding_file_sha256':self.session.file_hash(coding_target), 'at': r.now()})
        return {'filename': target.name, 'transcript': result,'project_filename':coding_target.name,'project':project}


def reading(session):
    with session.lock:
        if not hasattr(session, 'continuous'):
            session.continuous = ContinuousReview(session)
        return session.continuous
