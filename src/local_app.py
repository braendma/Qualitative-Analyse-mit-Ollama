"""Loopback-only desktop companion for the existing, independently usable runner."""
import argparse
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

from project_paths import DEFAULT_CONFIG, DEMO_DIR
import yaml
from runtime_support import atomic_json, atomic_text
from review_workspace import ReviewWorkspace, decisions_xlsx
from telegram_notifications import Telegram, NoRedirect
from llm_providers import PROVIDERS, KEY_ENVS, selection
from provider_keys import ProviderKeys

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('desktop_runner', ROOT / '00_WORKFLOW_RUNNER.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
MAX_UPLOAD = 20 * 1024 * 1024
csv.field_size_limit(MAX_UPLOAD)


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


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


def reject_secret_settings(settings):
    # Browser settings are persisted verbatim in revisions: reject credential-like
    # keys recursively before any snapshot, including passage-ID preparation.
    if isinstance(settings, dict):
        for key, value in settings.items():
            if re.search(r'(api.?key|token(?!s$)|secret|password|authorization|credential)',str(key),re.I):
                raise ValueError('API-Schlüssel ausschließlich im separaten Schlüsselfeld speichern.')
            reject_secret_settings(value)
    elif isinstance(settings, list):
        for value in settings: reject_secret_settings(value)


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

    def project_dir(self, pid):
        directory = safe_child(self.projects_dir, identifier(pid))
        if not (directory/'project.json').is_file():
            raise ValueError('Projekt wurde nicht gefunden.')
        return directory

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
            atomic_json(directory/'settings.json', {'context':{
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
        atomic_json(directory/'settings.json', settings)
        project = read_json(directory/'project.json')
        if project.get('revision'): project['last_valid_revision']=project['revision']
        project['revision'] = None
        # Replacing either input starts a new manual input lineage.
        project.pop('review_provenance',None)
        atomic_json(directory/'project.json', project)
        return uploads

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
        for key, lower, upper in [('num_ctx',2048,1048576),('max_tokens',128,131072)]:
            cfg['llm'][key] = int(settings.get(key,cfg['llm'][key]))
            if not lower <= cfg['llm'][key] <= upper:
                raise ValueError(f'{key} muss zwischen {lower} und {upper} liegen.')
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
        modules = RUNNER.normalize_modules(cfg)
        requested = settings.get('modules',[m['id'] for m in modules])
        if not isinstance(requested,list) or not requested or not set(requested) <= {m['id'] for m in modules}:
            raise ValueError('Mindestens einen gültigen Analyseschritt auswählen.')
        selected = set(requested)
        while True:
            expanded = selected | {d for m in modules if m['id'] in selected for d in m['depends_on']}
            if expanded == selected: break
            selected = expanded
        for m in cfg['pipeline']['modules']:
            m['enabled'] = m['id'] in selected
        RUNNER.topological_order(RUNNER.normalize_modules(cfg))
        cfg['paths']['input_csv'] = str(directory/'inputs'/(uploads['segments']['id']+'.csv'))
        original = directory/'inputs'/(uploads['codebook']['id']+'.csv')
        from coding_validation_common import CODEBOOK_ALIASES
        book_columns = settings.get('book_columns',{})
        names = ['Kategorie','Unterkategorie','Ausprägung','Facette','Definition','Ankerbeispiel']
        normalized = io.StringIO(newline='')
        writer = csv.writer(normalized, delimiter=';', lineterminator='\n')
        writer.writerow(names)
        mapping = []
        for key in CODEBOOK_ALIASES:
            column = book_columns.get(key,'')
            if column and column not in uploads['codebook']['headers']:
                raise ValueError('Unbekannte Kategoriensystem-Spalte.')
            if key in ('kategorie','definition') and not column:
                raise ValueError('Kategorie und Definition im Kategoriensystem zuordnen.')
            mapping.append(column)
        for row in csv.DictReader(io.StringIO(original.read_text(encoding='utf-8-sig')),delimiter=';'):
            writer.writerow([row.get(column,'') if column else '' for column in mapping])
        return cfg, normalized.getvalue()

    def save(self, pid, settings):
        with self.lock:
            cfg, book = self.config(pid,settings)
            directory = self.project_dir(pid)
            revision = directory/'revisions'/uuid.uuid4().hex[:20]
            revision.mkdir(parents=True)
            atomic_text(revision/'codebook.csv',book)
            cfg['paths']['category_system_csv'] = str(revision/'codebook.csv')
            atomic_text(revision/'config.yaml',yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))
            checked = self.validate_config(revision/'config.yaml')
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
        segments = load_segments(cfg['paths']['input_csv'],cfg['columns'])
        if cfg['coding_agreement']['label_mode'] == 'multi_label':
            group_units(segments)
        unknown = [{'row':i+2,'code':s.human_code} for i,s in enumerate(segments) if s.human_code not in codes]
        if unknown:
            raise ValueError('Codes fehlen im Kategoriensystem: '+ '; '.join(f"Zeile {x['row']}: {x['code']}" for x in unknown[:10]))
        modules = RUNNER.topological_order(RUNNER.normalize_modules(cfg))
        return {'valid':True,'segments':len(segments),'persons':len({s.person for s in segments}),
                'passages':len({s.unit_id for s in segments}) if cfg['columns'].get('unit_id') else None,
                'codes':len(codes),'modules':[{'id':m['id'],'name':m['name']} for m in modules], 'model_calls':0}

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
            manifests=list((folder/'runs').glob('*/workflow_manifest.json'))
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
                detail=read_json(manifests[0].parent/'progress.json',{})
                if detail.get('module')==job.get('current'):
                    job['progress_detail']=detail
                if job['status']=='running' and not pid_alive(job.get('pid')):
                    job['status']='interrupted'
                cfg=yaml.safe_load(Path(job['config']).read_text(encoding='utf-8'))
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
            job['pause_requested']=(folder/'pause.request').exists() and job['status']=='running'
            job.pop('pid',None)
            job.pop('config',None)
            results.append(job)
        return sorted(results,key=lambda j:j['created'],reverse=True)

    def start(self, pid, resume=None, prepared_config=None):
        with self.lock:
            # One analysis at a time across all projects, including after browser/server restart.
            if self.active is not None or any(j['status']=='running' for p in self.projects() for j in self.jobs(p['id'])):
                raise ValueError('Es läuft bereits eine Analyse. Zuerst deren Abschluss oder Pause abwarten.')
            directory=self.project_dir(pid)
            if resume:
                jid=identifier(resume)
                folder=safe_child(directory/'jobs',jid)
                job=read_json(folder/'job.json')
                if not job: raise ValueError('Lauf nicht gefunden.')
                manifests=list((folder/'runs').glob('*/workflow_manifest.json'))
                if not manifests: raise ValueError('Dieser Lauf hat keinen wiederaufnehmbaren Zwischenstand. Neuen Lauf starten.')
                if read_json(manifests[0])['status']=='success': raise ValueError('Dieser Lauf ist bereits abgeschlossen.')
                config=Path(job['config'])
            else:
                project=read_json(directory/'project.json')
                if not prepared_config and not project['revision']: raise ValueError('Einstellungen zuerst speichern und Eingaben prüfen.')
                config=prepared_config or directory/'revisions'/identifier(project['revision'])/'config.yaml'
                jid=uuid.uuid4().hex[:20]
                folder=directory/'jobs'/jid
                folder.mkdir(parents=True)
                job={'id':jid,'created':time.time(),'config':str(config),'status':'starting'}
            checked=self.validate_config(config)
            llm = yaml.safe_load(config.read_text(encoding='utf-8'))['llm']
            selected = self.authorize_llm(pid, llm)
            pause=folder/'pause.request'
            pause.unlink(missing_ok=True)
            command=[sys.executable,str(ROOT/'00_WORKFLOW_RUNNER.py'),'--config',str(config),'--output-dir',str(folder/'runs'),'--pause-file',str(pause)]
            if resume: command.extend(['--resume',str(manifests[0].parent)])
            env={k:v for k,v in os.environ.items() if k not in KEY_ENVS and k not in ('OLLAMA_API_KEY','OLLAMA_HOST','WORKFLOW_CHECKPOINT_DIR','WORKFLOW_FINGERPRINT','WORKFLOW_RUN_ID','WORKFLOW_PROGRESS_FILE','WORKFLOW_MODULE')}
            if selected['provider'] != 'ollama_local':
                env[selected['api_key_env']] = self.provider_keys.keys[selected['provider']]
            env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',MPLBACKEND='Agg')
            log=open(folder/'console.log','ab')
            try:
                process=subprocess.Popen(command,cwd=str(ROOT),env=env,stdout=log,stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            finally:
                log.close()
            job.update(status='running',pid=process.pid,modules=checked['modules'],error='',provider=selected['provider'],model=selected['model'])
            atomic_json(folder/'job.json',job)
            self.active=jid
            threading.Thread(target=self.monitor,args=(folder,process,len(checked['modules'])),daemon=True).start()
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
        last_count=0
        last_detail=None
        last_detail_sent=time.monotonic()
        try:
            self.telegram.send('start')
            while process.poll() is None:
                manifests=list((folder/'runs').glob('*/workflow_manifest.json'))
                if manifests:
                    count=len(read_json(manifests[0]).get('completed_steps',[]))
                    if count>last_count:
                        self.telegram.send('progress',count,total)
                        last_count=count
                    detail=read_json(manifests[0].parent/'progress.json',{})
                    marker=(detail.get('module'),detail.get('completed'),detail.get('requests'))
                    if marker!=last_detail and time.monotonic()-last_detail_sent>=120:
                        self.telegram.send('progress',count,total,detail=detail)
                        last_detail,last_detail_sent=marker,time.monotonic()
                time.sleep(1)
            manifests=list((folder/'runs').glob('*/workflow_manifest.json'))
            manifest=read_json(manifests[0],{}) if manifests else {}
            status=manifest.get('status','failed')
            if process.returncode or status not in ('success','paused'): status='failed'
            job=read_json(folder/'job.json')
            job.update(status=status,error=manifest.get('error','') or ('Lauf fehlgeschlagen. Details im lokalen Laufprotokoll.' if status == 'failed' else ''))
            atomic_json(folder/'job.json',job)
            self.telegram.send(status)
        finally:
            with self.lock: self.active=None

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
        return safe_child(folder/'runs'/job['run'],name)


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
                '/providers.js':'providers_ui.js','/passage-ids.js':'passage_ids_ui.js','/logo.jpg':'brand.jpg','/favicon.ico':'brand.jpg',
                '/handbuch':'../docs/HANDBUCH.html','/manual.css':'../docs/manual.css',
                '/BEDIENOBERFLAECHE.md':'../docs/BEDIENOBERFLAECHE.md',
                '/KI_ANBIETER.md':'../docs/KI_ANBIETER.md','/EXTENSIONS.md':'../docs/EXTENSIONS.md','/RELEASE_NOTES.md':'../docs/RELEASE_NOTES.md'}
        for screenshot in (ROOT.parent/'docs/screenshots').glob('*.jpg'):
            assets['/screenshots/'+screenshot.name]='../docs/screenshots/'+screenshot.name
        if not self.allowed(auth=parsed.path not in assets): return self.json({'error':'Zugriff abgelehnt. Oberfläche über die Startdatei öffnen.'},403)
        try:
            if parsed.path in assets:
                p=ROOT/assets[parsed.path]
                return self.send_bytes(p.read_bytes(),{'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.jpg':'image/jpeg','.md':'text/plain; charset=utf-8'}[p.suffix])
            query=urllib.parse.parse_qs(parsed.query)
            get=lambda key:query.get(key,[''])[0]
            app=self.server.app
            if parsed.path=='/api/state':
                cfg=app.template
                return self.json({'projects':app.projects(),'telegram':app.telegram.public(),'providers':PROVIDERS,'provider_keys':app.provider_keys.public(),
                    'defaults':{'llm':{k:cfg['llm'].get(k) for k in ('model','num_ctx','max_tokens','temperature','think')},'context':cfg['context'],'columns':cfg['columns']},
                    'modules':[{'id':m['id'],'name':m['name'],'depends_on':m['depends_on']} for m in RUNNER.normalize_modules(cfg)]})
            if parsed.path=='/api/project': return self.json(app.project(get('project')))
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
            with app.lock:
                if path=='/api/create': result=app.create(data.get('name',''),data.get('demo',False))
                elif path=='/api/upload': result=app.upload(data['project'],data['kind'],data['name'],data['data'],data.get('sheet'))
                elif path=='/api/privacy': result=app.privacy(data['project'],data['gdpr_relevant'])
                elif path=='/api/provider-key': result=app.save_provider_key(data['project'],data)
                elif path=='/api/save': result=app.save(data['project'],data['settings'])
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
        except (ValueError,OSError,KeyError,TypeError) as exc:
            if self.path.startswith('/api/provider-key') and not isinstance(exc,ValueError):
                return self.json({'error':'API-Schlüssel konnte nicht gespeichert werden.'},400)
            self.json({'error':str(exc) if not self.path.startswith('/api/telegram') else
                       (str(exc) if isinstance(exc,ValueError) else 'Telegram-Einstellung konnte nicht gespeichert werden.')},400)


class LocalHTTPServer(ThreadingHTTPServer):
    # A handbook loads several images in parallel; keep their connections queued.
    request_queue_size = 64


def make_server(app,port=0):
    server=LocalHTTPServer(('127.0.0.1',port),Handler)
    server.app=app
    server.token=secrets.token_urlsafe(32)
    return server


def main():
    parser=argparse.ArgumentParser(description='Lokale Bedienoberfläche für qualitative Analyse')
    parser.add_argument('--data-dir',default=str(Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'QualitativeOllama'))
    parser.add_argument('--config',default=None,help='Vertrauenswürdige lokale Vorlage, keine Browser-Uploads von ausführbaren Pipelines')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    server=make_server(App(args.data_dir,args.config),args.port)
    url=f'http://127.0.0.1:{server.server_port}/#'+server.token
    print('Lokale Oberfläche: '+url,flush=True)
    print('Dieses Fenster während der Analyse geöffnet lassen. Beenden mit Strg+C.',flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
