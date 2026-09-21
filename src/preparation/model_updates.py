"""Opt-in public metadata checks. Never sends projects, downloads weights or switches models."""
import datetime
import json
import os
from pathlib import Path
import re
import ssl
import threading
import time
import urllib.request
from workspace_store import atomic_write

DEFAULT_MODEL = 'large-v3'
DEFAULT_MODEL_ROOT = Path.home() / 'Documents' / 'Qualitative Analyse' / 'Modelle'
KNOWN = {'small': 'Systran/faster-whisper-small', 'large-v3': 'Systran/faster-whisper-large-v3'}
CATALOG_URL = 'https://huggingface.co/api/models?author=Systran&search=faster-whisper&limit=100&full=true'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Umleitung der Modellprüfung blockiert.')


def fetch_catalog():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request=urllib.request.Request(CATALOG_URL,headers={'Accept':'application/json','User-Agent':'QA-Transkription-Modellpruefung/1'})
    with opener.open(request,timeout=15) as response:
        data=response.read(1024*1024+1)
    if len(data)>1024*1024:raise ValueError('Modellkatalog zu groß.')
    value=json.loads(data)
    if not isinstance(value,list):raise ValueError('Ungültiger Modellkatalog.')
    return value


class ModelUpdates:
    def __init__(self, root, path, fetch=fetch_catalog, clock=time.time):
        self.root=Path(root);self.path=Path(path);self.fetch=fetch;self.clock=clock;self.lock=threading.Lock()
        self.data={'automatic':False,'last_attempt':0,'checked_at':None,'models':[],'error':None}
        if self.path.exists():
            saved=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(saved,dict):self.data.update(saved)

    def state(self):
        return {**self.data,'default_model':DEFAULT_MODEL,'scope':'SYSTRAN faster-whisper; andere Anbieter sind nicht erfasst.',
                'installed':self.installed()}

    def installed(self):
        values=[]
        for name,repo in KNOWN.items():
            path=self.root/name/'model_manifest.json'
            if not path.exists():continue
            try:
                manifest=json.loads(path.read_text(encoding='utf-8'))
                if manifest.get('repository')!=repo:continue
                values.append({'name':name,'repository':repo,'revision':manifest['revision']})
            except (ValueError,KeyError,OSError):continue
        return values

    def preference(self, automatic):
        if type(automatic) is not bool:raise ValueError('Automatik muss Ja/Nein sein.')
        with self.lock:
            self.data['automatic']=automatic;atomic_write(self.path,self.data)
        return self.state()

    def check(self, manual=False):
        with self.lock:
            now=self.clock()
            if not manual and not self.data['automatic']:return self.state()
            # Daily automatic check, brief manual rate limit; network errors retain old results.
            interval=60 if manual else 86400
            if self.data['last_attempt'] and now-self.data['last_attempt']<interval:return self.state()
            self.data['last_attempt']=now
            try:
                rows=self.fetch()
                if not isinstance(rows,list):raise ValueError('Katalogformat ungültig.')
                installed={x['repository'].lower():x for x in self.installed()}
                models=[]
                for item in rows[:100]:
                    if not isinstance(item,dict):continue
                    repo=item.get('id','');sha=item.get('sha','')
                    if not isinstance(repo,str) or not re.fullmatch(r'Systran/faster-whisper-[A-Za-z0-9._-]+',repo,re.I):continue
                    if not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{40,64}',sha):continue
                    if item.get('private') or item.get('disabled') or item.get('gated'):continue
                    local=installed.get(repo.lower())
                    status='current' if local and local['revision']==sha else 'revision_available' if local else 'alternative'
                    models.append({'repository':repo,'revision':sha,'installed_revision':local['revision'] if local else None,
                                   'status':status,'tested_family':repo.lower() in {r.lower() for r in KNOWN.values()},
                                   'url':'https://huggingface.co/'+repo})
                if not models:raise ValueError('Keine prüfbaren Modelle im Katalog.')
                self.data.update(models=models,error=None,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            except Exception:
                self.data['error']='Onlineprüfung nicht möglich. Verbindung später prüfen; vorhandene Modelle bleiben unverändert.'
            atomic_write(self.path,self.data)
            return self.state()
