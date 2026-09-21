"""Listen to a recording while completed ASR segments arrive; persist separate edits."""
import argparse
import copy
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import base64
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
import llm_review as review
from workspace_store import ProjectStore, atomic_write
from import_transcript import parse_bytes
from model_updates import ModelUpdates, DEFAULT_MODEL_ROOT, DEFAULT_MODEL
from continuous_review import reading, align
from reading_workflow import ReadingWorkflow, workspace, job_alive
from reading_speakers import SpeakerPanel


class Session:
    def __init__(self, audio, output, packet=None):
        self.audio = audio.resolve(strict=True) if audio else None
        self.output = output.resolve()
        self.lock = threading.RLock()
        self.path = self.output.parent / (self.output.name + '_Korrekturen.json')
        self.audio_hash = self.file_hash(self.audio) if self.audio else 'import_only'
        self.project_store = ProjectStore(self.output.parent / (self.output.name + '_Codierprojekt.json'))
        self.packet=packet
        self.review_store=None
        if packet:
            review.verify_packet(packet)
            initial={'packet_sha256':packet['packet_sha256'],'decisions':[{'id':x['id'],'decision':'pending','changes':{}} for x in packet['answer']['suggestions']]}
            self.review_store=ProjectStore(self.output.parent/(self.output.name+'_LLM_Entscheidungen.json'),validator=lambda d:review.validate_decision_draft(packet,d),initial=initial)
        self.data = {'schema': 1, 'audio_sha256': self.audio_hash, 'revision': 0, 'edits': {}, 'history': []}
        if self.path.exists():
            try:self.data = review.read(self.path)
            except (ValueError,OSError):self.data = review.read(self.path.with_suffix('.backup.json'))
            review.require(self.data.get('audio_sha256') == self.audio_hash, 'Korrekturen gehören zu anderer Audiodatei.')

    @staticmethod
    def file_hash(path):
        import hashlib
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
        return digest.hexdigest()

    def state(self):
        with self.lock:
            run_path = self.output / 'run.json'
            run = review.read(run_path) if run_path.exists() else {'status': 'waiting'}
            worker=getattr(self,'worker',None)
            job={}
            job_path=self.output.parent/(self.output.name+'_UI_Job.json')
            if job_path.exists():
                job=review.read(job_path)
                if job.get('status')=='failed' or (job.get('status')=='started' and job.get('pid') and not job_alive(job)):
                    run={**run,'status':'failed','error':job.get('error','CPU-Prozess wurde beendet. Teilresultate bleiben erhalten; Aufnahme erneut wählen.')}
                elif job.get('status')=='started' and run['status']=='completed':
                    run={**run,'status':'running'}
            if run['status']=='waiting' and worker and worker.poll() is not None:
                run={'status':'failed','error':'Transkriptionsprozess beendet, bevor ein Laufprotokoll erstellt wurde. Modellordner, Eingabedatei und Konsolenprotokoll prüfen.'}
            if run.get('identity'):
                review.require(run['identity']['audio_sha256'] == self.audio_hash, 'Lauf und Aufnahme passen nicht zusammen.')
            if run.get('status') == 'completed':
                document = review.read(self.output / 'transcript.json')
                raw = review.segments(document) if document.get('segments') else []
            else:
                raw = []
                partial = self.output / 'segments.partial.jsonl'
                if partial.exists():
                    for line in partial.read_text(encoding='utf-8').splitlines():
                        try: value = json.loads(line)
                        except json.JSONDecodeError: break  # writer may not have finished last line
                        raw.append(value)
                raw = review.segments({'segments': raw}) if raw else []
            values = []
            for segment in raw:
                binding = review.fingerprint(segment)
                edit = self.data['edits'].get(segment['id'])
                conflict = bool(edit and edit['source_sha256'] != binding)
                values.append({**segment, 'source_sha256': binding, 'edited': bool(edit), 'conflict': conflict,
                    'display_text': edit['text'] if edit else segment['text']})
            return {'status': run['status'], 'segments': values, 'revision': self.data['revision'],
                    'job_phase':job.get('phase'),'speaker_warning':job.get('speaker_warning',''),
                    'error': run.get('error', ''), 'saved_edits': len(self.data['edits']), 'audio_available': self.audio is not None,
                    'workspace_key':str(self.output), 'title': self.audio.name if self.audio else 'Transkriptimport'}

    def edit(self, payload):
        with self.lock:
            state = self.state()
            review.require(payload.get('revision') == self.data['revision'], 'Neuere Änderungen vorhanden. Ansicht aktualisieren.')
            segment = next((s for s in state['segments'] if s['id'] == payload.get('segment_id')), None)
            review.require(segment and payload.get('source_sha256') == segment['source_sha256'], 'Segment wurde inzwischen neu transkribiert. Original erneut prüfen.')
            review.nonempty(payload.get('text'), 'Korrigierter Text', 200000)
            next_data = copy.deepcopy(self.data)
            next_data['edits'][segment['id']] = {'source_sha256': segment['source_sha256'], 'original': segment['text'], 'text': payload['text'], 'at': review.now()}
            next_data['revision'] += 1
            next_data['history'].append({'segment_id': segment['id'], **next_data['edits'][segment['id']]})
            if self.path.exists():
                atomic_write(self.path.with_suffix('.backup.json'), self.data)
            atomic_write(self.path, next_data)
            self.data = next_data
            return self.state()

    def finish(self, reviewer):
        with self.lock:
            state = self.state()
            review.require(state['status'] == 'completed', 'Transkription erst vollständig abschließen lassen.')
            review.require(not any(s['conflict'] for s in state['segments']), 'Konflikte zwischen neuem Rohtext und Korrekturen zuerst prüfen.')
            raw = [{'id':s['id'],'start':s['start'],'end':s['end'],'speaker':s['speaker'],'text':s['display_text']} for s in state['segments']]
            result = review.approve_transcript({'segments': raw}, reviewer)
            result['asr_transcript_sha256'] = self.file_hash(self.output / 'transcript.json')
            result['correction_history'] = copy.deepcopy(self.data['history'])
            target = self.output.parent / (self.output.name + '_Geprueft_' + secrets.token_hex(4) + '.json')
            review.write(target, result)
            return {'filename': target.name, 'transcript': result}


def handler_for(session, token, integration=None):
    def factory(audio,output):
        new=Session(audio,output)
        if integration is not None:
            new.project_store=integration.store
        return new
    workflow = ReadingWorkflow(session, factory)
    if integration is not None:
        workflow.session.project_store=integration.store
        saved=integration.root/'audio_settings.json'
        if saved.exists():
            workflow.model_dir=Path(review.read(saved)['model_dir'])
            workflow.configure(workflow.session)
    session = workflow.session
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, code, body, mime='application/json'):
            if integration is not None and isinstance(body,bytes) and mime.startswith('text/html'):
                config=json.dumps({'token':token,'project':integration.pid,'storage_path':str(integration.app.project_dir(integration.pid)).removeprefix('\\\\?\\')}).replace('<','\\u003c')
                panel='<section id="host-workflow"></section><script>window.HOST_CONFIG='+config+';</script><script src="host_ui.js"></script>'
                body=body.replace(b'</html>',panel.encode()+b'</html>')
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code); self.send_header('Content-Type', mime); self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(data)))
            if integration is not None:
                import hashlib
                scripts=[]
                if mime.startswith('text/html'):
                    scripts=["'sha256-"+base64.b64encode(hashlib.sha256(x.encode()).digest()).decode()+"'" for x in re.findall(r'<script>(.*?)</script>',data.decode('utf-8'),re.S)]
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' "+' '.join(scripts)+"; style-src 'self' 'unsafe-inline'; connect-src 'self'; media-src 'self' blob:; img-src 'self' data: blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(data)
        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
        def do_GET(self):
            if not self.valid_host(): return self.reply(403, {'error':'Host blockiert'})
            with workflow.lock: active = session
            path = urlsplit(self.path).path
            binding = parse_qs(urlsplit(self.path).query).get('workspace', [None])[0]
            if binding is not None and binding != workspace(active): return self.reply(409, {'error':'Andere Aufnahme geöffnet. Lokalen Entwurf sichern und Seite neu laden.'})
            try:
                if integration is not None and path=='/host-state':return self.reply(200,integration.state())
                if integration is not None and path=='/host_ui.js':return self.reply(200,Path(__file__).with_name('host_ui.js').read_bytes(),'text/javascript')
                if path == '/':
                    body = Path(__file__).with_name('reading.html').read_text(encoding='utf-8').replace('__TOKEN__', token)
                    return self.reply(200, body.encode(), 'text/html; charset=utf-8')
                if path == '/reading-state': return self.reply(200, workflow.state())
                if path in ('/speakers','/speaker-state'):
                    with active.lock:
                        if not hasattr(active,'speaker_panel'):active.speaker_panel=SpeakerPanel(active)
                        panel=active.speaker_panel
                        if path=='/speaker-state':return self.reply(200,panel.store.get())
                        config={'token':token,'projectEndpoint':'/speaker-state?workspace='+workspace(active),'finishEndpoint':'/speaker-finish?workspace='+workspace(active),'backupKey':'speaker-integrated-'+workspace(active),'labelsOnly':True}
                        from speaker_review import source_words
                        data={'words':source_words(panel.packet),'turns':panel.packet['turns'],'duration':panel.packet['duration']}
                        body=Path(__file__).with_name('speaker_review.html').read_text(encoding='utf-8').replace('__CONFIG__',json.dumps(config).replace('<','\\u003c')).replace('__SOURCE__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c'))
                        body=body.replace('src="/audio"','src="/audio?workspace='+workspace(active)+'"').replace('<h1>Sprecher und Personen prüfen</h1>','<h1>Sprecher und Personen prüfen</h1><p><a href="/">Zurück zum Lesetext</a> · Textänderungen bleiben in der Lesetextansicht. Hier nur Sprecher/Personen und Wortgrenzen prüfen.</p>')
                        return self.reply(200,body.encode(),'text/html; charset=utf-8')
                if path == '/reading-project':
                    review.require(binding == workspace(active), 'Aufnahmenbindung fehlt.')
                    with active.lock:
                        editor=reading(active);editor.ensure()
                        return self.reply(200, editor.store.get())
                if path == '/segments':
                    body = Path(__file__).with_name('monitor.html').read_text(encoding='utf-8').replace('__TOKEN__', token)
                    return self.reply(200, body.encode(), 'text/html; charset=utf-8')
                if path == '/state': return self.reply(200, active.state())
                if path == '/model-updates':return self.reply(200,active.model_updates.state())
                if path == '/project': return self.reply(200, active.project_store.get())
                if path == '/review-state':
                    if integration is not None:active.review_store=integration.session.review_store
                    review.require(active.review_store is not None,'Kein Vorschlagspaket geöffnet.')
                    return self.reply(200,active.review_store.get())
                if path == '/review':
                    if integration is not None:
                        active.packet=integration.session.packet
                        active.review_store=integration.session.review_store
                    review.require(active.packet is not None,'Beim Start --review-packet angeben.')
                    data=json.dumps(active.packet,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
                    body=Path(__file__).with_name('review_template.html').read_text(encoding='utf-8').replace('__PACKET_JSON__',data)
                    config={'token':token,'projectEndpoint':'/review-state','backupKey':active.packet['packet_sha256']}
                    body=body.replace('<script id="data"','<script>window.WORKSPACE_CONFIG='+json.dumps(config)+';</script><script src="/coding_core.js"></script><script src="/autosave.js"></script><script id="data"',1)
                    return self.reply(200,body.encode(),'text/html; charset=utf-8')
                static = {'/coding': ('Codieren.html', 'text/html; charset=utf-8'),
                          '/coding_core.js': ('coding_core.js','text/javascript'),
                          '/coding_ui.js': ('coding_ui.js','text/javascript'),
                          '/autosave.js': ('autosave.js','text/javascript'),
                          '/monitor_ui.js': ('monitor_ui.js','text/javascript')}
                static['/reading_ui.js'] = ('reading_ui.js', 'text/javascript')
                static['/reading_core.js'] = ('reading_core.js', 'text/javascript')
                static['/reading_people.js'] = ('reading_people.js','text/javascript')
                static['/reading_people_ui.js'] = ('reading_people_ui.js','text/javascript')
                if path in static:
                    name,mime=static[path]
                    body=Path(__file__).with_name(name).read_text(encoding='utf-8')
                    if path=='/coding':body=body.replace('<script src="coding_core.js">', '<script>window.WORKSPACE_CONFIG='+json.dumps({'token':token,'projectEndpoint':'/project','backupKey':active.audio_hash+str(active.output)})+';</script><script src="coding_core.js">')
                    return self.reply(200,body.encode(),mime)
                if path == '/audio':
                    review.require(active.audio is not None,'Keine Aufnahme zugeordnet.')
                    size=active.audio.stat().st_size; start,end=0,size-1; code=200
                    header=self.headers.get('Range')
                    if header:
                        match=re.fullmatch(r'bytes=(\d+)-(\d*)',header)
                        if not match:return self.reply(416,{'error':'Ungültiger Audiobereich'})
                        start=int(match[1]);end=min(int(match[2]) if match[2] else end,end);code=206
                        if not 0<=start<=end<size:return self.reply(416,{'error':'Ungültiger Audiobereich'})
                    self.send_response(code);self.send_header('Content-Type',mimetypes.guess_type(active.audio.name)[0] or 'application/octet-stream')
                    self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1));self.send_header('Cache-Control','no-store')
                    if code==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    with active.audio.open('rb') as stream:
                        stream.seek(start); remaining=end-start+1
                        while remaining:
                            data=stream.read(min(65536,remaining))
                            if not data:break
                            self.wfile.write(data);remaining-=len(data)
                    return
                self.reply(404,{'error':'Nicht gefunden'})
            except (BrokenPipeError,ConnectionResetError): pass
            except Exception as exc: self.reply(400,{'error':str(exc)[:400]})
        def do_POST(self):
            nonlocal session, token
            def denied(message):
                # Windows can reset a closed socket with unread request bytes,
                # hiding the explicit rejection. Drain only tiny bounded JSON
                # requests, never an unauthenticated audio upload.
                self.close_connection=True
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if 0<length<=4096 and not self.headers.get('Transfer-Encoding'):
                        old_timeout=self.connection.gettimeout()
                        try:self.connection.settimeout(.5);self.rfile.read(length)
                        finally:self.connection.settimeout(old_timeout)
                except (ValueError,OSError):pass
                return self.reply(403,{'error':message})
            if not self.valid_host() or self.headers.get('X-Review-Token')!=token:return denied('Zugriff blockiert')
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':return denied('Origin blockiert')
            try:
                if self.path == '/next-audio':
                    result=workflow.upload(self)
                    with workflow.lock:
                        session=workflow.session
                        token=secrets.token_urlsafe(32)
                    return self.reply(200,result)
                length=int(self.headers.get('Content-Length','0'));review.require(0<length<=30*1024*1024,'Anfrage zu groß/leer.')
                body=json.loads(self.rfile.read(length))
                route=urlsplit(self.path).path
                if integration is not None and route=='/next-local-audio':
                    result=workflow.upload_local(self,body)
                    with workflow.lock:
                        session=workflow.session
                        token=secrets.token_urlsafe(32)
                    return self.reply(200,result)
                if integration is not None and route.startswith('/host-'):return self.reply(200,integration.action(route,body,session))
                if route in ('/speaker-state','/speaker-finish'):
                    with workflow.lock, session.lock:
                        binding=parse_qs(urlsplit(self.path).query).get('workspace',[None])[0]
                        review.require(binding==workspace(session),'Andere Aufnahme geöffnet.')
                        if not hasattr(session,'speaker_panel'):session.speaker_panel=SpeakerPanel(session)
                        panel=session.speaker_panel
                        if route=='/speaker-state':return self.reply(200,panel.store.save(body['project'],body['revision'],body['mutation_id']))
                        return self.reply(200,panel.approve(body))
                if route in ('/reading-project','/reading-edit','/reading-finish','/reading-align'):
                    with workflow.lock, session.lock:
                        binding=parse_qs(urlsplit(self.path).query).get('workspace',[None])[0]
                        review.require(binding==workspace(session),'Andere Aufnahme geöffnet; Entwurf sichern und neu laden.')
                        editor=reading(session);editor.ensure()
                        if route=='/reading-finish':
                            result=editor.finish(body)
                            if integration is not None:integration.adopt_finished(result)
                            return self.reply(200,result)
                        if route=='/reading-align':
                            review.require(isinstance(body.get('text'),str) and len(body['text'])<=2000000,'Transkript ist kein gültiger Text.')
                            return self.reply(200,{'words':editor.words({**editor.store.get()['project'],'text':body['text']})})
                        return self.reply(200,editor.save(body))
                if self.path=='/model-updates/check':return self.reply(200,session.model_updates.check(manual=body.get('manual') is True))
                if self.path=='/model-updates/preference':return self.reply(200,session.model_updates.preference(body.get('automatic')))
                if self.path=='/edit':return self.reply(200,session.edit(body))
                if self.path=='/finish':return self.reply(200,session.finish(body.get('reviewer')))
                if self.path=='/project':return self.reply(200,session.project_store.save(body['project'],body['revision'],body['mutation_id']))
                if self.path=='/review-state':
                    if integration is not None:session.review_store=integration.session.review_store
                    review.require(session.review_store is not None,'Kein Vorschlagspaket geöffnet.')
                    return self.reply(200,session.review_store.save(body['project'],body['revision'],body['mutation_id']))
                if self.path=='/import':
                    preview=parse_bytes(body['filename'],base64.b64decode(body['data'],validate=True),body.get('encoding'))
                    return self.reply(200,preview)
                if self.path=='/confirm-import':
                    confirmed=review.approve_transcript(body['transcript'],body['reviewer'])
                    confirmed['import_source']= {k:body['transcript'].get(k) for k in ('source_name','source_sha256','source_format','warnings')}
                    target=session.output.parent/('Import_Geprueft_'+secrets.token_hex(4)+'.json')
                    review.write(target,confirmed)
                    return self.reply(200,{'filename':target.name,'transcript':confirmed})
                self.reply(404,{'error':'Nicht gefunden'})
            except Exception as exc:self.reply(400,{'error':str(exc)[:400]})
    Handler.integration_workflow=workflow
    return Handler


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audio',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model-dir',type=Path,default=DEFAULT_MODEL_ROOT/DEFAULT_MODEL);p.add_argument('--start-cpu',action='store_true');p.add_argument('--port',type=int,default=0)
    p.add_argument('--review-packet',type=Path)
    p.add_argument('--speaker-result',type=Path);p.add_argument('--speaker-model-dir',type=Path)
    p.add_argument('--expected-speakers',type=int)
    a=p.parse_args();child=None
    review.require(a.expected_speakers is None or 1<=a.expected_speakers<=100,'Erwartete Sprecherzahl: 1 bis 100 oder weglassen.')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.expected_speakers is not None:
        meta=a.output.parent/(a.output.name+'_Aufnahme.json')
        details=review.read(meta) if meta.exists() else {}
        details.update(expected_speakers=a.expected_speakers,speaker_count_usage='plausibility_only_not_model_parameter')
        atomic_write(meta,details)
    if a.start_cpu:
        review.require(a.audio and a.model_dir and not a.output.exists(),'CPU-Start braucht Audio, Modellordner und einen neuen Ausgabeordner.')
        review.require(a.audio.is_file() and (a.model_dir/'model_manifest.json').is_file(),'Audio/Modellmanifest fehlt. Pfade prüfen und Modell zuerst herunterladen.')
        command=[sys.executable,str(Path(__file__).with_name('transcription_pipeline.py')),'--audio',str(a.audio),'--model-dir',str(a.model_dir),'--output',str(a.output),'--speaker-model-dir',str(a.speaker_model_dir or a.model_dir.parent/'sortformer-v2-onnx')]
        child=subprocess.Popen(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    session=Session(a.audio,a.output,review.read(a.review_packet) if a.review_packet else None)
    session.model_dir = a.model_dir.resolve()
    session.speaker_model_dir=(a.speaker_model_dir or a.model_dir.parent/'sortformer-v2-onnx').resolve()
    session.speaker_result=a.speaker_result
    session.expected_speakers=a.expected_speakers
    session.model_updates=ModelUpdates(a.model_dir.parent,a.output.parent/(a.output.name+'_Modellpruefung.json'))
    session.worker=child
    server=ThreadingHTTPServer(('127.0.0.1',a.port),handler_for(session,secrets.token_urlsafe(32)))
    print(f'http://127.0.0.1:{server.server_port}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close()
        # A separate CPU child is allowed to finish; closing this viewer never deletes its outputs.
        if child and child.poll() is None:print('CPU-Transkription läuft separat weiter; Korrekturen sind gespeichert.',flush=True)


if __name__=='__main__':main()
