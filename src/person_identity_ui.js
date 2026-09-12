'use strict';
let personPreview=null, personMap=Object.create(null), personProject=null;
function personIdentityReady(){return Boolean(personPreview && personProject===project?.id && $('person-confirmed').checked && Object.values(personMap).every(v=>v.trim()));}
function personIdentitySettings(){return personIdentityReady()?{fingerprint:personPreview.fingerprint,mapping:{...personMap},confirmed:true}:null;}
function resetPersonIdentity(){personPreview=null;personMap=Object.create(null);personProject=null;$('person-confirmed').checked=false;$('person-confirmed').disabled=true;$('person-rows').replaceChildren();$('person-count').textContent='Zuordnung noch nicht geprüft. Ein Interview kann auf mehrere Dokumente verteilt sein.';}
function updatePersonCount(){const values=Object.values(personMap).map(v=>v.trim());$('person-count').textContent=`${values.length} Dokumentkennungen → ${new Set(values.filter(Boolean)).size} Personen. Zusammengehörige Teile müssen dieselbe Personenkennung erhalten.`;$('person-confirmed').disabled=values.some(v=>!v);updateStartGate();}
action($('person-preview'),async()=>{
  const pid=needProject(),columns=settings().columns,inputId=project.uploads?.segments?.id;
  const info=await api('person-preview',{project:pid,columns});
  if(project?.id!==pid || project.uploads?.segments?.id!==inputId || JSON.stringify(settings().columns)!==JSON.stringify(columns))return;
  resetPersonIdentity();personPreview=info;personProject=pid;
  const saved=project.settings.person_identity;
  const reusable=saved?.fingerprint===info.fingerprint && saved.confirmed===true;
  const table=el('table'),head=el('tr');['Dokument / importierte Kennung','Codierzeilen','Gemeinsame Personenkennung'].forEach(v=>head.append(el('th',v)));table.append(head);
  info.documents.forEach(item=>{const row=el('tr'),cell=el('td'),input=el('input');input.type='text';input.maxLength=200;input.setAttribute('aria-label','Personenkennung für '+item.document);input.value=reusable?saved.mapping[item.document]||item.document:item.document;personMap[item.document]=input.value;
    input.addEventListener('input',()=>{personMap[item.document]=input.value;$('person-confirmed').checked=false;updatePersonCount();});cell.append(input);row.append(el('td',item.document),el('td',String(item.rows)),cell);table.append(row);});
  $('person-rows').append(table);$('person-confirmed').disabled=false;$('person-confirmed').checked=reusable;updatePersonCount();
});
$('person-confirmed').addEventListener('change',updateStartGate);
document.addEventListener('change',event=>{if(event.target.closest('#segment-columns')){resetPersonIdentity();updateStartGate();}});
