"""Explicit local setup checks. No model download or automatic inference."""
import importlib.metadata
import platform
import shutil
import tempfile
from pathlib import Path


def check_setup(app, model=''):
    checks=[]
    def add(name,ok,detail):checks.append({'name':name,'ok':ok,'detail':detail})
    add('Python',True,platform.python_version())
    for package in ('pandas','numpy','matplotlib','PyYAML','ollama','openpyxl'):
        try:add(package,True,importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:add(package,False,'Einrichtung.cmd erneut ausführen.')
    try:
        with tempfile.TemporaryFile(dir=app.directory) as f:f.write(b'local write check');f.flush()
        add('Lokale Ablage',True,'Projektordner ist beschreibbar.')
    except OSError:add('Lokale Ablage',False,'Schreibrechte prüfen oder einen anderen Datenordner mit --data-dir wählen.')
    free=shutil.disk_usage(app.directory).free
    add('Freier Speicher',free>256*1024*1024,f'{free/(1024**3):.1f} GiB frei. Modelle benötigen zusätzlichen Speicher in der Ollama-Ablage.')
    try:
        models=app.models()['models'];add('Ollama',True,f'{len(models)} lokale Modelle vorhanden.')
        if model:add('Gewähltes Modell',model in models,'Installiert.' if model in models else 'Ein vorhandenes Modell auswählen oder dieses Modell zuerst in Ollama installieren.')
    except ValueError as exc:
        models=[];add('Ollama',False,str(exc))
    return {'checks':checks,'models':models,'model_calls':0,
            'note':'Diese Prüfung startet kein Modell. Ob Modell und Kontext in RAM/VRAM passen, kann sie nicht zuverlässig bestimmen. Der optionale Modelltest prüft nur eine kurze Antwort.'}


def test_local_model(app, model):
    if model not in app.models()['models']:raise ValueError('Ein installiertes lokales Modell auswählen.')
    from coding_validation_common import default_llm
    answer=default_llm([{'role':'user','content':'Antworte ausschließlich mit OK.'}],
                      {'model':model,'host':'http://localhost:11434','num_ctx':2048,'max_tokens':32,
                       'temperature':0,'think':False,'timeout_seconds':45,'max_attempts':1,'log_thinking':False})
    if not answer.strip():raise ValueError('Keine sichtbare Modellantwort. Modell und Thinking-Einstellung prüfen.')
    return {'ok':True,'message':'Lokales Modell hat auf die kurze Testanfrage geantwortet. Das ist noch kein Test des vollständigen Analysekontexts.'}
