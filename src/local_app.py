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
from telegram_notifications import Telegram, NoRedirect

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


class App:
    def __init__(self, directory, template=None):
        self.directory = Path(directory).resolve()
        if os.name == 'nt' and not str(self.directory).startswith('\\\\?\\'):
            self.directory = Path('\\\\?\\'+str(self.directory))
        self.projects_dir = self.directory / 'projects'
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.template = yaml.safe_load((Path(template) if template else DEFAULT_CONFIG).read_text(encoding='utf-8'))
        self.telegram = Telegram(self.directory)
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
        project['revision'] = None
        atomic_json(directory/'project.json', project)
        return uploads

    def config(self, pid, settings):
        directory = self.project_dir(pid)
        uploads = read_json(directory/'uploads.json', {})
        if not all(k in uploads for k in ('segments','codebook')):
            raise ValueError('Bitte Interviewdatei und Kategoriensystem auswählen.')
        cfg = copy.deepcopy(self.template)
        model = str(settings.get('model', cfg['llm']['model'])).strip()
        if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',model) or 'cloud' in model.lower():
            raise ValueError('Bitte einen lokalen Ollama-Modellnamen ohne Cloud-Verweis wählen.')
        cfg['llm'].update(host='http://localhost:11434', model=model, log_thinking=False)
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
            raise ValueError('Mehrfachcodierung benötigt eine explizite Passage-ID-Spalte. Keine IDs aus ähnlichen Texten ableiten.')
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
            data = read_json(directory/'project.json')
            data['revision'] = revision.name
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
                if job['status']=='running' and not pid_alive(job.get('pid')):
                    job['status']='interrupted'
                cfg=yaml.safe_load(Path(job['config']).read_text(encoding='utf-8'))
                outputs={f for m in cfg['pipeline']['modules'] if m.get('enabled',True) for f in m.get('outputs',[])}
                outputs.add('gesamtbericht.md')
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

    def start(self, pid, resume=None):
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
                if not project['revision']: raise ValueError('Einstellungen zuerst speichern und Eingaben prüfen.')
                config=directory/'revisions'/identifier(project['revision'])/'config.yaml'
                jid=uuid.uuid4().hex[:20]
                folder=directory/'jobs'/jid
                folder.mkdir(parents=True)
                job={'id':jid,'created':time.time(),'config':str(config),'status':'starting'}
            checked=self.validate_config(config)
            model=yaml.safe_load(config.read_text(encoding='utf-8'))['llm']['model']
            if model not in self.models()['models']:
                raise ValueError('Das gewählte lokale Modell ist nicht installiert. In Ollama installieren oder ein vorhandenes Modell wählen.')
            pause=folder/'pause.request'
            pause.unlink(missing_ok=True)
            command=[sys.executable,str(ROOT/'00_WORKFLOW_RUNNER.py'),'--config',str(config),'--output-dir',str(folder/'runs'),'--pause-file',str(pause)]
            if resume: command.extend(['--resume',str(manifests[0].parent)])
            env={k:v for k,v in os.environ.items() if k not in ('OLLAMA_API_KEY','OLLAMA_HOST','WORKFLOW_CHECKPOINT_DIR','WORKFLOW_FINGERPRINT','WORKFLOW_RUN_ID')}
            env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',MPLBACKEND='Agg')
            log=open(folder/'console.log','ab')
            try:
                process=subprocess.Popen(command,cwd=str(ROOT),env=env,stdout=log,stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            finally:
                log.close()
            job.update(status='running',pid=process.pid,modules=checked['modules'],error='')
            atomic_json(folder/'job.json',job)
            self.active=jid
            threading.Thread(target=self.monitor,args=(folder,process,len(checked['modules'])),daemon=True).start()
            return {'id':jid,'status':'running'}

    def monitor(self, folder, process, total):
        last_count=0
        try:
            self.telegram.send('start')
            while process.poll() is None:
                manifests=list((folder/'runs').glob('*/workflow_manifest.json'))
                if manifests:
                    count=len(read_json(manifests[0]).get('completed_steps',[]))
                    if count>last_count:
                        self.telegram.send('progress',count,total)
                        last_count=count
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
    def log_message(self,*args): pass

    def send_bytes(self,data,content_type,status=200,attachment=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        # Allow only the exact bundled review script/style in sandboxed blob previews.
        template=(ROOT/'review_template.html').read_text(encoding='utf-8')
        hashes={tag:' '.join("'sha256-"+base64.b64encode(hashlib.sha256(part.encode()).digest()).decode()+"'" for part in re.findall('<'+tag+'>(.*?)</'+tag+'>',template,re.S)) for tag in ('script','style')}
        self.send_header('Content-Security-Policy',f"default-src 'none'; script-src 'self' {hashes['script']}; style-src 'self' {hashes['style']}; connect-src 'self'; img-src 'self' blob:; frame-src blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
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
        assets={'/':'local_app.html','/app.js':'local_app.js','/app.css':'local_app.css'}
        if not self.allowed(auth=parsed.path not in assets): return self.json({'error':'Zugriff abgelehnt. Oberfläche über die Startdatei öffnen.'},403)
        try:
            if parsed.path in assets:
                p=ROOT/assets[parsed.path]
                return self.send_bytes(p.read_bytes(),{'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}[p.suffix])
            query=urllib.parse.parse_qs(parsed.query)
            get=lambda key:query.get(key,[''])[0]
            app=self.server.app
            if parsed.path=='/api/state':
                cfg=app.template
                return self.json({'projects':app.projects(),'telegram':app.telegram.public(),
                    'defaults':{'llm':{k:cfg['llm'].get(k) for k in ('model','num_ctx','max_tokens','temperature','think')},'context':cfg['context'],'columns':cfg['columns']},
                    'modules':[{'id':m['id'],'name':m['name'],'depends_on':m['depends_on']} for m in RUNNER.normalize_modules(cfg)]})
            if parsed.path=='/api/project': return self.json(app.project(get('project')))
            if parsed.path=='/api/jobs': return self.json({'jobs':app.jobs(get('project')),'telegram':app.telegram.public()})
            if parsed.path=='/api/models': return self.json(app.models())
            if parsed.path=='/api/artifact':
                path=app.artifact(get('project'),get('job'),get('name'))
                if path.stat().st_size>100*1024*1024: raise ValueError('Datei ist für den Browser zu groß. Im lokalen Projektordner öffnen.')
                return self.send_bytes(path.read_bytes(),mimetypes.guess_type(path.name)[0] or 'application/octet-stream',attachment=path.name)
            self.json({'error':'Nicht gefunden.'},404)
        except (ValueError,OSError,KeyError) as exc: self.json({'error':str(exc)},400)

    def do_POST(self):
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
                elif path=='/api/save': result=app.save(data['project'],data['settings'])
                elif path=='/api/start': result=app.start(data['project'],data.get('resume'))
                elif path=='/api/pause': result=app.pause(data['project'],data['job'])
                elif path=='/api/telegram': result=app.telegram.save(data)
                elif path=='/api/telegram-test': result={'sent':app.telegram.send('start',test=True)}
                else: return self.json({'error':'Nicht gefunden.'},404)
            self.json(result)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            self.json({'error':str(exc) if not self.path.startswith('/api/telegram') else
                       (str(exc) if isinstance(exc,ValueError) else 'Telegram-Einstellung konnte nicht gespeichert werden.')},400)


def make_server(app,port=0):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
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
