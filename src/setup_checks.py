"""Explicit local setup checks. No model download or automatic inference."""
import importlib.metadata
import shutil
import sys
import tempfile
from pathlib import Path


def dependency_repair_hint():
    """Describe repair for the running distribution, never run an installer."""
    if getattr(sys, 'frozen', False):
        return ('Das vollständige Programmpaket erneut herunterladen und in einen neuen Ordner '
                'entpacken. QualitativeAnalyse.exe aus diesem Ordner starten. '
                'Eine eigene Python-Installation ist für das Paket nicht erforderlich.')
    if sys.platform == 'darwin':
        return 'start/macos/Einrichtung.command im vollständigen Programmordner erneut ausführen.'
    if sys.platform == 'win32':
        return 'Einrichtung.cmd im vollständigen Programmordner erneut ausführen.'
    return 'Die verwendete Python-Umgebung aktivieren und die Abhängigkeiten aus requirements.txt installieren.'


def check_setup(app, model='', selected=None, pid=None):
    checks=[]
    def add(name,ok,detail):checks.append({'name':name,'ok':ok,'detail':detail})
    bundled = bool(getattr(sys, 'frozen', False))
    add('Python (im Programmpaket)' if bundled else 'Python',True,'.'.join(map(str, sys.version_info[:3])))
    for package in ('pandas','numpy','matplotlib','PyYAML','ollama','openpyxl'):
        try:add(package,True,importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:add(package,False,dependency_repair_hint())
    try:
        with tempfile.TemporaryFile(dir=app.directory) as f:f.write(b'local write check');f.flush()
        add('Lokale Ablage',True,'Projektordner ist beschreibbar.')
    except OSError:add('Lokale Ablage',False,'Schreibrechte prüfen oder einen anderen Datenordner mit --data-dir wählen.')
    free=shutil.disk_usage(app.directory).free
    add('Freier Speicher',free>256*1024*1024,f'{free/(1024**3):.1f} GiB frei. Modelle benötigen zusätzlichen Speicher in der Ollama-Ablage.')
    if selected and selected.get('provider','ollama_local') != 'ollama_local':
        models=[]
        try:
            from llm_providers import PROVIDERS
            chosen=app.authorize_llm(pid, selected, installed=False)
            add('KI-Anbieter', True, PROVIDERS[chosen['provider']]['name'] + ': Freigabe und Schlüssel vorhanden. Erreichbarkeit und Modellzugriff erst beim optionalen Test geprüft.')
        except ValueError as exc: add('KI-Anbieter',False,str(exc))
    else:
        try:
            models=app.models()['models'];add('Ollama',True,f'{len(models)} lokale Modelle vorhanden.')
            if model:add('Gewähltes Modell',model in models,'Installiert.' if model in models else 'Ein vorhandenes Modell auswählen oder dieses Modell zuerst in Ollama installieren.')
        except ValueError as exc:
            models=[];add('Ollama',False,str(exc) + ' Ohne lokalen Ollama-Server bleiben die Oberfläche, freigegebene Cloud-Anbieter und reine Diagnosen ohne Modellbedarf nutzbar.')
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
