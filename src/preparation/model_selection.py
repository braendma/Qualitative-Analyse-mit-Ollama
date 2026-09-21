"""Explicit local Whisper selection; no downloads, model search or fallback."""
import hashlib
import json
from pathlib import Path
import re
from workspace_store import atomic_write

REQUIRED={'config.json','model.bin','tokenizer.json'}

def validate_model(folder, verify_hashes=False):
    path=Path(folder).expanduser()
    if not path.is_absolute():raise ValueError('Einen vollständigen lokalen Modellordner auswählen.')
    path=path.resolve()
    try:
        data=json.loads((path/'model_manifest.json').read_text(encoding='utf-8'))
        files=data.get('files') if isinstance(data,dict) else None
        if not isinstance(files,dict) or not REQUIRED<=files.keys():raise ValueError('Manifest enthält nicht alle benötigten Whisper-Dateien.')
        for name,entry in files.items():
            if not isinstance(name,str) or name in ('.','..') or '/' in name or '\\' in name or ':' in name:raise ValueError('Ungültiger Dateiname im Modellmanifest.')
            if not isinstance(entry,dict) or not isinstance(entry.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',entry['sha256']):raise ValueError('Prüfsumme im Modellmanifest fehlt oder ist ungültig.')
            item=path/name
            if not item.is_file() or not item.resolve().is_relative_to(path):raise ValueError('Eine benötigte Modelldatei fehlt oder liegt außerhalb des Modellordners.')
            size=entry.get('bytes')
            if type(size) is not int or size<=0 or item.stat().st_size!=size:raise ValueError('Eine Modelldatei ist unvollständig oder wurde verändert.')
            if verify_hashes:
                digest=hashlib.sha256()
                with item.open('rb') as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
                if digest.hexdigest()!=entry['sha256']:raise ValueError('Prüfsumme einer Modelldatei stimmt nicht. Den vollständigen ursprünglichen Modellordner wählen.')
        return path
    except (OSError,json.JSONDecodeError) as exc:
        raise ValueError('Whisper-Modell fehlt oder ist nicht lesbar. Einen installierten Modellordner mit model_manifest.json auswählen.') from exc


def saved_default(path, fallback):
    """Retain a missing saved path so setup explains it, never silently switch."""
    try:
        value=json.loads(path.read_text(encoding='utf-8')).get('model_dir')
        if isinstance(value,str) and Path(value).is_absolute():return Path(value)
    except (OSError,ValueError,AttributeError):pass
    return fallback


def selection_state(selected, defaults, known_paths):
    error=''
    try:validate_model(selected)
    except (ValueError,TypeError) as exc:error=str(exc)
    candidates=[];seen=set()
    for item in [selected,saved_default(defaults,selected),*known_paths]:
        try:
            path=validate_model(item)
            key=str(path).casefold()
            if key in seen:continue
            seen.add(key);candidates.append({'path':str(path),'name':path.name})
        except (ValueError,TypeError):continue
    return {'ready':not error,'path':str(selected),'error':error,'candidates':candidates,
            'default_path':str(saved_default(defaults,selected)),
            'note':'Modelle werden separat installiert. Die Auswahl wird geprüft; kein Download und kein automatischer Modellwechsel.'}


def remember_default(path, model):
    atomic_write(path,{'schema':1,'model_dir':str(model),'selection':'explicit_user_choice'})
