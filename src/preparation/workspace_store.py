"""Versioned atomic persistence, independent of HTTP/UI for later integration."""
import copy
import json
import os
from pathlib import Path
import threading
import uuid
import llm_review as r


def atomic_write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def empty_project():
    return {'schema':1,'kind':'coded_documents','id':str(uuid.uuid4()),'documents':[],'categories':[],'annotations':[],'history':[]}


def validate_project(p):
    r.require(isinstance(p,dict) and p.get('schema')==1 and p.get('kind')=='coded_documents','Ungültiges Codierprojekt.')
    for field in ('documents','categories','annotations','history'):
        r.require(isinstance(p.get(field),list),f'{field} fehlt.')
    docs={};cats={};codes=set();ids=set();seen=set()
    for d in p['documents']:
        r.require(isinstance(d,dict) and isinstance(d.get('segments'),list) and d.get('transcript_confirmed') is True,'Dokument nicht bestätigt.')
        r.nonempty(d.get('id'),'Dokument-ID');r.nonempty(d.get('title'),'Dokumenttitel');r.nonempty(d.get('transcript_sha256'),'Transkriptbindung')
        r.require(d['id'] not in docs,'Doppelte Dokument-ID.')
        items=r.segments(d);docs[d['id']]={s['id']:s for s in items}
        for s in d['segments']:
            r.require(isinstance(s.get('person'),str) and type(s.get('exclude')) is bool,'Person/Exportauswahl ungültig.')
    for c in p['categories']:
        for key in ('id','code','definition'):r.nonempty(c.get(key),key)
        parts=[s.strip() for s in c['code'].split('>')]
        r.require(1<=len(parts)<=4 and all(parts) and c['code']==' > '.join(parts),'Ungültiger Codepfad.')
        r.require(c['id'] not in cats and c['code'].casefold() not in codes,'Doppelte Kategorie.')
        for key in ('inclusion','exclusion','anchors'):r.require(isinstance(c.get(key),str),f'{key} fehlt.')
        cats[c['id']]=c;codes.add(c['code'].casefold())
    for a in p['annotations']:
        r.nonempty(a.get('id'),'Codierungs-ID')
        s=docs.get(a.get('document_id'),{}).get(a.get('segment_id'))
        r.require(s and a.get('category_id') in cats and a['id'] not in ids,'Codierung verweist auf unbekannte/doppelte ID.')
        start,end=a.get('start'),a.get('end')
        r.require(type(start) is int and type(end) is int and 0<=start<end<=len(s['text']) and s['text'][start:end]==a.get('quote'),'Codiertext oder Zeichenpositionen passen nicht.')
        r.require(a.get('origin') in ('manual','llm_reviewed') and isinstance(a.get('memo'),str),'Herkunft/Memo ungültig.')
        signature=(a['document_id'],a['segment_id'],start,end,a['category_id'])
        r.require(signature not in seen,'Doppelte Codierung.');seen.add(signature);ids.add(a['id'])
    return p


class ProjectStore:
    def __init__(self,path,validator=validate_project,initial=None):
        self.path=Path(path);self.backup=self.path.with_suffix('.backup.json');self.lock=threading.RLock()
        self.validator=validator
        self.recovery=''
        self.state={'revision':0,'mutation_id':None,'project':copy.deepcopy(initial) if initial is not None else empty_project()}
        if self.path.exists():
            try:self.state=self.load(self.path)
            except (ValueError,OSError,KeyError,TypeError):
                r.require(self.backup.exists(),'Projekt beschädigt und keine Sicherung vorhanden. Original erhalten; nicht überschreiben.')
                self.state=self.load(self.backup);self.recovery='Letzte gültige Sicherung geladen; letzte Änderung ggf. erneut prüfen.'
    def load(self,path):
        value=r.read(path);r.require(value.get('sha256')==r.fingerprint(value['project']),'Projekt-Prüfsumme stimmt nicht.')
        self.validator(value['project']);return value
    def get(self):
        with self.lock:return {**copy.deepcopy(self.state),'recovery':self.recovery}
    def save(self,project,revision,mutation_id):
        with self.lock:
            r.nonempty(mutation_id,'Änderungs-ID',120);self.validator(project)
            if mutation_id==self.state['mutation_id']:
                r.require(r.fingerprint(project)==r.fingerprint(self.state['project']),'Änderungs-ID wurde wiederverwendet.')
                return self.get()
            r.require(type(revision) is int and revision==self.state['revision'],'Speicherkonflikt: neuerer Projektstand vorhanden. Lokale Eingaben bleiben erhalten.')
            next_state={'revision':revision+1,'mutation_id':mutation_id,'project':copy.deepcopy(project),'sha256':r.fingerprint(project),'saved_at':r.now()}
            self.path.parent.mkdir(parents=True,exist_ok=True)
            if self.state['revision']:
                atomic_write(self.backup,self.state)
            atomic_write(self.path,next_state)
            self.state=next_state;self.recovery='';return self.get()
