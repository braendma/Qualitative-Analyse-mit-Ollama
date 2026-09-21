/* Same-origin navigation; normal links preserve existing unload/save guards. */
(()=>{'use strict';
const cfg=window.HOST_CONFIG,prep=!!cfg;
const node=(tag,text,parent)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(parent)parent.append(n);return n};
let sidebar=document.querySelector('.sidebar');
if(prep){document.body.classList.add('preparation-page');sidebar=node('aside');sidebar.className='sidebar';document.body.prepend(sidebar);node('h2','Qualitative Analyse',sidebar);node('p','Arbeitswege im selben Projekt',sidebar);}
if(!sidebar)return;
sidebar.id='workflow-sidebar';
const toggle=node('button','☰ Menü',document.body);toggle.id='workflow-toggle';toggle.type='button';toggle.setAttribute('aria-controls',sidebar.id);
const apply=value=>{document.body.classList.toggle('workflow-collapsed',value);toggle.setAttribute('aria-expanded',String(!value));toggle.textContent=value?'☰ Menü öffnen':'☰ Menü schließen'};
let saved;try{saved=sessionStorage.getItem('qa-menu-collapsed')}catch{}
apply(saved===null?window.innerWidth<850:saved==='true');
toggle.onclick=()=>{const value=!document.body.classList.contains('workflow-collapsed');apply(value);try{sessionStorage.setItem('qa-menu-collapsed',String(value))}catch{}};
const nav=node('nav');nav.className='workflow-links';nav.setAttribute('aria-label','Arbeitswege');
sidebar.insertBefore(nav,sidebar.querySelector('nav')||sidebar.lastElementChild);
const analysis=node('a','Vorhandener Export',nav);analysis.href=prep?'/?project='+encodeURIComponent(cfg.project):'/';
const preparation=node(prep?'a':'button','Transkription und Codierung',nav);
if(prep){preparation.href='/preparation/'+encodeURIComponent(cfg.project)+'/';preparation.setAttribute('aria-current','page');const links=node('nav',null,sidebar);links.className='workflow-links';links.setAttribute('aria-label','Transkription und Codierung');for(const [title,path]of [['Aufnahme & Text prüfen','/'],['Transkript importieren & codieren','/coding']]){const a=node('a',title,links);a.href='/preparation/'+encodeURIComponent(cfg.project)+path}node('p','Gespeicherte Texte und Codierungen bleiben beim Wechsel erhalten. Laufende Transkriptionen arbeiten weiter.',sidebar)}
else{analysis.setAttribute('aria-current','page');analysis.onclick=e=>{e.preventDefault();document.querySelector('[data-view="project"]').click()};preparation.type='button';preparation.onclick=()=>window.openPreparation?.();}
if(prep&&cfg.storage_path){const p=node('p','Projektordner: '+cfg.storage_path,sidebar);p.className='project-storage-path';}
// Browser-independent audio chooser for embedded browsers without a file dialog.
const local=document.getElementById('audioLocal');if(!local||!prep)return;
const endpoint='/preparation/'+encodeURIComponent(cfg.project);
async function post(path,body){const r=await fetch(endpoint+path,{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':window.READING_TOKEN},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||'Anfrage fehlgeschlagen');return v;}
const dialog=node('dialog',null,document.body);dialog.id='audio-picker';dialog.setAttribute('aria-label','Aufnahme auf diesem Rechner auswählen');node('h2','Aufnahme auswählen',dialog);
const path=node('input',null,dialog);path.setAttribute('aria-label','Ordnerpfad');
const open=node('button','Ordner öffnen',dialog),up=node('button','Übergeordneter Ordner',dialog),home=node('button','Persönlicher Ordner',dialog);
const roots=node('select',null,dialog);roots.setAttribute('aria-label','Startpunkt');
const list=node('div',null,dialog);list.id='audio-picker-list';const status=node('p',null,dialog);status.setAttribute('role','status');
const choose=node('button','Ausgewählte Aufnahme übernehmen',dialog),close=node('button','Abbrechen',dialog);
let selected=null,parent=null,epoch=0;
async function browse(value){const id=++epoch;selected=null;choose.disabled=true;list.replaceChildren();status.textContent='Ordner wird geöffnet …';try{const result=await post('/host-audio-browse',{path:value});if(id!==epoch||!dialog.open)return;path.value=result.path;parent=result.parent;up.disabled=!parent;roots.replaceChildren(new Option('Startpunkt auswählen …',''));for(const r of result.roots)roots.add(new Option(r.name,r.path));for(const d of result.directories){const b=node('button','📁 '+d.name,list);b.onclick=()=>browse(d.path)}for(const f of result.files){const b=node('button',f.name,list);b.onclick=()=>{selected=f;for(const n of list.children)n.removeAttribute('aria-pressed');b.setAttribute('aria-pressed','true');choose.disabled=false;status.textContent=f.name}}status.textContent=result.truncated?'Liste begrenzt; einen Unterordner öffnen.':result.files.length+' Audiodateien in diesem Ordner.'}catch(e){if(id===epoch)status.textContent=e.message}}
local.onclick=()=>{dialog.showModal();browse('')};open.onclick=()=>browse(path.value);path.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();browse(path.value)}};path.oninput=()=>{++epoch;selected=null;choose.disabled=true;list.replaceChildren();status.textContent='Pfad mit „Ordner öffnen“ bestätigen.'};up.onclick=()=>browse(parent);home.onclick=()=>browse('');roots.onchange=()=>{if(roots.value)browse(roots.value)};
close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>{++epoch});
choose.onclick=()=>{if(!selected)return;window.selectedLocalAudio=selected.path;document.getElementById('audioFile').value='';document.getElementById('audioSelection').textContent=selected.name+' ausgewählt';dialog.close()};
document.getElementById('audioFile').addEventListener('change',()=>{window.selectedLocalAudio=null;document.getElementById('audioSelection').textContent=''});
window.startLocalAudio=async()=>{if(uploading)return;uploading=true;pause();updateControls();const status=document.getElementById('uploadStatus');status.textContent='Aufnahme lokal kopieren und prüfen …';try{await post('/next-local-audio',{path:window.selectedLocalAudio,workspace_id:context.workspace_id,revision:saver?.revision??0,expected_speakers:document.getElementById('expectedSpeakers').value});location.reload()}catch(e){status.textContent=e.message;uploading=false;updateControls()}};
})();
