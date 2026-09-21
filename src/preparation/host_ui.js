/* Project integration; explicit human decisions, never a cloud fallback. */
(()=>{'use strict';
const root=document.getElementById('host-workflow'),cfg=window.HOST_CONFIG;if(!root||!cfg)return;
let state,initialized=false;
const el=(tag,text,parent=root)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;parent.append(n);return n};
const input=(label,type='text')=>{const l=el('label',label),n=el('input',undefined,l);n.type=type;return n};
const button=(text,action)=>{const b=el('button',text);b.type='button';b.onclick=async()=>{b.disabled=true;try{await action()}catch(e){status.textContent=e.message}finally{b.disabled=false}};return b};
async function request(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Review-Token':cfg.token}:{},body:body?JSON.stringify(body):undefined});const result=await r.json();if(!r.ok)throw Error(result.error||'Anfrage fehlgeschlagen');return result}
el('h2','Vorbereitung und Analyse verbinden');
const links=el('p');for(const [label,path]of [['Audio und Lesetext','/'],['Manuell codieren','/coding'],['LLM-Vorschläge prüfen','/review']]){const a=el('a',label,links);a.href=path;links.append(' · ')}
const home=el('a','Zur Analyseoberfläche',links);home.href=new URL('',location.origin).href;
el('p','Die Analyseoberfläche legt Anbieter, Modell und Datenfreigabe fest. Lokal ist Standard. Eine Cloud-Anfrage überträgt Text und Kategorien nur nach ausdrücklicher Freigabe. Audio bleibt lokal.');
const status=el('p','Lade gespeicherten Stand …');status.setAttribute('role','status');
const providerLabel=el('label','Ollama-Verbindung'),provider=el('select',undefined,providerLabel);for(const [value,text]of [['ollama_local','Ollama lokal (Standard)'],['ollama_cloud','Ollama Cloud (ausdrückliche Freigabe)']]){const o=el('option',text,provider);o.value=value}
const model=input('Modellname');model.value='granite4.2:8b';
const privacy=input('DSGVO-relevantes Material – ausschließlich lokal','checkbox');privacy.checked=true;
const key=input('Ollama-Cloud-Schlüssel (leer = vorhandenen verwenden)','password');key.autocomplete='off';
const persist=input('Schlüssel unter Windows geschützt für spätere Sitzungen speichern','checkbox');
button('Verbindungseinstellungen speichern',async()=>{await request('/host-provider',{provider:provider.value,model:model.value,gdpr_relevant:privacy.checked,key:key.value,persist:persist.checked});key.value='';await refresh()});
const reviewer=input('Prüfende Person');reviewer.autocomplete='name';
const documentLabel=el('label','Dokument für Vorschläge'),doc=el('select',undefined,documentLabel);
const modeLabel=el('label','Vorschlagsart'),mode=el('select',undefined,modeLabel);for(const [value,text]of [['coding','Codierungen vorschlagen'],['categories','Kategorien vorschlagen']]){const o=el('option',text,mode);o.value=value}
const categories=input('Ich habe das aktuelle Kategoriensystem geprüft.','checkbox');
const cloud=input('Für diese Anfrage darf der bestätigte Transkripttext mit Kategorien an Ollama Cloud übermittelt werden.','checkbox');
button('Vorschläge ausdrücklich anfordern',async()=>{await refresh();const r=await request('/host-suggest',{revision:state.revision,document_id:doc.value,mode:mode.value,reviewer:reviewer.value,categories_confirmed:categories.checked,cloud_confirmed:cloud.checked});status.textContent='Vorschlagsauftrag '+r.status+'. Ergebnisse müssen anschließend einzeln geprüft werden.'});
button('Geprüfte Vorschläge ins Codierprojekt übernehmen',async()=>{await refresh();const decisions=await request('/review-state');await request('/host-approve',{revision:state.revision,decisions_revision:decisions.revision,reviewer:reviewer.value});location.href='/coding'});
el('h3','Gespeicherten Stand an die Analyse übergeben');
el('p','Vorbereitung vollständig speichern. Die Freigabe gilt genau für diese Version. Der Snapshot bewahrt Originaltext, Personen, Kategorien, Codierungen und Verlauf; spätere Bearbeitungen ändern keine alten Ergebnisse.');
const confirmed=input('Transkript, Personenkennungen, Ausschlüsse, Kategorien und Codierungen vollständig geprüft.','checkbox');
const start=input('Nach gültiger Übergabe den gespeicherten Analyseworkflow sofort starten.','checkbox');
button('Version bestätigen und übergeben',async()=>{await refresh();if(!confirmed.checked)throw Error('Prüfung zuerst ausdrücklich bestätigen.');const r=await request('/host-handoff',{revision:state.revision,project_sha256:state.project_sha256,confirmed:true,reviewer:reviewer.value,start_analysis:start.checked});confirmed.checked=false;status.textContent='Version '+r.handoff.snapshot+' übernommen. '+(r.job?'Analyse gestartet.':'Zur Analyseoberfläche wechseln und Module/Modell prüfen.');});
el('h3','Lokale Audioverarbeitung');
el('p','Keine automatische Modellinstallation. Ein separat installiertes Modell mit Modellmanifest kann gewählt werden. Erkennung läuft auf CPU; Sprecherlabels benötigen menschliche Prüfung.');
const folder=input('Lokaler Whisper-Modellordner');
button('Modellordner verwenden',async()=>{const r=await request('/host-model-folder',{path:folder.value});status.textContent='Lokales Modell: '+r.model});
button('Eigene aktive Audioerkennung beenden',async()=>{await request('/host-stop-audio',{});status.textContent='Beenden angefordert. Die eigene Prozessaufsicht bestätigt anschließend den Abschluss; Teilresultate bleiben erhalten.'});
async function refresh(){state=await request('/host-state');if(!initialized){provider.value=state.provider;model.value=state.model;privacy.checked=state.gdpr_relevant;initialized=true}const value=doc.value;doc.replaceChildren();for(const d of state.documents){const o=el('option',d.title,doc);o.value=d.id}if([...doc.options].some(o=>o.value===value))doc.value=value;status.textContent='Gespeicherte Version '+state.revision+' · '+state.provider+' · '+state.model+' · Vorschlagsauftrag: '+state.job.status+(state.job.error?' · '+state.job.error:'');}
refresh().catch(e=>status.textContent=e.message);setInterval(()=>refresh().catch(e=>status.textContent=e.message),5000);
})();
