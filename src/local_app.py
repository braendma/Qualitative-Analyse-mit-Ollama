"""Loopback-only desktop companion for the existing, independently usable runner."""
import argparse
import job_storage
import thematic_pipeline
import base64
import copy
import csv
import importlib.util
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer

from project_paths import DEFAULT_CONFIG, DEMO_DIR, default_data_dir, resolve_output_parent
from output_path_advice import output_path_check, output_check_message
from filesystem_paths import canonical_path
from process_commands import python_command, validate_script
import yaml
from runtime_support import atomic_json, atomic_text, exclusive_file_lock, fingerprint, file_hash
from app_lifecycle import ActiveRun, confirmed_cleanup, supervision_paths
from review_workspace import ReviewWorkspace, decisions_xlsx
from telegram_notifications import Telegram, NoRedirect
from llm_providers import PROVIDERS, KEY_ENVS, selection
from provider_keys import ProviderKeys, reject_secret_settings
from progress_presentation import safe_series_progress

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('desktop_runner', ROOT / '00_WORKFLOW_RUNNER.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
MAX_UPLOAD = 20 * 1024 * 1024
csv.field_size_limit(MAX_UPLOAD)


def read_json(path, default=None):
    # On Windows an atomic replacement or virus scanner can briefly deny a read.
    for attempt in range(3):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return default
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(.05)


def safe_child(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Ungültiger Dateipfad.')
    return path


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{20}|[a-f0-9]{32}', value):
        raise ValueError('Ungültige Projekt- oder Datei-ID.')
    return value


def csv_info(raw):
    if len(raw) > MAX_UPLOAD:
        raise ValueError('CSV-Dateien dürfen höchstens 20 MB groß sein.')
    try:
        text = raw.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(text), delimiter=';', strict=True)
        headers = next(reader)
        if len(headers) < 2 or len(headers) != len(set(headers)) or any(not h.strip() for h in headers):
            raise ValueError('Eindeutige Spaltennamen und Semikolon als Trennzeichen erforderlich.')
        rows = []
        count = 0
        for line, row in enumerate(reader, 2):
            if not row:
                continue
            if len(row) != len(headers):
                raise ValueError(f'CSV-Datensatz {line}: Anzahl der Felder passt nicht zur Kopfzeile.')
            count += 1
            if len(rows) < 5:
                rows.append([v[:500] for v in row])
        if not count:
            raise ValueError('CSV-Datei enthält keine Datenzeilen.')
        return {'headers': headers, 'rows': rows, 'count': count}
    except (UnicodeError, StopIteration, csv.Error):
        raise ValueError('Die Datei muss eine lesbare CSV mit UTF-8 und Semikolon sein.') from None


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class App(ReviewWorkspace):
    def __init__(self, directory, template=None):
        self.directory = Path(directory).resolve()
        if os.name == 'nt' and not str(self.directory).startswith('\\\\?\\'):
            self.directory = Path('\\\\?\\'+str(self.directory))
        self.projects_dir = self.directory / 'projects'
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.template = yaml.safe_load((Path(template) if template else DEFAULT_CONFIG).read_text(encoding='utf-8'))
        self.telegram = Telegram(self.directory)
        self.provider_keys = ProviderKeys(self.directory)
        self.lock = threading.RLock()
        self.active = None
        self._session = None
        self._runtime_state = 'open'
        self._runtime_error = ''
        self._shutdown_callback = None
        self._shutdown_worker = None
        self._shutdown_responses = []
        self._shutdown_http = False
        self._shutdown_delivery = threading.Event()
        self._shutdown_delivery_timeout = 20
        self.local_imports = {}

    def runtime_status(self):
        with self.lock:session=self._session
        # A failed monitor must not leave a finished, now verifiable session
        # locked forever. Never wait here while the owned process is alive.
        if session is not None and session.process.poll() is not None:
            self._finish_session(session)
        with self.lock:
            return self._runtime_snapshot()

    def _runtime_snapshot(self):
        return {'state':self._runtime_state,
                'active':self._session.public() if self._session else None,
                'error':self._runtime_error}

    def runtime_delivered(self, status):
        # Called only after the authenticated HTTP response was sent and flushed.
        # An earlier stopping snapshot cannot acknowledge the final cleanup.
        with self.lock:
            if status.get('state')=='closed' and self._runtime_state=='closed':
                self._shutdown_delivery.set()

    def shutdown(self, mode='idle', job=None, attempt=None, confirmed=False, project=None, *, response_sent=None):
        if mode not in ('idle','pause','abort'):
            raise ValueError('Unbekannte Aktion zum Beenden.')
        with self.lock:
            session=self._session
            if self._runtime_state=='closed':return self._runtime_snapshot()
            if session is None:
                if mode!='idle':raise ValueError('Der angezeigte Lauf ist nicht mehr aktiv. Status aktualisieren.')
                self._runtime_state='stopping'
            else:
                if mode=='idle':raise ValueError('Eine Analyse ist aktiv. Zuerst Pause oder bestätigten Abbruch wählen.')
                if (job,attempt)!=(session.job,session.binding['attempt']) or (project is not None and project!=session.project):
                    raise ValueError('Der angezeigte Startversuch ist nicht mehr aktuell. Status aktualisieren.')
                if mode=='abort' and confirmed is not True:
                    raise ValueError('Den Abbruch des eigenen aktiven Laufs ausdrücklich bestätigen.')
                if mode=='pause':
                    atomic_text(session.folder/'pause.request','pause after current module\n')
                    self._runtime_state='waiting_for_pause'
                else:
                    session.stop_requested=True
                    session.release()
                    self._runtime_state='stopping'
            self._runtime_error=''
            event=response_sent or threading.Event()
            if response_sent is None:event.set()
            else:self._shutdown_http=True
            self._shutdown_responses.append(event)
            # An abort may supersede an already pending pause. Both workers share
            # the same owned session and cannot act on a later start attempt.
            if not self._shutdown_worker or not self._shutdown_worker.is_alive():
                self._shutdown_worker=threading.Thread(target=self._wait_shutdown,args=(session,event),daemon=True)
                self._shutdown_worker.start()
            return self._runtime_snapshot()

    def _wait_shutdown(self, session, response_sent):
        response_sent.wait()
        if session is not None:
            # Keep the lease open while the runner reaches a real pause boundary.
            while not session.finished.wait(.2):
                if session.process.poll() is not None:
                    if not self._finish_session(session):return
                with self.lock:
                    if self._runtime_state=='blocked':return
        while True:
            with self.lock:responses=list(self._shutdown_responses)
            for response in responses:response.wait()
            with self.lock:
                if len(responses)!=len(self._shutdown_responses):continue
                if self._session is not None or self._runtime_state=='blocked':return
                self._runtime_state='closed'
                callback=self._shutdown_callback
                wait_for_delivery=self._shutdown_http
                break
        # Keep the confirmed terminal status reachable for the browser. This is
        # an event handshake, not a fixed delay; a departed browser cannot keep
        # the application alive indefinitely. Direct console/API calls need no
        # browser acknowledgement and do not wait here.
        if wait_for_delivery:self._shutdown_delivery.wait(self._shutdown_delivery_timeout)
        if callback:callback()

    def _notify(self,*args,**kwargs):
        # Notification problems must never abandon an owned analysis process.
        try:self.telegram.send(*args,**kwargs)
        except Exception:pass

    def _finish_session(self, session):
        try:
            receipt=session.finish()
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
            with self.lock:
                if self._session is session:
                    self._runtime_state='blocked'
                    self._runtime_error='Prozessende ist noch nicht bestätigt. Nicht erneut starten; Prozessstatus und lokale Protokolle prüfen. '+str(exc)
            return False
        with self.lock:
            if self._session is not session:return True
            try:job=read_json(session.folder/'job.json')
            except (OSError,ValueError) as exc:
                self._runtime_state='blocked';self._runtime_error='Prozess ist beendet, aber der Jobindex ist nicht lesbar: '+str(exc)
                return False
            if not isinstance(job,dict):
                self._runtime_state='blocked';self._runtime_error='Jobindex fehlt. Prozess ist beendet, aber der Laufstatus konnte nicht gespeichert werden.'
                return False
            try:
                run=job_storage.run_path(session.folder,job)
                manifest=read_json(run/'workflow_manifest.json',{}) if run else {}
                status=manifest.get('status','failed')
                if session.stop_requested or receipt.get('parent_released'):
                    status='interrupted'
                elif receipt['exit_code'] or status not in ('success','paused'):
                    status='failed'
                error=manifest.get('error','')
                if status=='interrupted':error='Lauf auf Wunsch unterbrochen. Geprüfte Zwischenergebnisse bleiben erhalten.'
                elif status=='failed' and not error:error='Lauf fehlgeschlagen. Details im lokalen Laufprotokoll.'
            except (OSError,ValueError,KeyError,TypeError) as exc:
                status='interrupted';error='Ergebnisse derzeit nicht lesbar. Ergebnisordner erneut verbinden: '+str(exc)
            job.update(status=status,error=error,cleanup_confirmed=True,
                       supervision=session.binding,pid=session.process.pid)
            try:atomic_json(session.folder/'job.json',job)
            except OSError as exc:
                self._runtime_state='blocked';self._runtime_error='Prozess ist beendet, aber der Jobindex konnte nicht gespeichert werden: '+str(exc)
                return False
            self._session=None;self.active=None
            if self._runtime_state=='blocked':self._runtime_state='open'
            self._runtime_error=''
            session.finished.set()
        self._notify(status)
        return True

    def project_dir(self, pid):
        directory = safe_child(self.projects_dir, identifier(pid))
        if not (directory/'project.json').is_file():
            raise ValueError('Projekt wurde nicht gefunden.')
        return directory

    def job_config(self, pid, jid):
        folder=safe_child(self.project_dir(pid)/'jobs',identifier(jid))
        job=read_json(folder/'job.json')
        if not job: raise ValueError('Lauf nicht gefunden.')
        return job_storage.config_path(folder,job)

    def review_root(self, pid, jid):
        folder=safe_child(self.project_dir(pid)/'jobs',identifier(jid))
        job=read_json(folder/'job.json')
        if not job: raise ValueError('Lauf nicht gefunden.')
        return job_storage.review_root(folder,job)

    def projects(self):
        return sorted([read_json(p) for p in self.projects_dir.glob('*/project.json')], key=lambda p:p['created'], reverse=True)

    def create(self, name, demo=False):
        name = str(name).strip()
        if not name or len(name) > 100:
            raise ValueError('Projektname muss 1 bis 100 Zeichen lang sein.')
        pid = uuid.uuid4().hex[:20]
        directory = self.projects_dir/pid
        directory.mkdir()
        atomic_json(directory/'project.json', {'id':pid, 'name':name, 'created':time.time(), 'revision':None, 'demo':bool(demo)})
        if demo:
            # Dedicated demo copies are independent of a private installation's study CSVs.
            for kind, filename in [('segments','maxqda_export.csv'),('codebook','Kategoriesystem.csv')]:
                path = DEMO_DIR/filename
                if not path.is_file():
                    raise ValueError('Demo-Dateien fehlen in der Installation.')
                self.upload(pid, kind, filename, base64.b64encode(path.read_bytes()).decode())
            from coding_validation_common import CODEBOOK_HEADERS
            demo_headers = csv_info((DEMO_DIR/'Kategoriesystem.csv').read_bytes())['headers']
            atomic_json(directory/'settings.json', {'book_columns':{k:v for k,v in CODEBOOK_HEADERS.items() if v in demo_headers}, 'context':{
                'project_description':'Künstliche Interviews über technische Lernangebote. Alle Aussagen und Personen sind erfunden.',
                'participants':'Sechs frei erfundene Personen eines Demonstrationsdatensatzes.',
                'methodology':'Demonstration einer kategorienbasierten qualitativen Analyse; kein empirischer Qualitätsbenchmark.'}})
        return self.project(pid)

    def project(self, pid):
        directory = self.project_dir(pid)
        data = read_json(directory/'project.json')
        data['uploads'] = read_json(directory/'uploads.json', {})
        data['settings'] = read_json(directory/'settings.json', {})
        return data

    def upload(self, pid, kind, name, encoded, sheet=None):
        if kind not in ('segments', 'codebook'):
            raise ValueError('Unbekannter Dateityp.')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            raise ValueError('Dateiübertragung ist ungültig.') from None
        suffix = Path(str(name)).suffix.lower()
        metadata = {'format': 'csv'}
        normalized = raw
        if suffix == '.xlsx':
            from tabular_import import xlsx_csv
            normalized, metadata = xlsx_csv(raw, sheet)
            if normalized is None:
                return metadata
        elif suffix != '.csv':
            raise ValueError('Bitte eine .xlsx- oder .csv-Datei auswählen. Alte .xls-Dateien zuerst als .xlsx speichern.')
        info = {**csv_info(normalized), **metadata}
        directory = self.project_dir(pid)
        fid = uuid.uuid4().hex[:20]
        path = directory/'inputs'/(fid+'.csv')
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(normalized)
        if suffix == '.xlsx':
            path.with_suffix('.xlsx').write_bytes(raw)
        uploads = read_json(directory/'uploads.json', {})
        uploads[kind] = {'id':fid, 'name':Path(str(name).replace('\\','/')).name[:150], **info}
        atomic_json(directory/'uploads.json', uploads)
        settings = read_json(directory/'settings.json', {})
        settings.pop('columns' if kind == 'segments' else 'book_columns', None)
        if kind == 'segments' and settings.get('output_dir_mode') == 'input':
            settings.update(output_dir='', output_dir_mode='explicit')
        atomic_json(directory/'settings.json', settings)
        project = read_json(directory/'project.json')
        if project.get('revision'): project['last_valid_revision']=project['revision']
        project['revision'] = None
        # Replacing either input starts a new manual input lineage.
        project.pop('review_provenance',None)
        atomic_json(directory/'project.json', project)
        return uploads

    def local_browse(self, pid, path='', kind='directory'):
        from local_file_browser import browse
        self.project_dir(pid)
        return browse(path, kind)

    def local_import(self, pid, kind, path, sheet=None, receipt=None):
        """Read a selected local source through the existing immutable import path."""
        from local_file_browser import read_input
        if kind not in ('segments', 'codebook'):
            raise ValueError('Unbekannter Dateityp.')
        with self.lock:
            project = self.project(pid)
            now = time.monotonic()
            self.local_imports = {k:v for k,v in self.local_imports.items() if now-v['created'] < 600}
            previous_id = project['uploads'].get(kind, {}).get('id')
            pending = None
            if receipt is not None:
                pending = self.local_imports.get(receipt) if isinstance(receipt,str) else None
                if not pending or (pending['project'],pending['kind'],pending['path'],pending['previous_id']) != (pid,kind,path,previous_id):
                    raise ValueError('Die Dateiauswahl ist nicht mehr gültig. Bitte die Datei erneut auswählen.')
                if not isinstance(sheet,str) or not sheet:
                    raise ValueError('Bitte ein Tabellenblatt auswählen.')
            elif sheet is not None:
                raise ValueError('Bitte zuerst die Datei und anschließend ein Tabellenblatt auswählen.')
            source, raw = read_input(path, MAX_UPLOAD)
            digest = hashlib.sha256(raw).hexdigest()
            if pending and digest != pending['sha256']:
                raise ValueError('Die Originaldatei wurde seit der Vorschau geändert. Bitte erneut auswählen.')
            previous_settings = project['settings']
            result = self.upload(pid,kind,source.name,base64.b64encode(raw).decode('ascii'),sheet)
            if result.get('requires_sheet'):
                while len(self.local_imports) >= 16:
                    self.local_imports.pop(next(iter(self.local_imports)))
                token = secrets.token_urlsafe(24)
                self.local_imports[token] = {'created':now,'project':pid,'kind':kind,'path':str(source),
                                            'sha256':digest,'previous_id':previous_id}
                return {**result,'receipt':token,'name':source.name,'source_path':str(source)}
            if receipt is not None:
                self.local_imports.pop(receipt,None)
            result[kind].update(source_path=str(source), source_directory=str(source.parent), source_sha256=digest)
            directory = self.project_dir(pid)
            atomic_json(directory/'uploads.json',result)
            response = {'uploads':result,'source_path':str(source)}
            if kind == 'segments':
                target = str(source.parent)
                response['suggested_output_dir'] = target
                if not previous_settings.get('output_dir') or previous_settings.get('output_dir_mode') == 'input':
                    updated = read_json(directory/'settings.json',{})
                    updated.update(output_dir=target,output_dir_mode='input')
                    atomic_json(directory/'settings.json',updated)
            return response

    def prompt_templates(self, pid, jid=None):
        from prompt_catalog import catalog
        directory=self.project_dir(pid)
        project=self.project(pid)
        if jid:
            folder=safe_child(directory/'jobs',identifier(jid))
            job=read_json(folder/'job.json')
            if not job:raise ValueError('Lauf wurde nicht gefunden.')
            path=self.job_config(pid,jid)
            config=yaml.safe_load(path.read_text(encoding='utf-8'))
            source='Gespeicherte Konfiguration dieses Laufs. Spätere Projekteinstellungen werden hier nicht verwendet.'
        else:
            revision=project.get('revision') or project.get('last_valid_revision')
            if revision:
                path=safe_child(directory/'revisions',revision)/'config.yaml'
                config=yaml.safe_load(path.read_text(encoding='utf-8'))
                source='Zuletzt gültig gespeicherte Projektkonfiguration. Ungespeicherte Formularänderungen sind nicht enthalten.'
            else:
                config=self.template
                source='Programmvorlage: Für dieses Projekt ist noch keine gültige Konfiguration gespeichert.'
        return {**catalog(config,RUNNER.normalize_modules(config)),'source':source}

    def person_preview(self, pid, columns):
        from person_identity import preview
        upload=self.project(pid)['uploads'].get('segments')
        if not upload: raise ValueError('Zuerst eine Interviewdatei auswählen.')
        raw=(self.project_dir(pid)/'inputs'/(upload['id']+'.csv')).read_bytes()
        return preview(raw,columns)

    def passage_preview(self, pid, columns):
        from passage_ids import prepare
        project = self.project(pid)
        upload = project['uploads'].get('segments')
        if not upload: raise ValueError('Zuerst eine Interviewdatei auswählen.')
        raw = (self.project_dir(pid)/'inputs'/(upload['id']+'.csv')).read_bytes()
        return prepare(raw, columns)[0]

    def passage_apply(self, pid, settings, fingerprint, confirmed):
        from passage_ids import apply
        with self.lock:
            reject_secret_settings(settings)
            project = self.project(pid)
            upload = project['uploads'].get('segments')
            if not upload: raise ValueError('Zuerst eine Interviewdatei auswählen.')
            directory = self.project_dir(pid)
            raw = (directory/'inputs'/(upload['id']+'.csv')).read_bytes()
            normalized, mapped, provenance = apply(raw, settings.get('columns',{}), fingerprint, confirmed)
            info = csv_info(normalized)
            fid = uuid.uuid4().hex[:20]
            (directory/'inputs'/(fid+'.csv')).write_bytes(normalized)
            provenance.update(source_input=upload['id'], created=time.time())
            atomic_json(directory/'inputs'/(fid+'.ids.json'), provenance)
            project['uploads']['segments'] = {'id':fid, 'name':Path(upload['name']).stem+' · mit IDs.csv',
                                              'format':'csv', **info, 'id_preparation':provenance}
            for key in ('source_path','source_directory','source_sha256'):
                if key in upload: project['uploads']['segments'][key]=upload[key]
            atomic_json(directory/'uploads.json',project['uploads'])
            updated = copy.deepcopy(settings)
            updated.update(columns=mapped, label_mode='multi_label')
            atomic_json(directory/'settings.json',updated)
            data = read_json(directory/'project.json')
            if data.get('revision'): data['last_valid_revision']=data['revision']
            data['revision']=None
            atomic_json(directory/'project.json',data)
            return self.project(pid)

    def config(self, pid, settings):
        directory = self.project_dir(pid)
        uploads = read_json(directory/'uploads.json', {})
        if not all(k in uploads for k in ('segments','codebook')):
            raise ValueError('Bitte Interviewdatei und Kategoriensystem auswählen.')
        cfg = copy.deepcopy(self.template)
        provenance=read_json(directory/'project.json').get('review_provenance')
        if provenance: cfg['review_provenance']=provenance
        reject_secret_settings(settings)
        selected = selection({'model': cfg['llm']['model'], **settings})
        cfg['llm'].update(selected, log_thinking=False)
        from llm_client import request_timeout_seconds
        cfg['llm']['timeout_seconds'] = request_timeout_seconds({
            'timeout_seconds': settings.get('timeout_seconds', cfg['llm'].get('timeout_seconds', 180))})
        from managed_ollama import workers
        cfg['llm']['parallel_workers'] = workers({**cfg['llm'], 'parallel_workers': settings.get('parallel_workers', 1)})
        for key, lower, upper in [('num_ctx',2048,1048576),('max_tokens',128,131072)]:
            cfg['llm'][key] = int(settings.get(key,cfg['llm'][key]))
            if not lower <= cfg['llm'][key] <= upper:
                raise ValueError(f'{key} muss zwischen {lower} und {upper} liegen.')
        synthesis_calls=settings.get('synthesis_max_calls',cfg['llm'].get('hierarchical_synthesis',{}).get('max_calls',64))
        if type(synthesis_calls) is not int or not 1 <= synthesis_calls <= 10000:
            raise ValueError('Das Aufrufbudget der Gesamtsynthese muss eine ganze Zahl zwischen 1 und 10000 sein.')
        cfg['llm'].setdefault('hierarchical_synthesis',{})['max_calls']=synthesis_calls
        if cfg['llm']['max_tokens'] >= cfg['llm']['num_ctx']:
            raise ValueError('Das Antwortlimit muss kleiner als das Kontextfenster sein.')
        thinking = settings.get('think', cfg['llm'].get('think',False))
        if thinking not in (True, False, 'low','medium','high','max'):
            raise ValueError('Ungültige Thinking-Einstellung.')
        cfg['llm']['think'] = thinking
        cfg['llm']['temperature'] = float(settings.get('temperature',cfg['llm'].get('temperature',0.05)))
        if not 0 <= cfg['llm']['temperature'] <= 2:
            raise ValueError('Temperatur muss zwischen 0 und 2 liegen.')
        for key in ('segment','person','code','segment_id','unit_id'):
            column = str(settings.get('columns',{}).get(key,'')).strip()
            if key in ('segment','person','code') and not column:
                raise ValueError('Text, Person und Code müssen einer Spalte zugeordnet sein.')
            if column and column not in uploads['segments']['headers']:
                raise ValueError(f'Spalte fehlt in Interviewdatei: {column}')
            cfg['columns'][key] = column or None
        mode = settings.get('label_mode','multi_label')
        if mode not in ('multi_label','unspecified'):
            raise ValueError('Ungültiger Codierungsmodus.')
        if mode == 'multi_label' and not cfg['columns']['unit_id']:
            raise ValueError('Mehrfachcodierung benötigt Passage-IDs. Unter Eingaben prüfen „Passage-IDs vorbereiten“ verwenden oder den Zeilenvergleich wählen.')
        cfg['coding_agreement'].update(label_mode=mode, independent_units_confirmed=False)
        for key in ('project_description','participants','methodology'):
            value = str(settings.get('context',{}).get(key,cfg.get('context',{}).get(key,'')))
            if len(value)>12000:
                raise ValueError('Kontextbeschreibung ist zu lang (maximal 12000 Zeichen je Feld).')
            cfg.setdefault('context',{})[key] = value
        if 'analysis_perspectives' in settings:
            cfg['analysis_perspectives'] = copy.deepcopy(settings['analysis_perspectives'])
        thematic_pipeline.modes(cfg)
        modules = RUNNER.normalize_modules(cfg)
        requested = settings.get('modules',[m['id'] for m in modules if m['enabled']])
        if not isinstance(requested,list) or not requested or not set(requested) <= {m['id'] for m in modules}:
            raise ValueError('Mindestens einen gültigen Analyseschritt auswählen.')
        selected = set(requested)
        while True:
            expanded = selected | {d for m in modules if m['id'] in selected for d in m['depends_on']}
            if expanded == selected: break
            selected = expanded
        for m in cfg['pipeline']['modules']:
            m['enabled'] = m['id'] in selected
        for kind in ('stability', 'sensitivity'):
            if kind in selected:
                if cfg.get('diagnostics') is None:
                    cfg['diagnostics'] = {}
                diagnostics = cfg['diagnostics']
                if not isinstance(diagnostics, dict):
                    raise ValueError('diagnostics muss eine Zuordnung für die gewählten Diagnosemodule sein.')
                value = settings.get(kind, diagnostics.get(kind))
                if not isinstance(value, dict):
                    raise ValueError('Für ' + kind + ' Wiederholungszahl, Zielmodule und gegebenenfalls Varianten festlegen.')
                diagnostics[kind] = copy.deepcopy(value)
        RUNNER.topological_order(RUNNER.normalize_modules(cfg))
        cfg['paths']['input_csv'] = str(directory/'inputs'/(uploads['segments']['id']+'.csv'))
        original = directory/'inputs'/(uploads['codebook']['id']+'.csv')
        from coding_validation_common import CODEBOOK_HEADERS
        book_columns = settings.get('book_columns',{})
        names = list(CODEBOOK_HEADERS.values())
        normalized = io.StringIO(newline='')
        writer = csv.writer(normalized, delimiter=';', lineterminator='\n')
        writer.writerow(names)
        mapping = []
        if not isinstance(book_columns, dict):
            raise ValueError('Spaltenzuordnung des Kategoriensystems ist ungültig.')
        if not (book_columns.get('code') or book_columns.get('kategorie')) or not book_columns.get('definition'):
            raise ValueError('Pflichtspalten zuordnen: Code oder Kategorie sowie Definition im Kategoriensystem.')
        used = [v for v in book_columns.values() if v]
        if len(used) != len(set(used)):
            raise ValueError('Jede Kategoriensystem-Spalte darf nur einem Feld zugeordnet werden.')
        for key in CODEBOOK_HEADERS:
            column = book_columns.get(key,'')
            if column and column not in uploads['codebook']['headers']:
                raise ValueError('Unbekannte Kategoriensystem-Spalte.')
            mapping.append(column)
        for row in csv.DictReader(io.StringIO(original.read_text(encoding='utf-8-sig')),delimiter=';'):
            writer.writerow([row.get(column,'') if column else '' for column in mapping])
        return cfg, normalized.getvalue()

    def save(self, pid, settings):
        with self.lock:
            directory = self.project_dir(pid)
            settings=copy.deepcopy(settings)
            if 'output_dir' not in settings:
                previous=read_json(directory/'settings.json',{})
                if 'output_dir' in previous: settings['output_dir']=previous['output_dir']
            if 'output_dir' in settings:
                value=settings['output_dir']
                if not isinstance(value,str): raise ValueError('Speicherort für Analyseergebnisse muss ein Ordnerpfad sein.')
                settings['output_dir']=str(resolve_output_parent(output_dir=value)) if value.strip() else ''
            mode=settings.get('output_dir_mode','explicit')
            if mode not in ('input','explicit'):
                raise ValueError('Bitte den Speicherort aus der Eingabedatei oder ein eigenes Verzeichnis wählen.')
            if mode == 'input':
                source=self.project(pid)['uploads'].get('segments',{}).get('source_path')
                if not source or str(Path(source).parent) != settings.get('output_dir'):
                    raise ValueError('Der Ordner der Eingabedatei ist nicht bekannt oder wurde geändert. Bitte die Datei lokal erneut auswählen oder ein eigenes Ziel wählen.')
            settings['output_dir_mode']=mode
            cfg, book = self.config(pid,settings)
            revision = directory/'revisions'/uuid.uuid4().hex[:20]
            revision.mkdir(parents=True)
            from person_identity import apply
            raw=Path(cfg['paths']['input_csv']).read_bytes()
            normalized,columns,identity=apply(raw,cfg['columns'],settings.get('person_identity'))
            (revision/'segments.csv').write_bytes(normalized)
            cfg['paths']['input_csv']=str(revision/'segments.csv')
            cfg['columns']=columns
            cfg['person_identity']=identity
            atomic_text(revision/'codebook.csv',book)
            cfg['paths']['category_system_csv'] = str(revision/'codebook.csv')
            atomic_text(revision/'config.yaml',yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))
            checked = self.validate_config(revision/'config.yaml')
            if settings.get('output_dir'):
                checked['output_path_check'] = output_path_check(settings['output_dir'],
                    diagnostics=any(m['id'] in ('stability','sensitivity') for m in checked['modules']))
            atomic_json(revision/'settings.json',settings)
            data = read_json(directory/'project.json')
            data['revision'] = revision.name
            data['last_valid_revision'] = revision.name
            atomic_json(directory/'settings.json',settings)
            atomic_json(directory/'project.json',data)
            return checked

    def validate_config(self, path):
        from coding_validation_common import load_codebook, load_segments
        from multi_label_core import group_units
        cfg = yaml.safe_load(path.read_text(encoding='utf-8'))
        _, codes = load_codebook(cfg['paths']['category_system_csv'])
        from person_identity import verify
        verify(Path(cfg['paths']['input_csv']).read_bytes(),cfg['columns'],cfg.get('person_identity'))
        segments = load_segments(cfg['paths']['input_csv'],cfg['columns'])
        if cfg['coding_agreement']['label_mode'] == 'multi_label':
            group_units(segments)
        unknown = [{'row':i+2,'code':s.human_code} for i,s in enumerate(segments) if s.human_code not in codes]
        if unknown:
            raise ValueError('Codes fehlen im Kategoriensystem: '+ '; '.join(f"Zeile {x['row']}: {x['code']}" for x in unknown[:10]))
        modules = RUNNER.topological_order(RUNNER.normalize_modules(cfg))
        for module in modules:
            validate_script(RUNNER.resolve_path(ROOT,module['script']))
        thematic_pipeline.validate_material(path, cfg, modules)
        from stability_analysis import configured_plan, planning_summary
        stability_plan = configured_plan(path)
        sensitivity_plan = configured_plan(path, kind='sensitivity')
        from workflow_effort import effort_summary
        effort = effort_summary(modules, stability=planning_summary(stability_plan),
                                sensitivity=planning_summary(sensitivity_plan))
        effort['analysis_perspectives'] = thematic_pipeline.effort(cfg, modules)
        from context_preflight import check_context, require_context
        context_check=check_context(cfg,segments,codes,modules)
        require_context(context_check)
        return {'valid':True,'segments':len(segments),'persons':len({s.person for s in segments}),
                'context_check':context_check, 'effort':effort,
                **({'stability_plan':planning_summary(stability_plan)} if stability_plan else {}),
                **({'sensitivity_plan':planning_summary(sensitivity_plan)} if sensitivity_plan else {}),
                'passages':len({s.unit_id for s in segments}) if cfg['columns'].get('unit_id') else None,
                'codebook_fields':{key:sum(bool(getattr(c,key)) for c in codes.values()) for key in ('einschluss','ausschluss','abgrenzung','ankerbeispiel')},
                'codes':len(codes),'modules':[{'id':m['id'],'name':m['name'],'requires_model':m['requires_model']} for m in modules], 'model_calls':0}

    def models(self):
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            with opener.open('http://127.0.0.1:11434/api/tags',timeout=5) as response:
                result=json.loads(response.read(2*1024*1024))
            return {'models':[m['name'] for m in result.get('models',[]) if 'cloud' not in m['name'].lower() and not m.get('remote_host')]}
        except Exception:
            raise ValueError('Ollama ist lokal nicht erreichbar. Ollama starten und ein lokales Modell installieren; danach erneut prüfen.') from None

    def jobs(self, pid):
        directory=self.project_dir(pid)
        results=[]
        for folder in sorted((directory/'jobs').glob('*'),reverse=True):
            job=read_json(folder/'job.json')
            if not job: continue
            try:
                run=job_storage.run_path(folder,job)
                manifests=[run/'workflow_manifest.json'] if run else []
                if manifests:
                    manifest=read_json(manifests[0])
                    process_alive = pid_alive(job.get('pid'))
                    stored_status, stored_error = job['status'], job.get('error', '')
                    status = manifest['status']
                    if stored_status == 'running' and process_alive:
                        status = 'running'
                    elif stored_status == 'failed':
                        status = 'failed'
                    elif stored_status == 'running' and status == 'running':
                        status = 'interrupted'
                    job.update(status=status,completed=manifest.get('completed_steps',[]),
                               current=manifest.get('current_module'),
                               error=stored_error if stored_status == 'failed' else manifest.get('error',''))
                    job['run']=manifests[0].parent.name
                    job['module_status']=manifest.get('module_status',{})
                    job['module_errors']=manifest.get('module_errors',{})
                    job['blocked_by']=manifest.get('blocked_by',{})
                    detail=read_json(manifests[0].parent/'progress.json',{})
                    if detail.get('module')==job.get('current'):
                        job['progress_detail']=detail
                    if job['status']=='running' and not pid_alive(job.get('pid')):
                        job['status']='interrupted'
                    cfg=yaml.safe_load(job_storage.config_path(folder,job).read_text(encoding='utf-8'))
                    job['review_provenance']=cfg.get('review_provenance')
                    outputs={f for m in cfg['pipeline']['modules'] if m.get('enabled',True) for f in m.get('outputs',[])}
                    outputs.update(('gesamtbericht.md','gesamtbericht.html'))
                    if any(m['id']=='clusterer' and m.get('enabled',True) for m in cfg['pipeline']['modules']):
                        for suffix in ('*.png','*.svg'):
                            outputs.update(str(p.relative_to(manifests[0].parent)).replace('\\','/') for p in (manifests[0].parent/'plots').glob(suffix))
                    from html_report import IMAGE, local_file
                    for module in cfg['pipeline']['modules']:
                        if not module.get('enabled',True):continue
                        report=module.get('report',{}).get('markdown')
                        if not report:continue
                        try:
                            report_path=local_file(manifests[0].parent,report)
                            if not report_path.is_file():continue
                            for match in IMAGE.finditer(report_path.read_text(encoding='utf-8-sig')):
                                try:
                                    image_path=local_file(manifests[0].parent,str(report_path.parent.relative_to(manifests[0].parent)/match[2].replace('\\','/')))
                                    if image_path.suffix.lower() in ('.png','.svg'):
                                        outputs.add(str(image_path.relative_to(manifests[0].parent)))
                                except ValueError:continue
                        except (ValueError,OSError):continue
                    outputs.update(str(Path(name).with_suffix('.svg')) for name in list(outputs) if name.endswith('.png'))
                    outputs={f.replace('\\','/') for f in outputs}
                    job['files']=[f for f in sorted(outputs) if safe_child(manifests[0].parent,f).is_file() and not f.endswith('.log')]
                else:
                    job.setdefault('completed',[])
                    job['files']=[]
                    if job['status']=='running' and not pid_alive(job.get('pid')):
                        job['status']='interrupted'
                research=job_storage.research_root(folder,job)
                job['research_path']=str(canonical_path(research)) if research else (str(canonical_path(run)) if run else '')
            except (ValueError,OSError,KeyError,TypeError) as exc:
                job['files']=[]
                job['output_error']='Ergebnisse sind nicht zugänglich: '+str(exc)
                if job.get('status')=='running' and not pid_alive(job.get('pid')):
                    job['status']='interrupted'
            job.pop('storage',None)
            job['pause_requested']=(folder/'pause.request').exists() and job['status']=='running'
            if 'supervision' in job:
                try:
                    confirmed_cleanup(folder,job['supervision'])
                    job['cleanup_pending']=False
                except (ValueError,OSError,KeyError,TypeError):
                    job['cleanup_pending']=True
                    if not pid_alive(job.get('pid')):
                        job['status']='interrupted'
                        job['error']='Prozessende noch nicht sicher bestätigt. Lokale Prozessbestätigung prüfen; noch nicht neu starten.'
            job.pop('pid',None)
            job.pop('config',None)
            job.pop('supervision',None)
            results.append(job)
        return sorted(results,key=lambda j:j['created'],reverse=True)

    def start(self, pid, resume=None, prepared_config=None):
        with self.lock:
            previous=self._session
            try:return self._start(pid,resume,prepared_config)
            except Exception:
                failure=sys.exc_info()
                session=self._session if self._session is not previous else None
        # Publication/thread failures release only this call's newly created
        # process. Never kill another request's active session after a race.
        if session is not None:
            session.stop_requested=True
            session.release()
            self._finish_session(session)
        raise failure[1].with_traceback(failure[2])

    def runner_command(self, config, output_dir, pause_file, resume=None):
        command=python_command(ROOT/'00_WORKFLOW_RUNNER.py',['--config',str(config),
            '--output-dir',str(output_dir),'--pause-file',str(pause_file)])
        if resume:command.extend(['--resume',str(resume)])
        return command

    def _start(self, pid, resume=None, prepared_config=None):
        with self.lock:
            if self._runtime_state!='open':raise ValueError('Programm wird beendet oder wartet auf Prozessbestätigung. Zuerst den Laufstatus prüfen.')
            known=[j for p in self.projects() for j in self.jobs(p['id'])]
            if any(j.get('cleanup_pending') for j in known):
                raise ValueError('Prozessende eines früheren Startversuchs ist noch nicht bestätigt. Lokale Prozessbestätigung prüfen; noch nicht neu starten.')
            if self.active is not None or any(j['status']=='running' for j in known):
                raise ValueError('Es läuft bereits eine Analyse. Zuerst deren Abschluss oder Pause abwarten.')
            directory=self.project_dir(pid)
            if resume:
                jid=identifier(resume)
                folder=safe_child(directory/'jobs',jid)
                job=read_json(folder/'job.json')
                if not job: raise ValueError('Lauf nicht gefunden.')
                config=job_storage.config_path(folder,job)
                run=job_storage.run_path(folder,job)
                if run is None: raise ValueError('Dieser Lauf hat keinen wiederaufnehmbaren Zwischenstand. Neuen Lauf starten.')
                if read_json(run/'workflow_manifest.json')['status']=='success':
                    raise ValueError('Dieser Lauf ist bereits abgeschlossen.')
                resolve_output_parent(output_dir=job_storage.runs_root(folder,job),check_write=True)
            else:
                project=read_json(directory/'project.json')
                if not prepared_config and not project['revision']: raise ValueError('Einstellungen zuerst speichern und Eingaben prüfen.')
                setting=read_json(directory/'settings.json',{})
                if not setting.get('output_dir'):
                    raise ValueError('Speicherort für Analyseergebnisse auswählen. Ein Browserupload enthält keinen ursprünglichen Dateiordner.')
                parent=resolve_output_parent(output_dir=setting['output_dir'],check_write=True)
                config=Path(prepared_config or directory/'revisions'/identifier(project['revision'])/'config.yaml')
                jid=uuid.uuid4().hex[:20]
                folder=directory/'jobs'/jid
                folder.mkdir(parents=True)
                job={'id':jid,'created':time.time(),'config':str(config),'status':'starting'}
                config=job_storage.config_path(folder,job)
            try:
                checked=self.validate_config(config)
                cfg=yaml.safe_load(config.read_text(encoding='utf-8'))
                llm=cfg['llm']
                if not resume:
                    from output_path_advice import require_new_output_paths, RUN_NAME_RESERVE
                    from stability_analysis import configured_plan
                    planned_root=parent / ('QualitativeAnalyse_' + jid) / 'runs' / RUN_NAME_RESERVE
                    require_new_output_paths(planned_root, RUNNER.topological_order(RUNNER.normalize_modules(cfg)),
                        plans=(configured_plan(config), configured_plan(config, kind='sensitivity')))
                needs_model=any(m.get('requires_model',True) for m in checked['modules'])
                selected=self.authorize_llm(pid,llm) if needs_model else {'provider':'not_required','model':''}
                from managed_ollama import preflight
                if needs_model: preflight(llm)
            except (ValueError, OSError) as exc:
                # Keep rejected new starts inspectable without allocating a
                # research folder or replacing an existing resume checkpoint.
                if not resume:
                    job.update(status='failed',error=str(exc),start_rejected=True,modules=[])
                    atomic_json(folder/'job.json',job)
                raise
            if not resume:
                job['storage']=job_storage.create_binding(folder,config,parent)
            pause=folder/'pause.request'
            pause.unlink(missing_ok=True)
            run_parent=job_storage.runs_root(folder,job)
            command=self.runner_command(config,run_parent,pause,run if resume else None)
            env={k:v for k,v in os.environ.items() if k not in KEY_ENVS and not k.startswith('WORKFLOW_') and k not in ('QUALITATIVE_MANAGED_OLLAMA_HOST','OLLAMA_API_KEY','OLLAMA_HOST')}
            if needs_model and selected['provider']!='ollama_local':
                env[selected['api_key_env']]=self.provider_keys.keys[selected['provider']]
            env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',MPLBACKEND='Agg')
            job.update(modules=checked['modules'],error='',provider=selected['provider'],model=selected['model'])
            attempt=uuid.uuid4().hex
            binding={'attempt':attempt,'ticket':secrets.token_hex(24),'command_sha256':fingerprint(command),
                     'config_sha256':file_hash(config),'run_parent':str(run_parent),'job_folder':str(folder.resolve())}
            request_path,receipt_path=supervision_paths(folder,binding)
            atomic_json(request_path,binding)
            job['supervision']=binding
            job['cleanup_confirmed']=False
            atomic_json(folder/'job.json',job)
            log=None;process=None
            try:
                log=open(folder/'console.log','ab')
                supervised=python_command(ROOT/'managed_ollama.py',['--command',str(receipt_path),binding['ticket'],*command])
                process=subprocess.Popen(supervised,cwd=str(ROOT),env=env,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,
                                         start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                binding={**binding,'launcher_pid':process.pid}
                session=ActiveRun(pid,jid,folder,process,binding)
                self._session=session;self.active=jid
            except (OSError,ValueError):
                if process is None:
                    job.pop('supervision',None)
                    job.update(status='failed',error='Analyseprozess konnte nicht gestartet werden. Lokale Installation prüfen.')
                    atomic_json(folder/'job.json',job)
                raise
            finally:
                if log:log.close()
            job['supervision']=binding
            job.update(status='running',pid=process.pid,modules=checked['modules'],error='',provider=selected['provider'],model=selected['model'])
            atomic_json(folder/'job.json',job)
            session.thread=threading.Thread(target=self.monitor,args=(folder,process,len(checked['modules'])),daemon=True)
            session.thread.start()
            return {'id':jid,'status':'running'}

    def privacy(self, pid, private):
        if type(private) is not bool: raise ValueError('DSGVO-Einstellung muss ein Wahrheitswert sein.')
        with self.lock:
            if any(j['status']=='running' for j in self.jobs(pid)):
                raise ValueError('Die Datenfreigabe lässt sich erst nach Abschluss oder Pause des laufenden Moduls ändern.')
            directory = self.project_dir(pid)
            settings = read_json(directory/'settings.json', {})
            settings['gdpr_relevant'] = private
            if private:
                settings['provider'] = 'ollama_local'
                if 'cloud' in settings.get('model','').lower() or settings.get('host') == 'https://ollama.com':
                    settings['model'] = self.template['llm']['model']
            atomic_json(directory/'settings.json', settings)
            return {'gdpr_relevant': private}

    def authorize_llm(self, pid, llm, *, installed=True):
        if 'provider' not in llm and llm.get('host') == 'https://ollama.com':
            llm={**llm,'provider':'ollama_cloud','gdpr_relevant':llm.get('gdpr_relevant',False)}
        selected = selection(llm)
        if selected['provider'] != 'ollama_local':
            if self.project(pid)['settings'].get('gdpr_relevant', True):
                raise ValueError('Cloud-Lauf gesperrt: Für dieses Projekt ist DSGVO-relevantes Material aktiviert. Freigabe unter Analyse prüfen.')
            if not self.provider_keys.keys.get(selected['provider']):
                raise ValueError('API-Schlüssel für den gewählten Anbieter zuerst separat speichern.')
        else:
            if os.environ.get('QUALITATIVE_CLOUD_TEST_ONLY') == '1':
                raise ValueError('Lokale Modellaufrufe sind in dieser Cloud-Testoberfläche deaktiviert.')
            if installed and selected['model'] not in self.models()['models']:
                raise ValueError('Das gewählte lokale Modell ist nicht installiert. In Ollama installieren oder ein vorhandenes Modell wählen.')
        return selected

    def save_provider_key(self, pid, values):
        if self.project(pid)['settings'].get('gdpr_relevant', True) and not values.get('remove'):
            raise ValueError('Schlüsselfelder sind bei DSGVO-relevantem Material gesperrt.')
        return self.provider_keys.save(values.get('provider'), values.get('key',''),
                                       values.get('persist',False), values.get('remove',False))

    def model_test(self, pid, values):
        selected = self.authorize_llm(pid, values)
        import ollama
        from llm_client import request_chat
        cfg = {**selected, 'num_ctx': 4096, 'max_attempts': 1, 'timeout_seconds': 90}
        request = {'model': selected['model'], 'messages': [{'role':'user','content':'Antworte ausschließlich mit OK.'}],
                   'options': {'num_predict': 256, 'temperature': 0}, 'think': False}
        response = request_chat(ollama, request, cfg, api_key=self.provider_keys.keys.get(selected['provider']))
        if not response['message']['content'].strip(): raise ValueError('Keine sichtbare Modellantwort.')
        return {'ok': True, 'message': PROVIDERS[selected['provider']]['name'] + ': kurze künstliche Testanfrage beantwortet. Kein vollständiger Analysetest.'}

    def monitor(self, folder, process, total):
        session=self._session
        if session is None or session.process is not process or session.folder!=Path(folder):
            raise ValueError('Keine eigene Prozessaufsicht für diesen Monitor vorhanden.')
        last_count=0
        last_detail=None
        last_failure=None
        last_detail_sent=time.monotonic()
        try:
            self._notify('start')
            while process.poll() is None:
                try:
                    run=job_storage.run_path(folder,read_json(folder/'job.json'))
                    manifest=read_json(run/'workflow_manifest.json',{}) if run else {}
                    detail=read_json(run/'progress.json',{}) if run else {}
                except (OSError,ValueError,KeyError,TypeError):
                    # Offline storage must not release the guard for a live process.
                    time.sleep(1)
                    continue
                if run is not None:
                    if not isinstance(manifest, dict):
                        time.sleep(1)
                        continue
                    if not isinstance(detail, dict):
                        detail = {}
                    count=len(manifest.get('completed_steps',[]))
                    if detail.get('module')!=manifest.get('current_module'):
                        detail={'module':manifest.get('current_module')}
                    current = (safe_series_progress(detail.get('series_current')) or {}) if (
                        detail.get('module') in ('stability', 'sensitivity') and detail.get('phase') == 'repetitions') else {}
                    if 'series_current' in detail:
                        detail['series_current'] = current or None
                    child_detail = current.get('detail', {})
                    child_failed = (child_detail.get('failed') or 0) > 0 or child_detail.get('context_blocked') is True
                    failure=(detail.get('module'),detail.get('failed'),bool(detail.get('context_blocked')),
                             current.get('sample_number'),current.get('module'),child_detail.get('failed'),
                             child_detail.get('context_blocked'))
                    if (detail.get('failed') or detail.get('context_blocked') or child_failed) and failure!=last_failure:
                        self._notify('partial_failed')
                        last_failure=failure
                    marker=tuple(detail.get(k) for k in ('module','completed','total','unit','phase','phase_level',
                        'detail_completed','detail_total','requests','active_requests','request_active',
                        'request_started_at','last_response_at','reused','failed','context_blocked'))
                    # Poll timestamps alone are not new work. Preserve the usual
                    # two-minute throttle for genuine inner counter/phase changes.
                    marker_current = {**current}
                    if 'detail' in marker_current:
                        marker_current['detail'] = {k: v for k, v in child_detail.items() if k != 'updated_at'}
                    marker += (json.dumps(marker_current, sort_keys=True),)
                    tick=time.monotonic()
                    age=tick-last_detail_sent
                    if count>last_count or (marker!=last_detail and age>=120) or (detail.get('module') and age>=600):
                        self._notify('progress',count,total,detail=detail)
                        last_detail,last_detail_sent=marker,tick
                        last_count=count
                time.sleep(1)
        except Exception as exc:
            # Leave the owned handle/lease available for explicit cleanup.
            with self.lock:
                if self._session is session:
                    self._runtime_state='blocked';self._runtime_error='Fortschrittsüberwachung unterbrochen. Laufstatus prüfen: '+str(exc)
        finally:
            if process.poll() is not None:self._finish_session(session)

    def pause(self, pid, jid):
        folder=safe_child(self.project_dir(pid)/'jobs',identifier(jid))
        job=next((j for j in self.jobs(pid) if j['id']==jid),None)
        if not job or job['status']!='running': raise ValueError('Dieser Lauf ist nicht aktiv.')
        atomic_text(folder/'pause.request','pause after current module\n')
        return {'message':'Pause angefordert. Das laufende Modul wird zuerst abgeschlossen.'}

    def artifact(self, pid, jid, name):
        folder=safe_child(self.project_dir(pid)/'jobs',identifier(jid))
        job=next((j for j in self.jobs(pid) if j['id']==jid),None)
        if not job: raise ValueError('Lauf nicht gefunden.')
        if name=='console.log': return folder/'console.log'
        if name not in job['files']: raise ValueError('Diese Datei ist kein freigegebenes Ergebnis.')
        saved=read_json(folder/'job.json')
        run=job_storage.run_path(folder,saved)
        if run is None: raise ValueError('Für diesen Lauf sind noch keine Ergebnisse vorhanden.')
        return safe_child(run,name)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self,*args): pass

    def send_bytes(self,data,content_type,status=200,attachment=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        # Allow only exact bundled review/report code and styles in sandboxed previews.
        template=(ROOT/'review_template.html').read_text(encoding='utf-8')
        hashes={tag:' '.join("'sha256-"+base64.b64encode(hashlib.sha256(part.encode()).digest()).decode()+"'" for part in re.findall('<'+tag+'>(.*?)</'+tag+'>',template,re.S)) for tag in ('script','style')}
        from html_report import csp_hashes
        for tag,values in csp_hashes().items():hashes[tag]+=' '+' '.join(values)
        self.send_header('Content-Security-Policy',f"default-src 'none'; script-src 'self' {hashes['script']}; style-src 'self' {hashes['style']}; connect-src 'self'; img-src 'self' blob: data:; frame-src blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        if attachment: self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(attachment))
        self.end_headers()
        self.wfile.write(data)

    def json(self,value,status=200):
        self.send_bytes(json.dumps(value,ensure_ascii=False).encode(),'application/json; charset=utf-8',status)

    def allowed(self,auth=True):
        host=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host')!=host: return False
        if self.headers.get('Origin') not in (None,'http://'+host): return False
        if self.headers.get('Sec-Fetch-Site') in ('cross-site','same-site'): return False
        return not auth or secrets.compare_digest(self.headers.get('X-App-Token',''),self.server.token)

    def do_GET(self):
        parsed=urllib.parse.urlparse(self.path)
        assets={'/':'local_app.html','/app.js':'local_app.js','/app.css':'local_app.css',
                '/review.js':'review_ui.js','/reports.js':'report_viewer.js',
                '/prompt-view.js':'prompt_view.js','/failure-guide.js':'failure_guide.js','/context-help.js':'context_help.js','/context-help.css':'context_help.css',
                '/BEISPIELE.html':'../docs/BEISPIELE.html',
                '/capacity.js':'capacity_ui.js','/providers.js':'providers_ui.js','/passage-ids.js':'passage_ids_ui.js','/person-identity.js':'person_identity_ui.js','/logo.jpg':'brand.jpg','/favicon.ico':'brand.jpg',
                '/handbuch':'../docs/HANDBUCH.html','/HANDBUCH.html':'../docs/HANDBUCH.html','/manual.css':'../docs/manual.css',
                '/images/local-file-selection.svg':'../docs/images/local-file-selection.svg',
                '/BEDIENOBERFLAECHE.md':'../docs/BEDIENOBERFLAECHE.md',
                '/WINDOWS_STANDALONE.txt':'../docs/WINDOWS_STANDALONE.txt',
                '/DIAGNOSTICS.md':'../docs/DIAGNOSTICS.md','/CONFIGURATION.md':'../docs/CONFIGURATION.md',
                '/METHODOLOGY.md':'../docs/METHODOLOGY.md','/ROBUSTNESS.md':'../docs/ROBUSTNESS.md',
                '/KI_ANBIETER.md':'../docs/KI_ANBIETER.md','/EXTENSIONS.md':'../docs/EXTENSIONS.md','/RELEASE_NOTES.md':'../docs/RELEASE_NOTES.md'}
        for screenshot in (ROOT.parent/'docs/screenshots').glob('*'):
            if screenshot.is_file() and screenshot.suffix.lower() in {'.jpg','.png'}:
                assets['/screenshots/'+screenshot.name]='../docs/screenshots/'+screenshot.name
        if not self.allowed(auth=parsed.path not in assets): return self.json({'error':'Zugriff abgelehnt. Oberfläche über die Startdatei öffnen.'},403)
        try:
            if parsed.path in assets:
                p=ROOT/assets[parsed.path]
                return self.send_bytes(p.read_bytes(),{'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.jpg':'image/jpeg','.png':'image/png','.svg':'image/svg+xml','.md':'text/plain; charset=utf-8','.txt':'text/plain; charset=utf-8'}[p.suffix.lower()])
            query=urllib.parse.parse_qs(parsed.query)
            get=lambda key:query.get(key,[''])[0]
            app=self.server.app
            if parsed.path=='/api/state':
                cfg=app.template
                diagnostics=cfg.get('diagnostics')
                if not isinstance(diagnostics,dict):diagnostics={}
                return self.json({'projects':app.projects(),'runtime':app.runtime_status(),'telegram':app.telegram.public(),'providers':PROVIDERS,'provider_keys':app.provider_keys.public(),
                    'defaults':{'llm':{**{k:cfg['llm'].get(k) for k in ('model','num_ctx','max_tokens','temperature','think')},'timeout_seconds':cfg['llm'].get('timeout_seconds',180),'synthesis_max_calls':cfg['llm'].get('hierarchical_synthesis',{}).get('max_calls',64)},'context':cfg['context'],'columns':cfg['columns'],
                                'analysis_perspectives':thematic_pipeline.default_modes(cfg),
                                'stability':diagnostics.get('stability',{'modules':[],'repetitions':3}),
                                'sensitivity':diagnostics.get('sensitivity',{'modules':[],'repetitions':2,'variants':[]})},
                    'modules':[{k:m[k] for k in ('id','name','depends_on','enabled','requires_model','starts_child_runs','after_if_enabled')} |
                        {'cost_profile':m.get('cost_profile'), 'perspective_capability':thematic_pipeline.capability(m)} for m in RUNNER.normalize_modules(cfg)]})
            if parsed.path=='/api/project': return self.json(app.project(get('project')))
            if parsed.path=='/api/runtime':
                status=app.runtime_status()
                self.json(status)
                self.wfile.flush()
                app.runtime_delivered(status)
                return
            if parsed.path=='/api/prompts': return self.json(app.prompt_templates(get('project'),get('job') or None))
            if parsed.path=='/api/jobs': return self.json({'jobs':app.jobs(get('project')),'telegram':app.telegram.public()})
            if parsed.path=='/api/models': return self.json(app.models())
            if parsed.path=='/api/review':return self.json(app.review(get('project'),get('job')))
            if parsed.path=='/api/category-versions':return self.json({'versions':app.category_versions(get('project'))})
            if parsed.path=='/api/review-export':
                loaded=app.review(get('project'),get('job'))
                if get('format')=='xlsx':
                    return self.send_bytes(decisions_xlsx(loaded['queue'],loaded['draft']),
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',attachment='Pruefentscheidungen.xlsx')
                return self.send_bytes(json.dumps(loaded['draft'],ensure_ascii=False).encode('utf-8'),
                    'application/json',attachment='review_decisions.json')
            if parsed.path=='/api/artifact':
                path=app.artifact(get('project'),get('job'),get('name'))
                if path.stat().st_size>100*1024*1024: raise ValueError('Datei ist für den Browser zu groß. Im lokalen Projektordner öffnen.')
                raw=path.read_bytes()
                if path.suffix.lower()=='.svg':
                    from svg_images import passive_svg
                    raw=passive_svg(raw)
                return self.send_bytes(raw,mimetypes.guess_type(path.name)[0] or 'application/octet-stream',attachment=path.name)
            self.json({'error':'Nicht gefunden.'},404)
        except (ValueError,OSError,KeyError) as exc: self.json({'error':str(exc)},400)

    def do_POST(self):
        # Rejected uploads may leave unread request bytes. Do not reuse that socket.
        self.close_connection = True
        if not self.allowed(): return self.json({'error':'Zugriff abgelehnt.'},403)
        if self.headers.get('Content-Type')!='application/json': return self.json({'error':'JSON erwartet.'},415)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<MAX_UPLOAD*2: raise ValueError('Anfrage ist leer oder zu groß.')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('JSON-Objekt erwartet.')
            app=self.server.app
            path=urllib.parse.urlparse(self.path).path
            if path=='/api/ollama-capacity':
                from ollama_capacity import check
                return self.json(check(data['selection']))
            if path=='/api/local-browse':
                return self.json(app.local_browse(data['project'],data.get('path',''),data.get('kind','directory')))
            if path=='/api/shutdown':
                sent=threading.Event()
                result=app.shutdown(data.get('mode','idle'),data.get('job'),data.get('attempt'),
                                    data.get('confirmed',False),data.get('project'),response_sent=sent)
                try:return self.json(result)
                finally:sent.set()
            with app.lock:
                if path=='/api/create': result=app.create(data.get('name',''),data.get('demo',False))
                elif path=='/api/upload': result=app.upload(data['project'],data['kind'],data['name'],data['data'],data.get('sheet'))
                elif path=='/api/local-import': result=app.local_import(data['project'],data['kind'],data['path'],data.get('sheet'),data.get('receipt'))
                elif path=='/api/privacy': result=app.privacy(data['project'],data['gdpr_relevant'])
                elif path=='/api/provider-key': result=app.save_provider_key(data['project'],data)
                elif path=='/api/output-check':
                    app.project_dir(data['project'])
                    target=resolve_output_parent(output_dir=data.get('output_dir',''),check_write=True)
                    check=output_path_check(target)
                    result={'output_dir':str(target),'message':output_check_message(check),'output_path_check':check}
                elif path=='/api/save': result=app.save(data['project'],data['settings'])
                elif path=='/api/person-preview': result=app.person_preview(data['project'],data['columns'])
                elif path=='/api/passage-preview': result=app.passage_preview(data['project'],data['columns'])
                elif path=='/api/passage-apply': result=app.passage_apply(data['project'],data['settings'],data['fingerprint'],data['confirmed'])
                elif path=='/api/start': result=app.start(data['project'],data.get('resume'))
                elif path=='/api/pause': result=app.pause(data['project'],data['job'])
                elif path=='/api/review-save': result=app.save_review(data['project'],data['job'],data['decision'],data['revision'])
                elif path=='/api/followup-preview': result=app.followup_preview(data['project'],data['job'])
                elif path=='/api/followup-prepare': result=app.prepare_followup(data['project'],data['job'],data['revision'],data.get('accept_exclusions',False))
                elif path=='/api/refinement-start': result=app.start_refinement(data['project'],data['job'],data['revision'])
                elif path=='/api/category-compare': result=app.compare_categories(data['project'],data['settings'],data.get('baseline'))
                elif path=='/api/setup-check':
                    from setup_checks import check_setup
                    result=check_setup(app,str(data.get('model','')),data.get('selection'),data.get('project'))
                elif path=='/api/model-test':
                    from setup_checks import test_local_model
                    from llm_client import LLMError
                    if app.active is not None or any(j['status']=='running' for p in app.projects() for j in app.jobs(p['id'])):
                        raise ValueError('Während einer Analyse keinen zusätzlichen Modelltest starten.')
                    try:result=app.model_test(data['project'],data['selection'])
                    except LLMError as exc:raise ValueError(str(exc)) from None
                elif path=='/api/telegram': result=app.telegram.save(data)
                elif path=='/api/telegram-test': result={'sent':app.telegram.send('start',test=True)}
                else: return self.json({'error':'Nicht gefunden.'},404)
            self.json(result)
        except PermissionError:
            self.json({'error':'Dateizugriff wurde vom Betriebssystem verweigert. '
                'Betroffene Dateien in anderen Programmen schließen und die Schreibrechte des gewählten Ordners prüfen. '
                'Auch der Virenschutz kann das Speichern blockieren: seine Meldungen und die Freigabe für dieses '
                'geprüfte Programm kontrollieren. Danach den Vorgang erneut ausführen.'},400)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            if self.path.startswith('/api/provider-key') and not isinstance(exc,ValueError):
                return self.json({'error':'API-Schlüssel konnte nicht gespeichert werden.'},400)
            self.json({'error':str(exc) if not self.path.startswith('/api/telegram') else
                       (str(exc) if isinstance(exc,ValueError) else 'Telegram-Einstellung konnte nicht gespeichert werden.')},400)


class LocalHTTPServer(ThreadingHTTPServer):
    # A handbook loads several images in parallel; keep their connections queued.
    request_queue_size = 64

    def server_bind(self):
        # This server uses a numeric loopback address only. HTTPServer's reverse
        # DNS lookup adds a network-dependent wait before the local UI is ready.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def make_server(app,port=0):
    server=LocalHTTPServer(('127.0.0.1',port),Handler)
    server.app=app
    server.token=secrets.token_urlsafe(32)
    app._shutdown_callback=server.shutdown
    return server


def main():
    parser=argparse.ArgumentParser(description='Lokale Bedienoberfläche für qualitative Analyse')
    parser.add_argument('--data-dir',default=None,help='Technische App-Daten; vorhandene Projektablage wird automatisch erkannt')
    parser.add_argument('--config',default=None,help='Vertrauenswürdige lokale Vorlage, keine Browser-Uploads von ausführbaren Pipelines')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    try:
        data_dir = args.data_dir if args.data_dir is not None else default_data_dir()
    except ValueError as exc:
        parser.error(str(exc))
    data_dir=Path(data_dir).resolve();data_dir.mkdir(parents=True,exist_ok=True)
    instance=exclusive_file_lock(data_dir/'.app-instance.lock')
    try:instance.__enter__()
    except RuntimeError:
        parser.error('Diese Projektablage ist bereits geöffnet. Vorhandene Oberfläche verwenden oder zuerst beenden.')
    from app_logging import AppLog
    app_log=AppLog(data_dir,ROOT.parent/'VERSION')
    try:
        app_log.event('start')
        app=App(data_dir,args.config);server=make_server(app,args.port)
        try:
            url=f'http://127.0.0.1:{server.server_port}/#'+server.token
            print('Lokale Oberfläche: '+url,flush=True)
            print('Programm über die Oberfläche beenden. Strg+C fordert bei laufender Analyse eine sichere Pause an.',flush=True)
            if not args.no_browser:webbrowser.open(url)
            while app.runtime_status()['state']!='closed':
                try:server.serve_forever()
                except KeyboardInterrupt:
                    current=app.runtime_status();active=current['active']
                    if active:
                        app.shutdown('pause',active['job'],active['attempt'])
                        print('Pause angefordert. Die Oberfläche bleibt bis zum bestätigten Prozessende verfügbar. Für sofortigen Abbruch die bestätigte Aktion in der Oberfläche verwenden.',flush=True)
                    else:app.shutdown('idle')
        finally:server.server_close()
        app_log.event('closed')
    except BaseException as exc:
        app_log.event('unhandled_error',exc)
        raise
    finally:
        app_log.close()
        instance.__exit__(None,None,None)


if __name__=='__main__': main()
