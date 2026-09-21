"""Explicit per-range person assignments over immutable ASR token indices."""
import copy
import llm_review as r


def identity(word):
    if word.get('person') and word.get('person_confirmed'):return 'person:'+word['person']
    if word.get('speaker'):return 'speaker:'+word['speaker']
    return None


def initial_people(words):
    people=[];seen=set();used=set()
    for word in words:
        key=identity(word)
        if not key or key in seen:continue
        label=word.get('speaker_label') or 'P'+str(len(people)+1)
        if label in used:label='P'+str(max([int(p['label'][1:]) for p in people],default=0)+1)
        people.append({'id':key,'label':label,'name':word.get('person') or label,'origin':'source_reviewed' if word.get('person_confirmed') else 'automatic'})
        seen.add(key);used.add(label)
    return people


def validate(project, original_words):
    people=project.get('people',initial_people(original_words));overrides=project.get('speaker_overrides',[])
    r.require(isinstance(people,list) and isinstance(overrides,list),'Personenliste/Zuordnungen ungültig.')
    ids=set();labels=set();names=set()
    for person in people:
        for field in ('id','label','name'):r.nonempty(person.get(field),field,200)
        r.require(person['id'] not in ids and person['label'] not in labels and person['name'].casefold() not in names,'Doppelte Personenkennung.')
        r.require(person['label'].startswith('P') and person['label'][1:].isdigit(),'Personenlabel muss P und eine Zahl enthalten.')
        ids.add(person['id']);labels.add(person['label']);names.add(person['name'].casefold())
    end=0;region_ids=set()
    for region in overrides:
        r.nonempty(region.get('id'),'Zuordnungs-ID',200)
        r.require(region['id'] not in region_ids,'Doppelte Bereichs-ID.')
        r.require(type(region.get('first')) is int and type(region.get('last')) is int and end<=region['first']<region['last']<=len(original_words),'Zuordnungen überlappen oder liegen außerhalb der Quelle.')
        r.require(region.get('person_id') in ids or region.get('person_id') is None,'Person nicht in der gespeicherten Liste.')
        r.require(type(region.get('exclude')) is bool,'Ausschluss muss ausdrücklich gesetzt sein.')
        values=region.get('reviewed_tokens')
        r.require(isinstance(values,list) and len(values)<=20000 and all(isinstance(t,str) and len(t)<=200000 for t in values),'Geprüfter Wortbereich fehlt.')
        indices=region.get('reviewed_indices')
        r.require(isinstance(indices,list) and len(indices)==len(values) and all(type(i) is int and region['first']<=i<region['last'] for i in indices),'Geprüfte Quellwortindices fehlen.')
        end=region['last'];region_ids.add(region['id'])


def apply(words, project, original_words):
    people=project.get('people',initial_people(original_words));by_id={p['id']:p for p in people};regions=project.get('speaker_overrides',[])
    stable={region['id']:[w['text'] for w in words if region['first']<=w['source_token_index']<region['last']]==region['reviewed_tokens'] and [w['source_token_index'] for w in words if region['first']<=w['source_token_index']<region['last']]==region['reviewed_indices'] for region in regions}
    output=[]
    for item in words:
        word=copy.copy(item);word['reading_person_id']=identity(word);word['manual_assignment']=False
        person=by_id.get(word['reading_person_id'])
        if person:
            word.update(speaker_label=person['label'],person_display=person['name'])
            if word.get('person_confirmed'):word['person']=person['name']
        for region in regions:
            if region['first']<=word['source_token_index']<region['last']:
                person=by_id.get(region['person_id'])
                word.update(source_speaker=word.get('speaker'),source_person=word.get('person'),reading_person_id=region['person_id'],reading_region_id=region['id'],manual_assignment=True,exclude=region['exclude'],speaker=region['person_id'],speaker_label=person['label'] if person else '',person=person['name'] if person else '',person_display=person['name'] if person else '',person_confirmed=bool(person and stable[region['id']]),assignment_needs_review=bool(person and not stable[region['id']]))
                break
        output.append(word)
    return output
