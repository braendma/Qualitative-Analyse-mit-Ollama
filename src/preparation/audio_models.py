"""One central local model library. Installation is explicit and transactional."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
from model_selection import validate_model
from download_models import MODELS as WHISPER_MODELS
MODELS={**WHISPER_MODELS, "sortformer-v2-onnx":"altunenes/parakeet-rs"}
from workspace_store import atomic_write


def library_model(model,path,verify_hashes=False):
    if model!='sortformer-v2-onnx':
        path=validate_model(path,verify_hashes=verify_hashes)
        manifest=json.loads((path/'model_manifest.json').read_text(encoding='utf-8'))
        if manifest.get('repository')!=MODELS[model]:raise ValueError('Modellherkunft stimmt nicht mit der Auswahl überein.')
        return path,[*manifest['files'],'model_manifest.json']
    from download_diarization_model import digest
    from sortformer_streaming import FILENAME,SHA256
    path=Path(path).expanduser().resolve();manifest_path=path/'diarization_model_manifest.json'
    try:
        m=json.loads(manifest_path.read_text(encoding='utf-8'))
        valid=m.get('filename')==FILENAME and m.get('sha256')==SHA256 and m.get('backend')=='sortformer_v2_onnx' and m.get('repository')==MODELS[model] and (path/FILENAME).is_file()
        if not valid:raise ValueError('Sortformer-v2-Modell oder Manifest fehlt/passt nicht.')
        if verify_hashes and digest(path/FILENAME)!=SHA256:raise ValueError('Sortformer-v2-Prüfsumme stimmt nicht.')
    except (OSError,ValueError) as exc:
        raise ValueError('Sortformer v2 nicht vollständig verfügbar: '+str(exc)) from exc
    return path,[FILENAME,'diarization_model_manifest.json']

class AudioModels:
    def __init__(self,root):
        self.root=Path(root);self.lock=threading.RLock();self.busy=False
        self.cancel=threading.Event();self.job={'status':'idle'}
        self.folder=None

    def state(self):
        with self.lock:
            installed=[]
            for name in MODELS:
                try:
                    path,_=library_model(name,self.root/name)
                    installed.append({'name':name,'path':str(path)})
                except ValueError:pass
            return {'root':str(self.root),'installed':installed,'job':dict(self.job),'busy':self.busy,
                    'choices':[{'id':name,'repository':repo} for name,repo in MODELS.items()]}

    def start(self,model,confirmed=False,source=None,on_complete=None):
        if confirmed is not True:raise ValueError('Zentrale Modellinstallation ausdrücklich starten.')
        if model not in MODELS:raise ValueError('Ein angebotenes Audio-Modell auswählen.')
        with self.lock:
            if self.busy:raise ValueError('Eine Modellinstallation läuft bereits. Abschluss abwarten oder abbrechen.')
            self.root.mkdir(parents=True,exist_ok=True)
            from runtime_support import exclusive_file_lock
            guard=exclusive_file_lock(self.root/'.installation.lock')
            guard.__enter__()
            self.busy=True;self.cancel.clear()
            self.job={'id':secrets.token_hex(10),'model':model,'status':'checking','source':'local' if source else 'download'}
            self.folder=self.root/('.installation-'+self.job['id'])
            thread=threading.Thread(target=self._work,args=(model,source,guard,on_complete),daemon=True)
            try:thread.start()
            except BaseException:
                self.busy=False;guard.__exit__(None,None,None);raise
            return dict(self.job)

    def stop(self):
        with self.lock:
            if self.busy:self.cancel.set()
            return {'stop_requested':self.busy}

    def _check_cancel(self):
        if self.cancel.is_set():raise InterruptedError('Modellinstallation abgebrochen; vorhandene Modelle bleiben erhalten.')

    def _work(self,model,source,guard,on_complete):
        child=None
        try:
            final=self.root/model
            if final.exists():
                library_model(model,final,verify_hashes=True)
            else:
                self.folder.mkdir();staging=self.folder/model
                if source:
                    origin,files=library_model(model,source,verify_hashes=True)
                    self._check_cancel();staging.mkdir()
                    self.job={**self.job,'status':'copying'}
                    for name in files:
                        with (origin/name).open('rb') as src,(staging/name).open('xb') as dst:
                            while block:=src.read(1024*1024):
                                self._check_cancel();dst.write(block)
                else:
                    self.job={**self.job,'status':'downloading'}
                    from process_commands import python_command
                    command=python_command(Path(__file__).with_name('download_models.py'),['--directory',str(self.folder),'--model',model])
                    if model=='sortformer-v2-onnx':command=python_command(Path(__file__).with_name('download_diarization_model.py'),['--directory',str(staging),'--model','v2'])
                    # The public downloader never needs account keys or research data.
                    from llm_providers import KEY_ENVS
                    env={k:v for k,v in os.environ.items() if k not in KEY_ENVS and k not in ('HF_TOKEN','HUGGING_FACE_HUB_TOKEN','OLLAMA_API_KEY') and not k.startswith('WORKFLOW_')}
                    env['HF_HUB_OFFLINE']='0'
                    with (self.folder/'download.log').open('wb') as log:
                        child=subprocess.Popen(command,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        while child.poll() is None:
                            self._check_cancel();time.sleep(.2)
                        if child.returncode:raise ValueError('Download fehlgeschlagen. Verbindung und freien Speicher prüfen; die vorhandenen Modelle bleiben erhalten. Details im lokalen Downloadprotokoll.')
                self.job={**self.job,'status':'verifying'}
                library_model(model,staging,verify_hashes=True);self._check_cancel()
                if final.exists():raise ValueError('Zielordner wurde inzwischen angelegt. Keine vorhandene Installation überschrieben.')
                staging.rename(final)
            self._check_cancel()
            if on_complete:on_complete(final)
            self.job={**self.job,'status':'completed','path':str(final)}
        except Exception as exc:
            self.job={**self.job,'status':'cancelled' if isinstance(exc,InterruptedError) else 'failed','error':str(exc)[:600]}
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=10)
            with self.lock:
                self.busy=False
                try:atomic_write(self.root/'last_installation.json',self.job)
                finally:guard.__exit__(None,None,None)
