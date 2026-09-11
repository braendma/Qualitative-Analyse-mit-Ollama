'use strict';
const $ = id => document.getElementById(id);
const tokenKey = 'qualitative-session-' + location.port;
const token = location.hash.slice(1) || sessionStorage.getItem(tokenKey) || '';
if (location.hash) { sessionStorage.setItem(tokenKey, token); history.replaceState(null, '', '/'); }
let state, project, jobs = [], viewing = 'project', objectUrl = null, polling = false, projectRequest = 0, artifactRequest = 0;
const names = {project:'Projekt & Dateien',check:'Eingaben prüfen',analysis:'Analyse',results:'Ergebnisse',telegram:'Telegram-Updates'};
const moduleHelp = {
  clusterer:'Gruppiert Textstellen innerhalb eines Codepfads zu inhaltlichen Clustern.',
  code_verification:'Prüft, wie gut die menschlich vergebenen Codes zu den Textstellen passen.',
  blind_coding:'Vergibt Codes anhand des Kategoriensystems, ohne die menschlichen Zuordnungen als Vorgabe zu erhalten.',
  coding_agreement:'Vergleicht menschliche und modellbasierte Zuordnungen und berichtet Übereinstimmungen und Abweichungen.',
  summarizer:'Fasst die Inhalte der gebildeten Cluster zusammen.',
  swot:'Ordnet Befunde als Stärken, Schwächen, Chancen oder Risiken ein.',
  meta_swot:'Verdichtet die SWOT-Einzelbefunde zu übergreifenden Themen.',
  person_analysis:'Fasst Themen und Perspektiven für jede befragte Person zusammen.',
  person_comparison:'Vergleicht Personen hinsichtlich gemeinsamer Muster, Unterschiede und möglicher Typen.',
  contrast_analysis:'Sucht abweichende Fälle, die übergreifende Muster einschränken.',
  relation_analysis:'Untersucht mögliche Zusammenhänge zwischen Codepfaden anhand von Textbelegen.',
  ambiguity_analysis:'Untersucht gegenläufige Aussagen und Ambivalenzen innerhalb der einzelnen Personenanalysen.',
  evidence_audit:'Prüft ausgewählte Befunde auf Gegenbelege aus den vorherigen Analysen.',
  review_queue:'Erstellt die interaktive Liste zur manuellen Prüfung von Codierungen und Modellvorschlägen.',
  overall_synthesis:'Führt die vorherigen Analyseergebnisse zu einer Gesamtsynthese zusammen.'
};
function updateModuleSelection(){
  const selected=new Set([...document.querySelectorAll('[name=module]:checked')].map(n=>n.value));
  const required=new Set(selected);
  let changed=true;
  while(changed){changed=false;state.modules.forEach(m=>{if(required.has(m.id))m.depends_on.forEach(id=>{if(!required.has(id)){required.add(id);changed=true;}});});}
  const added=state.modules.filter(m=>required.has(m.id)&&!selected.has(m.id)).map(m=>m.name);
  $('module-selection').textContent=selected.size?`${selected.size} ${selected.size===1?"Modul":"Module"} ausgewählt · ${required.size} ${required.size===1?"Modul wird":"Module werden"} ausgeführt.`+(added.length?' Automatisch benötigte Vorstufen: '+added.join(', ')+'.':' Keine zusätzlichen Vorstufen erforderlich.'):'Noch kein Modul ausgewählt. Setze mindestens ein Häkchen.';
}
const columnLabels = {segment:'Text / Segment *',person:'Person / Dokument *',code:'Vergebener Code *',segment_id:'Eindeutige Zeilen-ID (optional)',unit_id:'Passage-ID (für Mehrfachcodierung)'};
function bookDescription(c){return 'Definition: '+c.definition+' · Einschluss: '+(c.einschluss||'—')+' · Ausschluss: '+(c.ausschluss||'—')+' · Abgrenzung: '+(c.abgrenzung||'—')+' · Ankerbeispiele: '+(c.ankerbeispiel||'—');}
const bookLabels = {code:'Code / vollständiger Codepfad *',kategorie:'Kategorie / erste Hierarchieebene *',unterkategorie:'Unterkategorie',auspraegung:'Ausprägung',facette:'Facette',definition:'Definition *',einschluss:'Einschlussregeln (optional)',ausschluss:'Ausschlussregeln (optional)',abgrenzung:'Abgrenzung / weitere Codierhinweise (optional)',ankerbeispiel:'Ankerbeispiele (optional)'};
const aliases = {segment:['Segment','Text','Segmenttext'],person:['Dokumentname','Dokument','Person','Interview'],code:['Code','Codes','human_code'],segment_id:['segment_id','Segment-ID','ID'],unit_id:['PassageID','Passage-ID','unit_id'],kategorie:['Kategorie','Hauptkategorie'],unterkategorie:['Unterkategorie','Subkategorie'],auspraegung:['Ausprägung','Auspraegung'],facette:['Facette'],definition:['Definition','Beschreibung'],ankerbeispiel:['Ankerbeispiel','Ankerbeispiele','Beispiel'],einschluss:['Einschlussregeln','Einschlusskriterien'],ausschluss:['Ausschlussregeln','Ausschlusskriterien']};
function el(tag, text, className) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(className)n.className=className; return n; }
function message(text, error=false) { $('message').textContent=text; $('message').className=error?'error':''; $('message').hidden=false; if($('sheet-dialog').open)$('sheet-error').textContent=error?text:''; for(const dialog of document.querySelectorAll('dialog[open]')){let box=dialog.querySelector('.dialog-error');if(!box){box=el('p',undefined,'dialog-error error');box.setAttribute('role','alert');dialog.append(box);}box.textContent=error?text:'';} }
async function api(path, data) {
  const response=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:{'X-App-Token':token,...(data===undefined?{}:{'Content-Type':'application/json'})},body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok)throw new Error(result.error || 'Anfrage fehlgeschlagen.'); return result;
}
function action(button, fn) { button.addEventListener('click',async e=>{ e.preventDefault();button.disabled=true;try{await fn();}catch(err){message(err.message,true);}finally{button.disabled=false;if(button.id==='start')updateStartGate();} }); }
function show(view) {
  viewing=view; document.querySelectorAll('.view').forEach(n=>n.hidden=n.id!=='view-'+view);
  document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.view===view));
  $('page-title').textContent=names[view];
  if(view!=='project'&&view!=='telegram'&&!project)message('Bitte zuerst ein Projekt anlegen oder auswählen.');
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.view)));
function needProject(){if(!project)throw new Error('Bitte zuerst ein Projekt auswählen.');return project.id;}
function renderProjects(){
  const selected=project?.id || '';
  $('projects').replaceChildren(new Option('Projekt auswählen …',''));
  state.projects.forEach(p=>$('projects').add(new Option(p.name,p.id)));
  $('projects').value=selected;
}
function renderMapping(container, labels, headers, configured={}) {
  $(container).replaceChildren();
  Object.entries(labels).forEach(([key,label])=>{
    const wrap=el('div'), select=el('select'), caption=el('label',label);select.id=container+'-'+key;caption.htmlFor=select.id;
    select.add(new Option('— Nicht zugeordnet —',''));headers.forEach(h=>select.add(new Option(h,h)));
    const candidates=container==='book-columns'?[configured[key]]:[configured[key],...(aliases[key]||[])];
    select.value=candidates.find(c=>headers.includes(c))||'';
    if(configured[key]===null || configured[key]==='')select.value='';
    wrap.append(caption,select);$(container).append(wrap);
  });
}
function table(info, title) {
  const part=el('div'), heading=el('h3',title), wrap=el('div',undefined,'table-wrap'), table=el('table');
  const head=el('thead'), row=el('tr');info.headers.forEach(h=>row.append(el('th',h)));head.append(row);table.append(head);
  const body=el('tbody');info.rows.forEach(values=>{const tr=el('tr');values.forEach(v=>tr.append(el('td',v)));body.append(tr);});table.append(body);wrap.append(table);part.append(heading,wrap);return part;
}
function renderFiles(){
  const uploads=project.uploads||{};$('previews').replaceChildren();
  for(const kind of ['segments','codebook']){
    const info=uploads[kind];$(kind+'-info').textContent=info?`${info.name}${info.sheet?' · Blatt '+info.sheet:''} · ${info.count} ${kind==='segments'?'Codierzeilen':'Kategoriezeilen'}`:'Noch keine Datei ausgewählt';
    if(info)$('previews').append(table(info,kind==='segments'?'Interviewdatei · erste fünf Zeilen':'Kategoriensystem · erste fünf Zeilen'));
  }
  renderMapping('segment-columns',columnLabels,uploads.segments?.headers||[],project.settings.columns||state.defaults.columns);
  $('book-preview').replaceChildren();
  if(uploads.codebook)$('book-preview').append(table(uploads.codebook,'Vorschau deiner Datei · Originalspalten'));
  else $('book-preview').append(el('p','Wähle unter Projekt & Dateien zuerst die Kategoriensystem-Datei aus.','hint'));
  renderMapping('book-columns',bookLabels,uploads.codebook?.headers||[],project.settings.book_columns||{});
  updateStartGate();
}
function loadFields(){
  const s=project.settings||{}, llm=state.defaults.llm;
  $('parallel-workers').value=String(s.parallel_workers??1);
  $('model').value=s.model??llm.model;$('num-ctx').value=s.num_ctx??llm.num_ctx;$('max-tokens').value=s.max_tokens??llm.max_tokens;
  $('temperature').value=s.temperature??llm.temperature;$('think').value=String(s.think??llm.think);
  $('label-mode').value=s.label_mode||'multi_label';
  const context=s.context||state.defaults.context;
  $('context-project').value=context.project_description||'';$('context-persons').value=context.participants||'';$('context-method').value=context.methodology||'';
  $('modules').replaceChildren();
  const selected=s.modules||state.modules.map(m=>m.id);
  state.modules.forEach(m=>{const label=el('label',undefined,'checkbox'),input=el('input'),text=el('span',m.name);input.type='checkbox';input.value=m.id;input.name='module';input.checked=selected.includes(m.id);input.addEventListener('change',updateModuleSelection);if(moduleHelp[m.id])text.append(el('small',moduleHelp[m.id]));if(m.depends_on.length)text.append(el('small','Benötigt: '+m.depends_on.map(id=>state.modules.find(x=>x.id===id)?.name||id).join(', ')));label.append(input,text);$('modules').append(label);});
  updateModuleSelection();
  renderFiles();
  if(typeof loadProviderFields==='function')loadProviderFields();
}
async function openProject(id){
  if(!id){$('projects').value=project?.id||'';return;}
  if(typeof finishReviewSave==='function')await finishReviewSave();
  const request=++projectRequest, loaded=await api('project?project='+id);
  if(request!==projectRequest)return;
  if(typeof finishReviewSave==='function')await finishReviewSave();
  if(request!==projectRequest)return;
  project=loaded;closeViewer();jobs=null;$('projects').value=id;$('welcome').hidden=true;
  document.querySelectorAll('.project-content').forEach(n=>n.hidden=false);
  $('project-subtitle').textContent=project.name+(project.demo?' · Künstliche Beispieldaten':' · Lokales Projekt');
  $('validation-result').hidden=true;$('category-result').replaceChildren();$('category-baseline').replaceChildren(new Option('Letzte gültige Version',''));loadFields();
  $('lineage-note').hidden=!project.review_provenance;$('lineage-note').textContent=project.review_provenance?.note||'';await refreshJobs();
}
function settings(){
  const columns={},book_columns={};Object.keys(columnLabels).forEach(k=>columns[k]=$('segment-columns-'+k).value);
  Object.keys(bookLabels).forEach(k=>book_columns[k]=$('book-columns-'+k).value);
  const think=$('think').value;
  return {...(typeof providerSelection==='function'?providerSelection():{}),columns,book_columns,parallel_workers:$('provider').value==='ollama_local'?Number($('parallel-workers').value):1,model:$('model').value,num_ctx:Number($('num-ctx').value),max_tokens:Number($('max-tokens').value),temperature:Number($('temperature').value),
    think:think==='true'?true:think==='false'?false:think,label_mode:$('label-mode').value,
    context:{project_description:$('context-project').value,participants:$('context-persons').value,methodology:$('context-method').value},
    modules:[...document.querySelectorAll('[name=module]:checked')].map(n=>n.value)};
}
async function saveAndValidate(pid=needProject()){
  $('validation-result').hidden=true;
  const s=settings(), result=await api('save',{project:pid,settings:s});
  if(project?.id!==pid)return result;
  project.settings=s;
  const box=$('validation-result');box.replaceChildren(el('h3','Eingaben sind gültig'));box.hidden=false;
  const stats=el('div',undefined,'stats');[['Codierzeilen',result.segments],['Passagen',result.passages??'—'],['Personen',result.persons],['Codepfade',result.codes]].forEach(([label,n])=>{const part=el('div',undefined,'stat');part.append(el('b',String(n)),el('span',label));stats.append(part);});box.append(stats,el('p','Diese Module werden bei einem Start ausgeführt (einschließlich benötigter Vorstufen): '+result.modules.map(m=>m.name).join(' → '),'hint'));
  if(result.codebook_fields)box.append(el('p',`${result.codebook_fields.einschluss} Codes mit Einschlussregeln · ${result.codebook_fields.ausschluss} mit Ausschlussregeln · ${result.codebook_fields.abgrenzung||0} mit weiteren Codierhinweisen · ${result.codebook_fields.ankerbeispiel} mit Ankerbeispielen. Die zugeordneten Regeln werden bei der Codierung und Codeprüfung berücksichtigt.`));
  return result;
}
function badge(status){const labels={running:'Läuft',success:'Abgeschlossen',failed:'Fehler',paused:'Pausiert',interrupted:'Unterbrochen',starting:'Startet'};return el('span',labels[status]||status,'badge '+status);}
function runCard(job,results=false){
  const card=el('article',undefined,'card run-card'),head=el('div',undefined,'section-heading'),date=new Date(job.created*1000).toLocaleString('de-DE');head.append(el('h3','Lauf vom '+date),badge(job.status));card.append(head);
  const completed=job.completed?.length||0,total=job.modules?.length||0,progress=el('progress');progress.max=total||1;progress.value=completed;
  card.append(progress,el('p',`${completed} von ${total} Modulen abgeschlossen`,'hint'));
  if(job.current&&job.status==='running')card.append(el('p','Aktuell: '+(job.modules.find(m=>m.id===job.current)?.name||job.current)));
  if(job.review_provenance)card.append(el('p',job.review_provenance.note,'selection-summary'));
  if(job.progress_detail&&job.status==='running'){
    const d=job.progress_detail,unit={passages:'Passagen',rows:'Codierzeilen',batches:'Prüfblöcke'}[d.unit];
    if(unit&&Number.isInteger(d.total)){const p=el('progress');p.max=d.total||1;p.value=d.completed||0;card.append(p,el('p',`${d.completed||0} von ${d.total} ${unit} bearbeitet`));}
    card.append(el('p',`${d.requests||0} Modellantworten empfangen`+(d.request_active?' · Modellanfrage läuft':''),'hint'));
    if(d.last_response_at)card.append(el('p','Letzte Modellantwort: '+new Date(d.last_response_at*1000).toLocaleTimeString('de-DE'),'hint'));
  }
  if(job.pause_requested)card.append(el('p','Pause angefordert. Das laufende Modul wird noch abgeschlossen.','hint'));
  if(job.error)card.append(el('p',job.error));
  const actions=el('div',undefined,'actions');
  if(job.status==='running'&&!job.pause_requested){const b=el('button','Nach diesem Modul pausieren','secondary');action(b,async()=>{const r=await api('pause',{project:project.id,job:job.id});message(r.message);await refreshJobs();});actions.append(b);}
  if(['failed','paused','interrupted'].includes(job.status)){const b=el('button','Diesen Lauf fortsetzen');action(b,async()=>{await api('start',{project:project.id,resume:job.id});message('Wiederaufnahme mit der ursprünglichen Dateiversion und den ursprünglichen Einstellungen gestartet.');await refreshJobs();});actions.append(b);}
  const log=el('button','Laufprotokoll herunterladen','small secondary');action(log,()=>artifact(job,'console.log',false));actions.append(log);card.append(actions);
  if(results){
    if(job.files?.includes('gesamtbericht.html')){const b=el('button','Interaktiven Bericht öffnen');action(b,()=>artifact(job,'gesamtbericht.html',true));card.append(b);}
    if(job.files?.includes('review_queue.json')){const b=el('button','Codierungen im Projekt prüfen');action(b,()=>openReview(job));card.append(b);}
    const list=el('div',undefined,'result-list');
    const priority=name=>name==='gesamtbericht.html'?2:name==='gesamtbericht.md'?1:0;
    const files=[...(job.files||[])].sort((a,b)=>priority(b)-priority(a));
    const titles={'gesamtbericht.html':'Interaktiver Gesamtbericht · HTML','gesamtbericht.md':'Gesamtbericht · Markdown','review_queue.html':'Separate Offline-Prüfliste · HTML','review_queue.json':'Prüffälle · JSON','codebook_proposals.md':'Kategorienvorschläge · Bericht','codebook_proposals.json':'Kategorienvorschläge · Daten'};
    files.forEach(name=>{const row=el('div',undefined,'result-row'),label=el('span',titles[name]||name);if(titles[name])label.append(el('small',name));row.append(label);const view=el('button','Ansehen','small secondary'),download=el('button','Speichern','small secondary');action(view,()=>artifact(job,name,true));action(download,()=>artifact(job,name,false));row.append(view,download);list.append(row);});
    if(files.length){const details=el('details');details.append(el('summary',`Einzelberichte und Datendateien (${files.length})`),list);card.append(details);}else card.append(el('p','Ergebnisse erscheinen nach Abschluss der ersten Module.','hint'));
  }
  return card;
}
async function refreshJobs(){
  if(!project)return;
  const pid=project.id, response=await api('jobs?project='+pid);if(project.id!==pid)return;
  $('telegram-status').textContent=response.telegram.last_status;
  if(JSON.stringify(jobs)===JSON.stringify(response.jobs))return;
  jobs=response.jobs;
  $('run-cards').replaceChildren();$('result-cards').replaceChildren();
  if(!jobs.length){$('run-cards').append(el('p','Noch kein Analyselauf. Deine Eingaben werden vor dem Start erneut geprüft.','empty'));$('result-cards').append(el('p','Hier erscheinen deine Berichte, Grafiken und Prüflisten.','empty'));}
  jobs.forEach(j=>{$('run-cards').append(runCard(j));$('result-cards').append(runCard(j,true));});
}
async function artifact(job,name,preview){
  const pid=needProject(),request=preview?++artifactRequest:0,query=new URLSearchParams({project:pid,job:job.id,name});
  const response=await fetch('/api/artifact?'+query,{headers:{'X-App-Token':token}});
  if(!response.ok)throw new Error((await response.json()).error);
  const blob=await response.blob();
  if(preview&&(project?.id!==pid||request!==artifactRequest))return;
  if(!preview){const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);return;}
  const isImage=/\.(png|jpg|jpeg|webp|svg)$/i.test(name),rawText=isImage?'':await blob.text();
  if(typeof finishReviewSave==='function')await finishReviewSave();
  if(project?.id!==pid||request!==artifactRequest)return;
  if(typeof closeReview==='function')closeReview();
  $('formatted-preview').hidden=true;$('formatted-preview').replaceChildren();
  $('viewer').hidden=false;$('viewer-name').textContent=name;$('text-preview').hidden=true;$('html-preview').hidden=true;$('image-preview').hidden=true;
  if(objectUrl)URL.revokeObjectURL(objectUrl);
  if(name.endsWith('.html')){$('html-preview').title=name==='gesamtbericht.html'?'Interaktiver Gesamtbericht':'HTML-Ergebnis';$('html-preview').srcdoc=rawText;$('html-preview').hidden=false;}
  else if(/\.(png|jpg|jpeg|webp|svg)$/i.test(name)){objectUrl=URL.createObjectURL(blob);$('image-preview').src=objectUrl;$('image-preview').hidden=false;}
  else{
    const text=rawText.slice(0,1000000);
    if(name.endsWith('.md')){markdownReport(text,$('formatted-preview'));$('formatted-preview').hidden=false;}
    else if(name.endsWith('.json')){
      let data;try{data=JSON.parse(text);}catch{}
      const rows=Array.isArray(data)?data:data?.results||data?.cases||data?.proposals||data?.decisions;
      if(Array.isArray(rows)&&rows.every(r=>r&&typeof r==='object'&&!Array.isArray(r))){searchableRows(rows,$('formatted-preview'));$('formatted-preview').hidden=false;}
      else{$('text-preview').textContent=text;$('text-preview').hidden=false;}
    }else{$('text-preview').textContent=text;$('text-preview').hidden=false;}
    if(rawText.length>1000000){$('formatted-preview').hidden=false;$('formatted-preview').append(el('p','Vorschau auf die ersten 1.000.000 Zeichen begrenzt. Vollständige Datei über Speichern herunterladen.'));}
  }
  show('results');$('viewer').scrollIntoView({behavior:'smooth'});
}
function renderTelegram(t){
  $('token-state').textContent=t.has_token?'Ein Token ist hinterlegt. Leeres Feld behält ihn bei; eine neue Eingabe ersetzt ihn.':'Kein Token hinterlegt.';
  $('chat-id').value=t.chat_id;$('telegram-enabled').checked=t.enabled;$('persist-token').checked=t.persist;$('persist-token').disabled=!t.can_persist;
  document.querySelectorAll('[name=tg-event]').forEach(n=>n.checked=t.events.includes(n.value));$('telegram-status').textContent=t.last_status;
}
function telegramValues(remove=false){return {token:$('bot-token').value,chat_id:$('chat-id').value,enabled:$('telegram-enabled').checked,persist:$('persist-token').checked,events:[...document.querySelectorAll('[name=tg-event]:checked')].map(n=>n.value),remove_token:remove};}
action($('save-telegram'),async()=>{const result=await api('telegram',telegramValues());$('bot-token').value='';renderTelegram(result);message('Telegram-Einstellungen gespeichert.');});
action($('remove-token'),async()=>{const result=await api('telegram',telegramValues(true));$('bot-token').value='';$('token-file').value='';renderTelegram(result);message('Token entfernt und Benachrichtigungen deaktiviert.');});
action($('test-telegram'),async()=>{if($('bot-token').value)throw new Error('Den neuen Token zuerst speichern.');await api('telegram-test',{});message('Testnachricht an den gespeicherten Telegram-Chat gesendet.');});
$('token-file').addEventListener('change',async()=>{try{const f=$('token-file').files[0];if(!f)return;if(f.size>4096)throw new Error('Token-Datei ist zu groß. Eine Textdatei nur mit dem Bot-Token verwenden.');$('bot-token').value=(await f.text()).trim();message('Token aus Datei geladen. Zum Übernehmen Einstellungen speichern.');}catch(e){message(e.message,true);}finally{$('token-file').value='';}});
let pendingUpload=null, uploading=false;
function uploadBusy(value){uploading=value;for(const kind of ['segments','codebook'])$(kind+'-file').disabled=value;}
function acceptUpload(uploads, pid, kind){
  if(project.id!==pid)return;
  project.uploads=uploads;delete project.settings[kind==='segments'?'columns':'book_columns'];renderFiles();$('validation-result').hidden=true;
  $('preview-details').open=true;
  message('Datei eingelesen. Prüfe die Vorschau und ordne unter Eingaben prüfen die vorhandenen Spalten zu.');
}
action($('sheet-import'),async()=>{
  if(!pendingUpload)return;
  const payload={...pendingUpload,sheet:$('sheet-choice').value};
  const result=await api('upload',payload);acceptUpload(result,payload.project,payload.kind);
  pendingUpload=null;$('sheet-dialog').close();
});
$('sheet-cancel').addEventListener('click',()=>{$('sheet-dialog').close();});
$('sheet-dialog').addEventListener('close',()=>{pendingUpload=null;uploadBusy(false);});
for(const kind of ['segments','codebook'])$(kind+'-file').addEventListener('change',async()=>{try{
  const pid=needProject(),file=$(kind+'-file').files[0];if(!file)return;
  if(uploading)throw new Error('Bitte den laufenden Dateiimport zuerst abschließen.');
  if(file.size>20*1024*1024)throw new Error('Datei überschreitet 20 MB.');
  uploadBusy(true);const capturedSettings=settings();
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
  if(project?.id!==pid)return;
  project.settings=capturedSettings;const payload={project:pid,kind,name:file.name,data:btoa(binary)}, result=await api('upload',payload);
  if(project?.id!==pid)return;
  if(result.requires_sheet){pendingUpload=payload;$('sheet-error').textContent='';$('sheet-choice').replaceChildren();result.sheets.forEach(s=>$('sheet-choice').add(new Option(s,s)));$('sheet-dialog').showModal();}
  else acceptUpload(result,pid,kind);
}catch(e){message(e.message,true);}finally{$(kind+'-file').value='';if(!pendingUpload)uploadBusy(false);}});
action($('validate'),async()=>{const pid=needProject(),r=await saveAndValidate(pid);if(project?.id!==pid)return;message(`Prüfung bestanden: ${r.segments} Codierzeilen, ${r.codes} Codepfade. Kein Modellaufruf.`);});
action($('start'),async()=>{const pid=needProject();await saveAndValidate(pid);if(project?.id!==pid)throw new Error('Projekt wurde während der Prüfung gewechselt. Bitte im gewünschten Projekt erneut starten.');await api('start',{project:pid});message('Analyse gestartet. Den Fortschritt findest du unten.');await refreshJobs();});
action($('check-ollama'),async()=>{const r=await api('models');$('model-list').replaceChildren();r.models.forEach(m=>$('model-list').append(new Option(m,m)));$('ollama-status').textContent=r.models.length?`${r.models.length} lokale Modelle gefunden. Im Modellfeld auswählen oder Namen eingeben.`:'Ollama ist erreichbar, aber kein lokales Modell installiert.';});
action($('clear-modules'),async()=>{document.querySelectorAll('[name=module]').forEach(n=>n.checked=false);updateModuleSelection();});
action($('all-modules'),async()=>{document.querySelectorAll('[name=module]').forEach(n=>n.checked=true);updateModuleSelection();});
action($('coding-modules'),async()=>{document.querySelectorAll('[name=module]').forEach(n=>n.checked=['clusterer','code_verification','blind_coding','coding_agreement'].includes(n.value));updateModuleSelection();});
function closeViewer(){if(typeof closeReview==='function')closeReview();artifactRequest++;$('formatted-preview').hidden=true;$('formatted-preview').replaceChildren();$('viewer').hidden=true;$('html-preview').removeAttribute('srcdoc');$('text-preview').textContent='';$('image-preview').removeAttribute('src');if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=null;}}
action($('close-viewer'),async()=>{if(typeof finishReviewSave==='function')await finishReviewSave();closeViewer();});
$('projects').addEventListener('change',async()=>{try{await openProject($('projects').value);show('project');}catch(e){message(e.message,true);}});
for(const id of ['new-project','welcome-create'])$(id).addEventListener('click',()=>{$('create-dialog').showModal();$('project-name').focus();});
$('cancel-create').addEventListener('click',()=>$('create-dialog').close());
$('create-form').addEventListener('submit',async e=>{e.preventDefault();try{if(typeof finishReviewSave==='function')await finishReviewSave();const p=await api('create',{name:$('project-name').value});state.projects.unshift(p);project=p;renderProjects();await openProject(p.id);$('create-dialog').close();show('project');message('Projekt angelegt. Wähle jetzt deine beiden Dateien (XLSX oder CSV).');}catch(err){message(err.message,true);$('create-dialog').close();}});
action($('demo'),async()=>{if(typeof finishReviewSave==='function')await finishReviewSave();const p=await api('create',{name:'Demo · Künstliche Interviews',demo:true});state.projects.unshift(p);project=p;renderProjects();await openProject(p.id);message('Demo geladen: 50 künstliche Codierzeilen und 43 Passagen. Du kannst zuerst die Eingaben prüfen.');});
async function init(){try{state=await api('state');renderProjects();renderTelegram(state.telegram);if(state.projects.length)await openProject(state.projects[0].id);}catch(e){message(e.message,true);}}
setInterval(async()=>{if(!project||polling||!['analysis','results'].includes(viewing))return;polling=true;try{await refreshJobs();}catch(e){message('Verbindung zur lokalen Oberfläche unterbrochen. Startfenster prüfen.',true);}finally{polling=false;}},4000);
function mappingProblems(){
  if(!project)return ['Projekt auswählen.'];
  const issues=[],uploads=project.uploads||{};
  for(const [kind,container,keys] of [['segments','segment-columns',['segment','person','code']],['codebook','book-columns',['definition']]]){
    const info=uploads[kind];if(!info){issues.push(kind==='segments'?'Interviewdatei auswählen.':'Kategoriensystem auswählen.');continue;}
    const labels=kind==='segments'?columnLabels:bookLabels;
    for(const key of keys)if(!info.headers.includes($(container+'-'+key).value))issues.push('Spalte zuordnen: '+labels[key].replace(' *','')+'.');
    if(kind==='codebook'){
      if(!['code','kategorie'].some(k=>info.headers.includes($('book-columns-'+k).value)))issues.push('Codepfad oder Kategorie zuordnen.');
      const used=Object.keys(bookLabels).map(k=>$('book-columns-'+k).value).filter(Boolean);
      if(new Set(used).size!==used.length)issues.push('Jede Kategoriensystem-Spalte nur einmal zuordnen.');
      if(used.some(v=>!info.headers.includes(v)))issues.push('Eine zugeordnete Kategoriensystem-Spalte fehlt in der Datei.');
    }
  }
  return issues;
}
function updateStartGate(){
  const issues=mappingProblems();$('start').disabled=issues.length>0;
  $('start-requirements').textContent=issues.length?'Start gesperrt: '+issues.join(' '):'Spalten zugeordnet. Beim Start werden alle Eingaben erneut geprüft.';
  $('mapping-requirements').textContent=$('start-requirements').textContent;
}
function invalidateCheck(event){if(event.target.closest('#view-project, #view-check, #view-analysis')){$('validation-result').hidden=true;updateStartGate();}}
document.addEventListener('input',invalidateCheck);
document.addEventListener('change',invalidateCheck);
action($('setup-check'),async()=>{const r=await api('setup-check',{project:needProject(),model:$('model').value,selection:providerSelection()});$('setup-result').replaceChildren();r.checks.forEach(c=>$('setup-result').append(el('p',(c.ok?'✓ ':'✗ ')+c.name+': '+c.detail)));$('setup-result').append(el('p',r.note,'hint'));});
let pendingModelTest=null;
action($('model-test'),async()=>{pendingModelTest={project:needProject(),selection:providerSelection()};$('model-test-dialog').showModal();});
$('model-test-cancel').onclick=()=>$('model-test-dialog').close();
action($('model-test-confirm'),async()=>{$('model-test-dialog').close();message('Kurzer Modelltest läuft …');const r=await api('model-test',pendingModelTest);message(r.message);});
action($('category-refresh'),async()=>{const pid=needProject(),r=await api('category-versions?project='+pid);if(project?.id!==pid)return;$('category-baseline').replaceChildren(new Option('Letzte gültige Version',''));r.versions.forEach(v=>$('category-baseline').add(new Option(new Date(v.created*1000).toLocaleString('de-DE')+' · '+v.id.slice(0,8),v.id)));});
action($('category-compare'),async()=>{const pid=needProject(),r=await api('category-compare',{project:pid,settings:settings(),baseline:$('category-baseline').value||null});if(project?.id!==pid)return;const box=$('category-result');box.replaceChildren(el('p',r.note));if(!r.baseline)return;box.append(el('p',`${r.added.length} neue, ${r.removed.length} entfernte, ${r.changed.length} geänderte Kategorien · ${r.affected_count} betroffene Codierzeilen`));r.added.forEach(c=>box.append(el('p','Neu: '+c.code+' — '+c.definition)));r.removed.forEach(c=>box.append(el('p','Entfernt: '+c.code)));r.changed.forEach(c=>{const d=el('details');d.append(el('summary','Geändert: '+c.code),el('p','Bisher: '+bookDescription(c.before)),el('p','Jetzt: '+bookDescription(c.after)));box.append(d);});if(r.affected.length){const d=el('details');d.append(el('summary','Betroffene Codierzeilen (maximal 200)'));r.affected.forEach(c=>d.append(el('p',c.segment_id+' · '+c.code)));box.append(d);}});
if(typeof initReviews==='function')initReviews();
init();
