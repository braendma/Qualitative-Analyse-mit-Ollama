"""Attach recording-local/explicitly reviewed speaker labels to immutable ASR words."""
import copy
from pathlib import Path
import llm_review as r
from speaker_review import source_words,make_draft,finish,validate_draft
from workspace_store import ProjectStore,atomic_write


def packet_path(session):
    explicit=getattr(session,'speaker_result',None)
    candidate=Path(explicit) if explicit else session.output.parent/(session.output.name+'_Sprecher')/'speaker_suggestions.json'
    if not candidate.is_file():return None
    run=r.read(candidate.with_name('run.json'))
    if run.get('status')!='completed':return None
    r.require(run.get('outputs',{}).get(candidate.name)==session.file_hash(candidate),'Sprecherergebnis verändert.')
    packet=r.read(candidate)
    r.require(packet.get('audio_sha256')==session.audio_hash and packet.get('transcript_sha256')==session.file_hash(session.output/'transcript.json'),'Sprecher-/ASR-Quelle passt nicht zusammen.')
    return candidate


def source(session, raw):
    document=copy.deepcopy(raw);path=packet_path(session)
    if path is None:return document,None,{'available':False,'count':None,'labels':[]}
    packet=r.read(path);allwords=source_words(packet)
    pointer=session.output.parent/(session.output.name+'_SprecherQuelle.json')
    confirmed=None
    if pointer.exists():
        receipt=r.read(pointer);approved=pointer.parent/receipt['filename']
        if isinstance(receipt.get('carry_text'),str) and not hasattr(session,'reading_carry'):session.reading_carry=receipt['carry_text']
        r.require(session.file_hash(approved)==receipt['sha256'],'Bestätigte Sprecherquelle verändert.')
        confirmed=r.read(approved);r.confirmed(confirmed)
        r.require(confirmed.get('speaker_review_source_sha256')==r.fingerprint(packet),'Sprecherfreigabe gehört zu anderer Quelle.')
        r.require(confirmed['review'].get('person_assignments_sha256')==r.fingerprint(confirmed['person_assignments']),'Personenzuordnung verändert.')
        r.require(confirmed['review'].get('source_word_ranges_sha256')==r.fingerprint(confirmed.get('source_word_ranges')),'Wortgrenzen der Sprecherfreigabe fehlen oder wurden verändert.')
    labels=list(dict.fromkeys(turn['speaker'] for turn in sorted(packet.get('turns',[]),key=lambda t:t['start']) if turn.get('speaker')))
    for w in allwords:
        if w.get('speaker') and w['speaker'] not in labels:labels.append(w['speaker'])
    by_word={}
    if confirmed:
        r.require(len(confirmed['source_word_ranges'])==len(confirmed['segments'])==len(confirmed['person_assignments']),'Sprechergruppenanzahl widersprüchlich.')
        cursor=0
        for group,segment,person in zip(confirmed['source_word_ranges'],confirmed['segments'],confirmed['person_assignments']):
            r.require(group['first']==cursor and cursor<group['last']<=len(allwords),'Sprecherwortabdeckung ungültig.')
            for i in range(cursor,group['last']):by_word[i]={'speaker':segment['speaker'],'person':person['person'],'person_confirmed':True,'exclude':person['exclude']}
            cursor=group['last']
        r.require(cursor==len(allwords),'Sprecherwortabdeckung unvollständig.')
    person_labels={}
    if confirmed:
        people=list(dict.fromkeys(p['person'] for p in confirmed['person_assignments'] if p['person']))
        person_labels=confirmed.get('reading_person_labels') or {person:'P'+str(i+1) for i,person in enumerate(people)}
        r.require(all(person in person_labels for person in people) and len(set(person_labels.values()))==len(person_labels),'Personennummern fehlen oder sind doppelt.')
        r.require(all(isinstance(label,str) and label.startswith('P') and label[1:].isdigit() for label in person_labels.values()),'Personennummer ungültig.')
    count=0
    for segment in document['segments']:
        for word in segment.get('words',[]):
            r.require(count<len(allwords) and word['word']==allwords[count]['word'],'ASR-Wortfolge passt nicht zum Sprecherpaket.')
            data=by_word.get(count,{'speaker':allwords[count].get('speaker'),'person':'','person_confirmed':False,'exclude':False})
            word.update(data)
            word['speaker_label']=person_labels[data['person']] if data['person_confirmed'] and data['person'] in person_labels else (('P'+str(labels.index(data['speaker'])+1)) if data['speaker'] in labels else '')
            count+=1
    r.require(count==len(allwords),'ASR-/Sprecherwortanzahl verschieden.')
    document['person_assignments']=confirmed.get('person_assignments',[]) if confirmed else []
    document['person_mapping_confirmed']=bool(confirmed)
    document['reading_person_labels']=person_labels
    binding=r.fingerprint({'packet':packet,'confirmed':confirmed})
    return document,binding,{'available':True,'count':len(labels),'labels':labels,'confirmed':bool(confirmed)}


class SpeakerPanel:
    def __init__(self,session):
        self.session=session;path=packet_path(session);r.require(path,'Noch keine abgeschlossene Sprechererkennung für diese Aufnahme.')
        self.packet=r.read(path)
        self.store=ProjectStore(session.output.parent/(session.output.name+'_Sprecherpruefung.json'),validator=lambda d:validate_draft(self.packet,d),initial=make_draft(self.packet))

    def approve(self,body):
        state=self.store.get();r.require(body.get('revision')==state['revision'],'Sprecherentwurf wurde geändert.')
        # Integrated panel edits labels/persons only. Reading text has its own saved revision.
        words=source_words(self.packet)
        for group in state['project']['groups']:
            r.require(group['text']==''.join(w['word'] for w in words[group['first']:group['last']]).strip(),'Text bitte in der zusammenhängenden Lesetextansicht korrigieren.')
        result=finish(self.packet,state['project'],body.get('reviewer'),body.get('confirmed'))
        import secrets
        target=self.session.output.parent/(self.session.output.name+'_SprecherGeprueft_'+secrets.token_hex(4)+'.json')
        # Keep corrected reading text; the changed person source creates a separate draft version.
        from continuous_review import reading
        previous=reading(self.session);previous.ensure()
        r.require(not previous.store.get()['project'].get('speaker_overrides'),'Direkte Sprecherzuordnungen liegen im Lesetext vor. Dort weiterbearbeiten; die separate Quellenprüfung darf diese Zuordnungen nicht ersetzen.')
        self.session.reading_carry=previous.store.get()['project']['text']
        person_labels=dict(previous.source.get('reading_person_labels',{}))
        for person in result['transcript']['person_assignments']:
            identity=person['person']
            if identity and identity not in person_labels:person_labels[identity]='P'+str(max([int(label[1:]) for label in person_labels.values()],default=0)+1)
        result['transcript']['reading_person_labels']=person_labels
        result['project']['documents'][0]['transcript_sha256']=r.fingerprint(result['transcript'])
        atomic_write(target,result['transcript'])
        atomic_write(self.session.output.parent/(self.session.output.name+'_SprecherQuelle.json'),{'filename':target.name,'sha256':self.session.file_hash(target),'carry_text':getattr(self.session,'reading_carry',None)})
        if hasattr(self.session,'continuous'):del self.session.continuous
        return result
