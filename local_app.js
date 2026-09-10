'use strict';
const $ = id => document.getElementById(id);
const tokenKey = 'qualitative-session-' + location.port;
const token = location.hash.slice(1) || sessionStorage.getItem(tokenKey) || '';
if (location.hash) { sessionStorage.setItem(tokenKey, token); history.replaceState(null, '', '/'); }
let state, project, jobs = [], viewing = 'project', objectUrl = null, polling = false;
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
const bookLabels = {kategorie:'Kategorie *',unterkategorie:'Unterkategorie',auspraegung:'Ausprägung',facette:'Facette',definition:'Definition *',ankerbeispiel:'Ankerbeispiel'};
const aliases = {segment:['Segment','Text','Segmenttext'],person:['Dokumentname','Dokument','Person','Interview'],code:['Code','Codes','human_code'],segment_id:['segment_id','Segment-ID','ID'],unit_id:['PassageID','Passage-ID','unit_id'],kategorie:['Kategorie','Hauptkategorie'],unterkategorie:['Unterkategorie','Subkategorie'],auspraegung:['Ausprägung','Auspraegung'],facette:['Facette'],definition:['Definition','Beschreibung'],ankerbeispiel:['Ankerbeispiel','Beispiel']};
function el(tag, text, className) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(className)n.className=className; return n; }
function message(text, error=false) { $('message').textContent=text; $('message').className=error?'error':''; $('message').hidden=false; }
async function api(path, data) {
  const response=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:{'X-App-Token':token,...(data===undefined?{}:{'Content-Type':'application/json'})},body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok)throw new Error(result.error || 'Anfrage fehlgeschlagen.'); return result;
}
function action(button, fn) { button.addEventListener('click',async e=>{ e.preventDefault();button.disabled=true;try{await fn();}catch(err){message(err.message,true);}finally{button.disabled=false;} }); }
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
    const candidates=[configured[key],...(aliases[key]||[])];
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
    const info=uploads[kind];$(kind+'-info').textContent=info?`${info.name} · ${info.count} Codier-/Kategoriezeilen`:'Noch keine Datei ausgewählt';
    if(info)$('previews').append(table(info,kind==='segments'?'Interviewdatei · erste fünf Zeilen':'Kategoriensystem · erste fünf Zeilen'));
  }
  renderMapping('segment-columns',columnLabels,uploads.segments?.headers||[],project.settings.columns||state.defaults.columns);
  renderMapping('book-columns',bookLabels,uploads.codebook?.headers||[],project.settings.book_columns||{});
}
function loadFields(){
  const s=project.settings||{}, llm=state.defaults.llm;
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
}
async function openProject(id){
  if(!id)return;
  project=await api('project?project='+id);jobs=null;$('projects').value=id;$('welcome').hidden=true;
  document.querySelectorAll('.project-content').forEach(n=>n.hidden=false);
  $('project-subtitle').textContent=project.name+(project.demo?' · Künstliche Beispieldaten':' · Lokales Projekt');
  $('validation-result').hidden=true;loadFields();await refreshJobs();
}
function settings(){
  const columns={},book_columns={};Object.keys(columnLabels).forEach(k=>columns[k]=$('segment-columns-'+k).value);
  Object.keys(bookLabels).forEach(k=>book_columns[k]=$('book-columns-'+k).value);
  const think=$('think').value;
  return {columns,book_columns,model:$('model').value,num_ctx:Number($('num-ctx').value),max_tokens:Number($('max-tokens').value),temperature:Number($('temperature').value),
    think:think==='true'?true:think==='false'?false:think,label_mode:$('label-mode').value,
    context:{project_description:$('context-project').value,participants:$('context-persons').value,methodology:$('context-method').value},
    modules:[...document.querySelectorAll('[name=module]:checked')].map(n=>n.value)};
}
async function saveAndValidate(){
  const pid=needProject(), s=settings(), result=await api('save',{project:pid,settings:s});project.settings=s;
  const box=$('validation-result');box.replaceChildren(el('h3','Eingaben sind gültig'));box.hidden=false;
  const stats=el('div',undefined,'stats');[['Codierzeilen',result.segments],['Passagen',result.passages??'—'],['Personen',result.persons],['Codepfade',result.codes]].forEach(([label,n])=>{const part=el('div',undefined,'stat');part.append(el('b',String(n)),el('span',label));stats.append(part);});box.append(stats,el('p','Diese Module werden bei einem Start ausgeführt (einschließlich benötigter Vorstufen): '+result.modules.map(m=>m.name).join(' → '),'hint'));
  return result;
}
function badge(status){const labels={running:'Läuft',success:'Abgeschlossen',failed:'Fehler',paused:'Pausiert',interrupted:'Unterbrochen',starting:'Startet'};return el('span',labels[status]||status,'badge '+status);}
function runCard(job,results=false){
  const card=el('article',undefined,'card run-card'),head=el('div',undefined,'section-heading'),date=new Date(job.created*1000).toLocaleString('de-DE');head.append(el('h3','Lauf vom '+date),badge(job.status));card.append(head);
  const completed=job.completed?.length||0,total=job.modules?.length||0,progress=el('progress');progress.max=total||1;progress.value=completed;
  card.append(progress,el('p',`${completed} von ${total} Modulen abgeschlossen`,'hint'));
  if(job.current&&job.status==='running')card.append(el('p','Aktuell: '+(job.modules.find(m=>m.id===job.current)?.name||job.current)));
  if(job.pause_requested)card.append(el('p','Pause angefordert. Das laufende Modul wird noch abgeschlossen.','hint'));
  if(job.error)card.append(el('p',job.error));
  const actions=el('div',undefined,'actions');
  if(job.status==='running'&&!job.pause_requested){const b=el('button','Nach diesem Modul pausieren','secondary');action(b,async()=>{const r=await api('pause',{project:project.id,job:job.id});message(r.message);await refreshJobs();});actions.append(b);}
  if(['failed','paused','interrupted'].includes(job.status)){const b=el('button','Diesen Lauf fortsetzen');action(b,async()=>{await api('start',{project:project.id,resume:job.id});message('Wiederaufnahme mit der ursprünglichen Dateiversion und den ursprünglichen Einstellungen gestartet.');await refreshJobs();});actions.append(b);}
  const log=el('button','Laufprotokoll herunterladen','small secondary');action(log,()=>artifact(job,'console.log',false));actions.append(log);card.append(actions);
  if(results){
    const list=el('div',undefined,'result-list');
    const files=[...(job.files||[])].sort((a,b)=>Number(b==='gesamtbericht.md')-Number(a==='gesamtbericht.md'));
    files.forEach(name=>{const row=el('div',undefined,'result-row');row.append(el('span',name));const view=el('button','Ansehen','small secondary'),download=el('button','Speichern','small secondary');action(view,()=>artifact(job,name,true));action(download,()=>artifact(job,name,false));row.append(view,download);list.append(row);});
    card.append(files.length?list:el('p','Ergebnisse erscheinen nach Abschluss der ersten Module.','hint'));
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
  const query=new URLSearchParams({project:project.id,job:job.id,name});
  const response=await fetch('/api/artifact?'+query,{headers:{'X-App-Token':token}});
  if(!response.ok)throw new Error((await response.json()).error);
  const blob=await response.blob();
  if(!preview){const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);return;}
  $('viewer').hidden=false;$('viewer-name').textContent=name;$('text-preview').hidden=true;$('html-preview').hidden=true;$('image-preview').hidden=true;
  if(objectUrl)URL.revokeObjectURL(objectUrl);
  if(name.endsWith('.html')){$('html-preview').srcdoc=await blob.text();$('html-preview').hidden=false;}
  else if(/\.(png|jpg|jpeg|webp)$/i.test(name)){objectUrl=URL.createObjectURL(blob);$('image-preview').src=objectUrl;$('image-preview').hidden=false;}
  else{$('text-preview').textContent=(await blob.text()).slice(0,1000000);$('text-preview').hidden=false;}
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
for(const kind of ['segments','codebook'])$(kind+'-file').addEventListener('change',async()=>{try{
  const pid=needProject(),file=$(kind+'-file').files[0];if(!file)return;if(file.size>20*1024*1024)throw new Error('Datei überschreitet 20 MB.');
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
  project.settings=settings();project.uploads=await api('upload',{project:pid,kind,name:file.name,data:btoa(binary)});renderFiles();$('validation-result').hidden=true;message('Datei als lokale Projektkopie übernommen. Bitte Spaltenzuordnung prüfen.');
}catch(e){message(e.message,true);}finally{$(kind+'-file').value='';}});
action($('validate'),async()=>{const r=await saveAndValidate();message(`Prüfung bestanden: ${r.segments} Codierzeilen, ${r.codes} Codepfade. Kein Modellaufruf.`);});
action($('start'),async()=>{await saveAndValidate();await api('start',{project:project.id});message('Analyse gestartet. Den Fortschritt findest du unten.');await refreshJobs();});
action($('check-ollama'),async()=>{const r=await api('models');$('model-list').replaceChildren();r.models.forEach(m=>$('model-list').append(new Option(m,m)));$('ollama-status').textContent=r.models.length?`${r.models.length} lokale Modelle gefunden. Im Modellfeld auswählen oder Namen eingeben.`:'Ollama ist erreichbar, aber kein lokales Modell installiert.';});
action($('clear-modules'),async()=>{document.querySelectorAll('[name=module]').forEach(n=>n.checked=false);updateModuleSelection();});
action($('all-modules'),async()=>{document.querySelectorAll('[name=module]').forEach(n=>n.checked=true);updateModuleSelection();});
action($('coding-modules'),async()=>{document.querySelectorAll('[name=module]').forEach(n=>n.checked=['clusterer','code_verification','blind_coding','coding_agreement'].includes(n.value));updateModuleSelection();});
$('close-viewer').addEventListener('click',()=>{$('viewer').hidden=true;$('html-preview').removeAttribute('srcdoc');if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=null;}});
$('projects').addEventListener('change',async()=>{try{await openProject($('projects').value);show('project');}catch(e){message(e.message,true);}});
for(const id of ['new-project','welcome-create'])$(id).addEventListener('click',()=>{$('create-dialog').showModal();$('project-name').focus();});
$('cancel-create').addEventListener('click',()=>$('create-dialog').close());
$('create-form').addEventListener('submit',async e=>{e.preventDefault();try{const p=await api('create',{name:$('project-name').value});state.projects.unshift(p);project=p;renderProjects();await openProject(p.id);$('create-dialog').close();show('project');message('Projekt angelegt. Wähle jetzt deine beiden CSV-Dateien.');}catch(err){message(err.message,true);$('create-dialog').close();}});
action($('demo'),async()=>{const p=await api('create',{name:'Demo · Künstliche Interviews',demo:true});state.projects.unshift(p);project=p;renderProjects();await openProject(p.id);message('Demo geladen: 50 künstliche Codierzeilen und 43 Passagen. Du kannst zuerst die Eingaben prüfen.');});
async function init(){try{state=await api('state');renderProjects();renderTelegram(state.telegram);if(state.projects.length)await openProject(state.projects[0].id);}catch(e){message(e.message,true);}}
setInterval(async()=>{if(!project||polling||!['analysis','results'].includes(viewing))return;polling=true;try{await refreshJobs();}catch(e){message('Verbindung zur lokalen Oberfläche unterbrochen. Startfenster prüfen.',true);}finally{polling=false;}},4000);
init();
