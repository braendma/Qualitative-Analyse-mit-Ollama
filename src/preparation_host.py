"""Private v8 preparation, sharing the host's project, privacy and credential services."""
import base64
import copy
import csv
import io
import json
import re
from pathlib import Path
import secrets
import sys
import threading
from urllib.parse import urlsplit

PREP = Path(__file__).with_name('preparation')
if str(PREP) not in sys.path:
    sys.path.append(str(PREP))
import llm_review as review
from workspace_store import ProjectStore, validate_project, atomic_write
from transcription_monitor import Session, handler_for
from model_updates import DEFAULT_MODEL_ROOT, DEFAULT_MODEL, ModelUpdates
from model_selection import saved_default, selection_state, validate_model, remember_default


def exports(project):
    """Server-side equivalent of Coding.exportsFor; quotes are exact source slices."""
    validate_project(project)
    cats = {c['id']: c for c in project['categories']}
    docs = {d['id']: d for d in project['documents']}
    rows = [['segment_id','PassageID','Dokumentname','Code','Segment','Quelldokument','PersonID','Zeitbeginn','Zeitende','Zeichenbeginn','Zeichenende','Herkunft','Memo']]
    anchors = {c: [] for c in cats}
    for a in project['annotations']:
        d = docs[a['document_id']]
        s = next(s for s in d['segments'] if s['id'] == a['segment_id'])
        if s['exclude']:
            continue
        review.nonempty(s['person'], 'Personenzuordnung', 200)
        passage = 'PASS-' + json.dumps([d['id'],s['id'],a['start'],a['end']],ensure_ascii=False,separators=(',',':'))
        rows.append([a['id'],passage,s['person'],cats[a['category_id']]['code'],a['quote'],d['title'],s['person'],s['start'],s['end'],a['start'],a['end'],a['origin'],a['memo']])
        anchors[a['category_id']].append(a['quote'])
    review.require(cats and len(rows)>1, 'Mindestens eine Kategorie und eine nicht ausgeschlossene Codierung erforderlich.')
    book = [['Code','Definition','Einschluss','Ausschluss','Ankerbeispiele']]
    for c in cats.values():
        book.append([c['code'],c['definition'],c['inclusion'],c['exclusion'],c['anchors'] or '\n'.join(dict.fromkeys(anchors[c['id']]))])
    def encode(values):
        out=io.StringIO(newline='');writer=csv.writer(out,delimiter=';',quoting=csv.QUOTE_ALL)
        writer.writerows(values)
        return ('\ufeff'+out.getvalue()).encode('utf-8')
    return encode(rows),encode(book),len(rows)-1


class Preparation:
    def __init__(self, app, pid):
        self.app,self.pid=app,pid
        if not hasattr(app,'audio_models'):
            from audio_models import AudioModels
            app.audio_models=AudioModels(DEFAULT_MODEL_ROOT)
        self.root=app.project_dir(pid)/'preparation'
        self.root.mkdir(exist_ok=True)
        self.lock=threading.RLock()
        self.running=False
        self.job={'status':'idle'}
        self.store=ProjectStore(self.root/'Codierprojekt.json')
        self.session=Session(None,self.root/'Import')
        self.session.project_store=self.store
        self.audio_defaults=app.directory/'audio_defaults.json'
        self.session.model_dir=saved_default(self.audio_defaults,DEFAULT_MODEL_ROOT/DEFAULT_MODEL)
        self.session.speaker_model_dir=DEFAULT_MODEL_ROOT/'sortformer-v2-onnx'
        self.session.model_updates=ModelUpdates(self.session.model_dir.parent,self.root/'Modellpruefung.json')
        pointer=self.root/'last_suggestion.json'
        if pointer.exists():
            self.bind_packet(review.read(pointer))
            self.job={'status':'applied' if self.packet_info.get('applied') else 'awaiting_human_review'}
        job_pointer=self.root/'last_job.json'
        if job_pointer.exists():
            jid=review.read(job_pointer).get('id')
            review.require(isinstance(jid,str) and re.fullmatch('[0-9a-f]{20}',jid),'Ungültige gespeicherte Auftragsreferenz.')
            status_path=self.root/'suggestions'/jid/'status.json'
            self.job=review.read(status_path)
            if self.job.get('status')=='running':
                self.job={**self.job,'status':'interrupted','error':'Vorheriger Vorschlagsauftrag wurde nicht abgeschlossen. Gespeicherte Eingaben und vorhandene Rohantwort bleiben erhalten; keine automatische Wiederholung.'}
                atomic_write(status_path,self.job)
            if self.job.get('status')=='awaiting_human_review' and getattr(self,'packet_info',{}).get('applied'):
                self.job={**self.job,'status':'applied'}
        self.handler=handler_for(self.session,secrets.token_urlsafe(32),integration=self)

    def bind_packet(self, saved):
        packet=saved['packet'];review.verify_packet(packet)
        self.packet_info=saved
        self.session.packet=packet
        self.session.review_store=ProjectStore(self.root/('Decisions_'+packet['packet_sha256']+'.json'),
            validator=lambda p:review.validate_decision_draft(packet,p),
            initial={'packet_sha256':packet['packet_sha256'],'decisions':[{'id':x['id'],'decision':'pending','changes':{}} for x in packet['answer']['suggestions']]})

    def adopt_finished(self, result):
        """A reviewed recording adds a new version; it never replaces coded text."""
        with self.lock:
            state=self.store.get();project=copy.deepcopy(state['project'])
            for doc in result['project']['documents']:
                if not any(d['transcript_sha256']==doc['transcript_sha256'] for d in project['documents']):
                    project['documents'].append(copy.deepcopy(doc))
            project['history'].extend(result['project']['history'])
            self.store.save(project,state['revision'],secrets.token_hex(12))

    def state(self):
        state=self.store.get()
        saved=self.app.project(self.pid)['settings']
        return {'revision':state['revision'],'project_sha256':review.fingerprint(state['project']),
            'documents':[{'id':d['id'],'title':d['title']} for d in state['project']['documents']],
            'job':self.job,'provider':saved.get('provider','ollama_local'),'model':saved.get('model','granite4.2:8b'),
            'gdpr_relevant':saved.get('gdpr_relevant',True),'review_available':hasattr(self,'packet_info'),
            'last_handoff':review.read(self.root/'last_handoff.json') if (self.root/'last_handoff.json').exists() else None}

    def action(self, route, body, active):
        with self.lock:
            if route=='/host-model-state':
                known=[DEFAULT_MODEL_ROOT/'large-v3',DEFAULT_MODEL_ROOT/'small']
                for config in (p for root in self.app.project_roots for p in root.glob('*/preparation/audio_settings.json')):
                    try:
                        path=review.read(config).get('model_dir')
                        if isinstance(path,str):known.append(path)
                    except (OSError,ValueError,AttributeError):pass
                return {**selection_state(self.handler.integration_workflow.model_dir,self.audio_defaults,known),
                        'library':self.app.audio_models.state()}
            if route=='/host-model-install':
                callback=(lambda path:remember_default(self.audio_defaults,path)) if body.get('remember') is True and body.get('model')!='sortformer-v2-onnx' else None
                return self.app.audio_models.start(body.get('model'),body.get('confirmed') is True,body.get('source') or None,callback)
            if route=='/host-model-install-stop':return self.app.audio_models.stop()
            if route=='/host-model-browse':
                from local_file_browser import browse
                return browse(body.get('path',''),'directory')
            if route=='/host-audio-browse':
                from local_file_browser import browse
                return browse(body.get('path',''), 'audio')
            if route=='/host-state':return self.state()
            if route=='/host-suggest':return self.suggest(body)
            if route=='/host-approve':return self.approve(body)
            if route=='/host-handoff':return self.handoff(body)
            if route=='/host-provider':
                from llm_providers import selection
                from provider_keys import reject_secret_settings
                review.require(not self.running,'Verbindungseinstellungen nach Abschluss des laufenden Vorschlagsauftrags ändern.')
                settings=copy.deepcopy(self.app.project(self.pid)['settings'])
                supplied={k:body[k] for k in ('provider','model','gdpr_relevant') if k in body}
                selected=selection(supplied)
                review.require(selected['provider'] in ('ollama_local','ollama_cloud'),'Ollama lokal oder Cloud wählen.')
                settings.update(supplied)
                reject_secret_settings(settings)
                if selected['provider']=='ollama_cloud' and body.get('key'):
                    self.app.provider_keys.save('ollama_cloud',body['key'],persist=body.get('persist') is True)
                atomic_write(self.app.project_dir(self.pid)/'settings.json',settings)
                return {'provider':selected['provider'],'model':selected['model']}
            if route=='/host-stop-audio':
                worker=getattr(active,'worker',None)
                job_path=active.output.parent/(active.output.name+'_UI_Job.json')
                job=review.read(job_path) if job_path.exists() else {}
                review.require((worker is not None and worker.poll() is None) or job.get('status')=='started','Kein aktiver Audioprozess für diese Aufnahme.')
                (active.output.parent/(active.output.name+'_stop.request')).write_text('explicit user stop\n',encoding='utf-8')
                return {'stop_requested':True,'message':'Beenden angefordert. Auf den Abschluss der eigenen Prozessaufsicht warten.'}
            if route=='/host-model-folder':
                review.require(not getattr(active,'worker',None) or active.worker.poll() is not None,'Aktuelle Transkription zuerst beenden.')
                workflow=self.handler.integration_workflow
                from reading_workflow import job_alive
                with workflow.lock:
                    review.require(not workflow.uploading,'Dateiübertragung zuerst abschließen.')
                    job_path=active.output.parent/(active.output.name+'_UI_Job.json')
                    job=review.read(job_path) if job_path.exists() else {}
                    review.require(not(job.get('status')=='started' and job_alive(job)),'Aktuelle Transkription zuerst beenden.')
                    path=validate_model(body.get('path',''),verify_hashes=True)
                    if body.get('remember') is True:remember_default(self.audio_defaults,path)
                    atomic_write(self.root/'audio_settings.json',{'model_dir':str(path)})
                    workflow.model_dir=path
                    workflow.configure(active)
                return {'model':path.name,'path':str(path),'remembered':body.get('remember') is True}
            raise ValueError('Unbekannte Vorbereitungsaktion.')

    def suggest(self, body):
        review.require(not self.running,'Ein Vorschlagsauftrag läuft bereits.')
        review.require(not hasattr(self,'packet_info') or self.packet_info.get('applied') is True,'Aktuelle Vorschläge zuerst vollständig prüfen und übernehmen oder ablehnen.')
        state=self.store.get();review.require(body.get('revision')==state['revision'],'Codierprojekt geändert. Neu laden.')
        doc=next((d for d in state['project']['documents'] if d['id']==body.get('document_id')),None)
        review.require(doc is not None,'Ein bestätigtes Dokument auswählen.')
        review.nonempty(body.get('reviewer'),'Prüfende Person',120)
        transcript=review.approve_transcript({'segments':doc['segments']},body['reviewer'])
        # The source document remains the identity used by reviewed coding import.
        mode=body.get('mode','coding')
        review.require(mode in ('coding','categories'),'Kategorien oder Codierung auswählen.')
        book=None
        if mode=='coding':
            review.require(body.get('categories_confirmed') is True,'Kategorien vor der Vorschlagsanfrage ausdrücklich prüfen.')
            categories=[{k:c[k] for k in ('id','code','definition','inclusion','exclusion')} for c in state['project']['categories']]
            book={'kind':'approved_categories','manual':True,'categories':categories,'review':{'confirmed':True,'categories_sha256':review.fingerprint(categories)}}
        settings=copy.deepcopy(self.app.project(self.pid)['settings'])
        from llm_providers import selection
        selected=selection({'model':settings.get('model','granite4.2:8b'),**settings})
        review.require(selected['provider'] in ('ollama_local','ollama_cloud'),'Für diese Vorbereitung Ollama lokal oder Ollama Cloud wählen.')
        if selected['provider']=='ollama_cloud':
            review.require(body.get('cloud_confirmed') is True,'Übertragung dieses Transkripts und Kategoriensystems an Ollama Cloud ausdrücklich bestätigen.')
        task=review.prepare(transcript,mode,model=selected['model'].replace('-cloud',''),book=book,context=int(settings.get('num_ctx',32768)),limit=int(settings.get('max_tokens',4096)))
        task['request']['model']=selected['model']
        task['task_sha256']=review.fingerprint({k:v for k,v in task.items() if k!='task_sha256'})
        jid=secrets.token_hex(10);folder=self.root/'suggestions'/jid;folder.mkdir(parents=True)
        review.write(folder/'task.json',task)
        binding={'document_id':doc['id'],'document_sha256':review.fingerprint(doc),'source_transcript_sha256':doc['transcript_sha256'],'project_sha256':review.fingerprint(state['project'])}
        self.running=True;self.job={'id':jid,'status':'running','provider':selected['provider'],'model':selected['model']}
        atomic_write(folder/'status.json',self.job)
        atomic_write(self.root/'last_job.json',{'id':jid})
        key=self.app.provider_keys.keys.get(selected['provider'])
        def work():
            try:
                import ollama
                from llm_client import request_chat
                with self.app.lock:
                    self.app.authorize_llm(self.pid,selected,installed=False)
                if selected['provider']=='ollama_local':
                    local=ollama.Client(host=selected['host'],timeout=15)
                    listed=local.list();listed=listed.model_dump() if hasattr(listed,'model_dump') else listed
                    matches=[x for x in listed.get('models',[]) if (x.get('model') or x.get('name')) in (selected['model'],selected['model']+':latest')]
                    review.require(len(matches)==1,'Lokales Modell nicht eindeutig installiert. Kein automatischer Download.')
                    shown=local.show(selected['model']);shown=shown.model_dump() if hasattr(shown,'model_dump') else shown
                    review.require(not any(x.get('remote_host') or x.get('remote_model') for x in (matches[0],shown)),'Remote-Modell im lokalen Weg gesperrt.')
                request=copy.deepcopy(task['request'])
                response=request_chat(ollama,request,{**settings,**selected,'response_schema':task['request']['format'],'max_attempts':1,'num_ctx':task['request']['options']['num_ctx']},api_key=key)
                raw=response.model_dump() if hasattr(response,'model_dump') else response
                review.write(folder/'response.json',raw)
                review.require(raw.get('done') is True and raw.get('done_reason')=='stop','Antwort unvollständig. Keine Vorschläge freigegeben.')
                review.require(not raw.get('message',{}).get('tool_calls'),'Unerwartete Werkzeuganweisung.')
                answer=review.validate_suggestions(task,review.parse_answer(raw['message']['content']))
                packet={'kind':'review_packet','task':task,'answer':answer,'generation':selected['provider'],'response_sha256':review.fingerprint(raw)}
                packet['packet_sha256']=review.fingerprint(packet)
                review.write(folder/'suggestions.json',packet)
                with self.lock:
                    saved={'packet':packet,'binding':binding}
                    atomic_write(self.root/'last_suggestion.json',saved);self.bind_packet(saved)
                    self.job={**self.job,'status':'awaiting_human_review','count':len(answer['suggestions'])}
            except Exception as exc:
                with self.lock:self.job={**self.job,'status':'failed','error':str(exc)[:600]}
            finally:
                with self.lock:
                    atomic_write(folder/'status.json',self.job);self.running=False
        threading.Thread(target=work,daemon=True).start()
        return self.job

    def approve(self, body):
        review.require(hasattr(self,'packet_info'),'Kein Vorschlagspaket vorhanden.')
        state=self.store.get();review.require(body.get('revision')==state['revision'],'Projekt wurde geändert. Neu laden.')
        info=self.packet_info;packet=info['packet'];binding=info['binding']
        review.require(info.get('applied') is not True,'Dieses Vorschlagspaket wurde bereits abgeschlossen.')
        next_project=copy.deepcopy(state['project'])
        doc=next((d for d in next_project['documents'] if d['id']==binding['document_id']),None)
        review.require(doc is not None and review.fingerprint(doc)==binding['document_sha256'],'Quelldokument geändert. Keine automatische Übernahme.')
        decisions=self.session.review_store.get()
        review.require(body.get('decisions_revision')==decisions['revision'],'Entscheidungen geändert. Neu laden.')
        result=review.finalize(packet,decisions,body.get('reviewer'))
        if packet['task']['mode']=='categories':
            for c in result['categories']:
                review.require(not any(x['id']==c['id'] or x['code'].casefold()==c['code'].casefold() for x in next_project['categories']),'Kategorie bereits vorhanden. Bestehende Zuordnungen zuerst prüfen.')
                next_project['categories'].append({k:c[k] for k in ('id','code','definition','inclusion','exclusion')}|{'anchors':'\n'.join(e['quote'] for e in c['evidence'])})
        else:
            review.require(review.fingerprint(state['project'])==binding['project_sha256'],'Codierprojekt seit Anfrage geändert. Vorschläge nicht automatisch einfügen.')
            for item in result['coding']:
                for evidence in item['evidence']:
                    s=next(s for s in doc['segments'] if s['id']==evidence['segment_id']);quote=evidence['quote'];start=s['text'].find(quote)
                    review.require(start>=0 and s['text'].find(quote,start+1)<0,'Beleg nicht eindeutig. Bitte manuell codieren.')
                    next_project['annotations'].append({'id':secrets.token_hex(12),'document_id':doc['id'],'segment_id':s['id'],'start':start,'end':start+len(quote),'quote':quote,'category_id':item['category_id'],'origin':'llm_reviewed','memo':item['reason']})
        next_project['history'].append({'at':review.now(),'action':'Menschlich geprüfte LLM-Vorschläge übernommen','packet_sha256':packet['packet_sha256'],'reviewer':body.get('reviewer')})
        validate_project(next_project)
        target=self.root/('Approved_'+secrets.token_hex(8)+'.json');review.write(target,result)
        saved=self.store.save(next_project,state['revision'],secrets.token_hex(12))
        self.packet_info={**self.packet_info,'applied':True,'applied_revision':saved['revision']}
        atomic_write(self.root/'last_suggestion.json',self.packet_info)
        self.job={**self.job,'status':'applied'}
        if self.job.get('id'):
            atomic_write(self.root/'suggestions'/self.job['id']/'status.json',self.job)
        return {'revision':saved['revision'],'approved':True}

    def handoff(self, body):
        state=self.store.get()
        review.require(body.get('revision')==state['revision'] and body.get('project_sha256')==review.fingerprint(state['project']),'Vorbereitung wurde geändert. Neuen Stand erneut prüfen.')
        review.require(body.get('confirmed') is True,'Transkript, Personen, Kategorien und Codierungen ausdrücklich bestätigen.')
        review.nonempty(body.get('reviewer'),'Prüfende Person',120)
        review.require(not self.running,'Vorschlagsauftrag zuerst abschließen.')
        review.require(not hasattr(self,'packet_info') or self.packet_info.get('applied') is True,'Offene LLM-Vorschläge zuerst einzeln prüfen und Übernahme abschließen; Ablehnen ist möglich.')
        segments,book,count=exports(state['project'])
        folder=self.root/'handoffs'/secrets.token_hex(10);folder.mkdir(parents=True)
        review.write(folder/'project.json',state)
        (folder/'segments.csv').write_bytes(segments);(folder/'codebook.csv').write_bytes(book)
        receipt={'at':review.now(),'reviewer':body['reviewer'],'confirmed':True,'source_revision':state['revision'],'project_sha256':review.fingerprint(state['project']),'rows':count,'snapshot':folder.name}
        review.write(folder/'approval.json',receipt)
        # Host imports preserve each previous input and each completed analysis.
        with self.app.lock:
            self.app.upload(self.pid,'segments','Vorbereitung.csv',base64.b64encode(segments).decode())
            self.app.upload(self.pid,'codebook','Kategoriesystem.csv',base64.b64encode(book).decode())
            settings=self.app.project(self.pid)['settings']
            columns={'segment':'Segment','person':'Dokumentname','code':'Code','segment_id':'segment_id','unit_id':'PassageID'}
            from person_identity import preview
            people=preview(segments,columns)
            settings.update(columns=columns,book_columns={'code':'Code','definition':'Definition','einschluss':'Einschluss','ausschluss':'Ausschluss','ankerbeispiel':'Ankerbeispiele'},label_mode='multi_label',
                person_identity={'confirmed':True,'fingerprint':people['fingerprint'],'mapping':{d['document']:d['document'] for d in people['documents']}},output_dir_mode='explicit')
            # Persist pending mapping even when a later context preflight rejects settings.
            atomic_write(self.app.project_dir(self.pid)/'settings.json',settings)
            checked=self.app.save(self.pid,settings)
            receipt['analysis_revision']=self.app.project(self.pid)['revision']
            receipt['validation']=checked
            atomic_write(folder/'analysis_handoff.json',receipt)
            atomic_write(self.root/'last_handoff.json',receipt)
        if body.get('start_analysis') is True:
            result=self.app.start(self.pid)
            atomic_write(folder/'started_job.json',result)
            return {'handoff':receipt,'job':result}
        return {'handoff':receipt}


def dispatch(handler):
    path=urlsplit(handler.path).path
    if not path.startswith('/preparation/'):
        return False
    if not handler.allowed(auth=False):
        handler.json({'error':'Zugriff abgelehnt'},403);return True
    parts=path.split('/')
    try:
        pid=parts[2];app=handler.server.app
        with app.lock:
            if not hasattr(app,'preparations'):app.preparations={}
            if pid not in app.preparations:app.preparations[pid]=Preparation(app,pid)
            service=app.preparations[pid]
        prefix='/preparation/'+pid
        handler.path=handler.path[len(prefix):] or '/'
        base=service.handler
        class Bound(base):
            protocol_version="HTTP/1.1"
            def reply(self,code,body,mime='application/json'):
                if isinstance(body,bytes) and (mime.startswith('text/html') or mime.startswith('text/javascript')):
                    value=body.decode('utf-8').replace("'/", "'"+prefix+'/').replace('"/', '"'+prefix+'/')
                    if mime.startswith('text/html'):
                        value=value.replace('</html>','<link rel="stylesheet" href="/workflow-nav.css"><script src="/workflow-nav.js" defer></script><script src="/model-setup.js" defer></script></html>')
                    body=value.encode('utf-8')
                return super().reply(code,body,mime)
        original=handler.__class__;handler.__class__=Bound
        try:
            if handler.command=='GET':handler.do_GET()
            else:handler.do_POST()
        finally:handler.__class__=original
    except Exception as exc:
        handler.json({'error':str(exc)[:500]},400)
    return True


def require_idle(app):
    """A normal host shutdown must not silently abandon preparation work."""
    if hasattr(app,'audio_models'):
        review.require(not app.audio_models.busy,'Eine Modellinstallation läuft. Im Modelldialog abbrechen oder Abschluss abwarten.')
    for service in getattr(app,'preparations',{}).values():
        review.require(not service.running,'Ein Vorschlagsauftrag läuft. Abschluss abwarten, bevor das Programm beendet wird.')
        active=service.handler.integration_workflow.session
        worker=getattr(active,'worker',None)
        review.require(worker is None or worker.poll() is not None,'Eine Audioerkennung läuft. Im Vorbereitungsbereich beenden und Abschluss abwarten.')
    from reading_workflow import job_alive
    for path in (p for root in app.project_roots for p in root.glob('*/preparation/**/*_UI_Job.json')):
        job=review.read(path)
        review.require(not (job.get('status')=='started' and job_alive(job)),'Eine Audioerkennung ist noch aktiv. Zugehöriges Projekt öffnen und im Vorbereitungsbereich beenden.')
