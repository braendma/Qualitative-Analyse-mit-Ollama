"""Persistent recording sequence; upload is committed only against the reviewed source."""
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from urllib.parse import unquote
import llm_review as r
from continuous_review import reading
from workspace_store import atomic_write
from model_updates import ModelUpdates, DEFAULT_MODEL_ROOT, DEFAULT_MODEL


def workspace(session):
    return r.fingerprint({'output':str(session.output),'audio':session.audio_hash})


def job_alive(job):
    """Read-only Windows PID/creation-time check, never signal a process."""
    import os
    if os.name!='nt':
        # A surviving PID is conservative on POSIX; cancellation only writes a
        # project-bound request file and never signals this recorded PID.
        try:os.kill(int(job['pid']),0);return True
        except (OSError,ValueError,KeyError):return False
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,int(job['pid']))
    if not handle:return False
    try:
        code=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value!=259:return False
        stamps=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(x) for x in stamps]):return False
        created=((stamps[0].dwHighDateTime<<32)+stamps[0].dwLowDateTime)/10000000-11644473600
        return abs(created-job['started_at'])<10
    finally:kernel.CloseHandle(handle)


class ReadingWorkflow:
    def __init__(self, session, factory):
        self.lock=threading.RLock();self.factory=factory;self.session=session;self.uploading=False
        self.path=session.output.parent/(session.output.name+'_Arbeitsfolge.json')
        self.model_dir=getattr(session,'model_dir',DEFAULT_MODEL_ROOT/DEFAULT_MODEL)
        self.speaker_model_dir=getattr(session,'speaker_model_dir',self.model_dir.parent/'sortformer-v2-onnx')
        self.entries=[self.entry(session)]
        if self.path.exists():
            saved=r.read(self.path)
            r.require(isinstance(saved.get('origin'),str) and Path(str(Path(saved['origin']).resolve()).removeprefix('\\\\?\\'))==Path(str(session.output).removeprefix('\\\\?\\')),'Arbeitsfolge gehört zu anderem Startordner.')
            self.entries=saved['entries'];last=self.entries[-1]
            target=Path(str(Path(last['output']).resolve()).removeprefix('\\\\?\\'))
            if str(session.output).startswith('\\\\?\\'):target=Path('\\\\?\\'+str(target))
            r.require(Path(str(target).removeprefix('\\\\?\\')).is_relative_to(Path(str(session.output.parent).removeprefix('\\\\?\\'))),'Arbeitsfolge verweist außerhalb ihres Arbeitsordners.')
            if target!=session.output:
                self.session=self.factory(Path(last['audio']),target)
                self.configure(self.session)
            r.require(self.session.audio_hash==last['audio_sha256'],'Aufnahme der Arbeitsfolge wurde geändert.')
        self.origin=str(session.output)

    def configure(self, session):
        session.model_dir=self.model_dir
        session.speaker_model_dir=self.speaker_model_dir
        session.model_updates=ModelUpdates(self.model_dir.parent,session.output.parent/(session.output.name+'_Modellpruefung.json'))

    @staticmethod
    def entry(session):
        return {'audio':str(session.audio) if session.audio else None,'output':str(session.output),'audio_sha256':session.audio_hash}

    def state(self):
        with self.lock:
            current=self.session
            result=reading(current).state()
            result.update(workspace_id=workspace(current),uploading=self.uploading,recordings=len(self.entries))
            meta=current.output.parent/(current.output.name+'_Aufnahme.json')
            metadata=r.read(meta) if meta.exists() else {}
            result['expected_speakers']=metadata.get('expected_speakers',getattr(current,'expected_speakers',None))
            result['title']=metadata.get('source_name') or result['title']
            result['model_name']=self.model_dir.name
            result['speaker_model_available']=(self.speaker_model_dir/'diar_streaming_sortformer_4spk-v2.onnx').is_file()
            result['speaker_model_path']=str(self.speaker_model_dir)
            speaker_progress=current.output.parent/(current.output.name+'_Sprecher')/'progress.json'
            if speaker_progress.exists():result['speaker_progress']=r.read(speaker_progress)
            info=result.get('speaker_info',{})
            expected=result['expected_speakers']
            result['speaker_count_note']=''
            if expected and expected>4:result['speaker_count_note']='Mehr als vier Personen angegeben: Sortformer kann höchstens vier Labels liefern. Zuordnung manuell prüfen.'
            elif expected and info.get('count') is not None and expected!=info['count']:result['speaker_count_note']=f"Erwartet {expected}, automatisch erkannt {info['count']} Sprecherlabels. Keine automatische Zusammenlegung; bitte prüfen."
            return result

    def eligible(self, old):
        state=old.state()
        if not old.audio or state['status'] in ('failed','interrupted'):
            return None
        if state['status']=='completed' and not r.read(old.output/'transcript.json').get('segments'):
            return None
        editor=reading(old);editor.ensure()
        r.require(editor.is_approved(),'Aktuelle Textprüfung zuerst abschließen.')
        return (editor.store.get()['revision'],r.fingerprint(editor.store.get()['project']))

    def upload(self, handler):
        with self.lock:
            old=self.session
            r.require(handler.headers.get('X-Workspace-Id')==workspace(old),'Andere Aufnahme geöffnet; Seite neu laden. Alter Entwurf bleibt erhalten.')
            r.require(not self.uploading,'Eine Aufnahme wird bereits geladen.')
            approval=self.eligible(old)
            if approval is not None:
                r.require(handler.headers.get('X-Reading-Revision')==str(approval[0]),'Freigabe wurde inzwischen geändert.')
            r.require((self.model_dir/'model_manifest.json').is_file(),'Lokales Whisper-Modell fehlt. Oben unter Modell einrichten / ändern ein vorhandenes Modell wählen oder ausdrücklich zentral herunterladen.')
            length=int(handler.headers.get('Content-Length','0'))
            r.require(0<length<=2*1024*1024*1024,'Aufnahme muss zwischen 1 Byte und 2 GiB groß sein.')
            name=Path(unquote(handler.headers.get('X-Audio-Name',''))).name
            suffix=Path(name).suffix.lower()
            expected=handler.headers.get('X-Expected-Speakers','').strip()
            expected=int(expected) if expected else None
            r.require(expected is None or 1<=expected<=100,'Erwartete Sprecherzahl muss 1 bis 100 oder unbekannt sein.')
            r.require(suffix in ('.wav','.mp3','.m4a','.mp4','.flac','.ogg','.wma','.aac'),'Unterstützte Audiodatei wählen.')
            self.uploading=True
        folder=old.output.parent/('Aufnahme_'+secrets.token_hex(6))
        audio=folder/('Original'+suffix)
        try:
            folder.mkdir()
            handler.connection.settimeout(120)
            with audio.open('xb') as stream:
                remaining=length
                while remaining:
                    block=handler.rfile.read(min(1024*1024,remaining));r.require(block,'Dateiübertragung abgebrochen. Alte Aufnahme bleibt geöffnet.')
                    stream.write(block);remaining-=len(block)
                stream.flush()
                import os
                os.fsync(stream.fileno())
            import av
            with av.open(str(audio)) as container:
                r.require(container.streams.audio and container.duration is not None and 0<container.duration/av.time_base<=7200,'Audiodauer fehlt, keine Audiospur oder länger als 120 Minuten.')
            with self.lock:
                if hasattr(handler,'verify_source'):handler.verify_source()
                r.require(self.session is old and self.eligible(old)==approval,'Freigabe während Upload geändert. Alte Aufnahme bleibt geöffnet; Upload wird nicht gestartet.')
                new=self.factory(audio,folder/'Transkript');self.configure(new)
                atomic_write(folder/'Transkript_Aufnahme.json',{'source_name':name,'expected_speakers':expected,'speaker_count_usage':'plausibility_only_not_model_parameter'})
                entries=self.entries+[self.entry(new)]
                atomic_write(self.path,{'origin':self.origin,'entries':entries})
                self.entries=entries;self.session=new
                job=folder/'Transkript_UI_Job.json'
                sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
                from process_commands import python_command
                command=python_command(Path(__file__).with_name('transcription_pipeline.py'),['--audio',str(audio),'--model-dir',str(self.model_dir),'--output',str(new.output),'--speaker-model-dir',str(self.speaker_model_dir)])
                try:
                    with (folder/'CPU_Protokoll.txt').open('ab') as log:
                        new.worker=subprocess.Popen(command,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=(sys.platform!='win32'))
                except OSError as exc:
                    atomic_write(job,{'status':'failed','error':'CPU-Prozess konnte nicht gestartet werden: '+str(exc)})
                return {'accepted':True,'started':hasattr(new,'worker'),'workspace_id':workspace(new)}
        except BaseException as exc:
            if folder.exists():atomic_write(folder/'Upload_Fehler.json',{'error':str(exc)[:500],'previous_output':str(old.output),'inference_started':False})
            raise
        finally:
            with self.lock:self.uploading=False

    def upload_local(self, handler, body):
        """Stream an explicitly selected local file through the same upload checks."""
        import os
        import stat
        from types import SimpleNamespace
        from urllib.parse import quote
        from local_file_browser import _absolute, _linked, _file_identity
        source=_absolute(body.get('path',''))
        before=source.lstat()
        r.require(not _linked(before) and stat.S_ISREG(before.st_mode),'Eine reguläre Audiodatei auswählen.')
        canonical=source.resolve(strict=True)
        with canonical.open('rb') as stream:
            opened=os.fstat(stream.fileno())
            r.require(_file_identity(opened)==_file_identity(before),'Datei während Auswahl geändert. Erneut auswählen.')
            def verify():
                after=source.lstat();current=os.fstat(stream.fileno())
                r.require(not _linked(after) and source.resolve()==canonical
                    and _file_identity(after)==_file_identity(before)
                    and _file_identity(current)==_file_identity(opened)
                    and current.st_ctime_ns==opened.st_ctime_ns
                    and after.st_ctime_ns==before.st_ctime_ns,'Audiodatei während Übertragung geändert; kein Start.')
            proxy=SimpleNamespace(headers={'X-Workspace-Id':body.get('workspace_id'),
                'X-Reading-Revision':str(body.get('revision','')),'Content-Length':str(opened.st_size),
                'X-Audio-Name':quote(source.name),'X-Expected-Speakers':str(body.get('expected_speakers',''))},
                rfile=stream,connection=handler.connection,verify_source=verify)
            return self.upload(proxy)
