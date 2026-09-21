'use strict';
// Human annotations overlay immutable model prose. Never mutate section Markdown,
// quotes, source links, identifiers, tables or downstream analysis artifacts.
function createReportReview(data){
  const fields=new Map(),current=new Map();
  for(const section of data.sections){
    const lines=section.markdown.split(/\r?\n/);
    for(const [line,field] of Object.entries(section.editable_fields||{})){
      if(!/^\d+$/.test(line)||lines[Number(line)]!==field.original_markdown)throw Error('Berichtsfeld passt nicht zur Originalquelle.');
      const key=section.id+':'+line;fields.set(key,field);current.set(key,field.original);
    }
  }
  const history=[];
  function append(change){
    const field=fields.get(change.key);
    if(!field||change.source_sha256!==field.source_sha256||change.before!==current.get(change.key)||change.revision!==history.length+1)throw Error('Änderung passt nicht zum unveränderten Berichtsfeld.');
    for(const key of ['after','reviewer','reason','at'])if(typeof change[key]!=='string'||!change[key].trim())throw Error('Text, Name, Begründung und Zeitpunkt sind erforderlich.');
    if(change.after.length>100000||!['needs_review','edited','reviewed'].includes(change.status))throw Error('Ungültige Berichtskorrektur.');
    const stored={key:change.key,source_sha256:field.source_sha256,revision:change.revision,before:change.before,after:change.after,reviewer:change.reviewer,reason:change.reason,at:change.at,status:change.status};
    history.push(stored);current.set(change.key,stored.after);return stored;
  }
  for(const record of data.report_review?.history||[])append(record);
  const sections=new Map(data.sections.map(s=>[s.id,s]));
  function related(key){
    const field=fields.get(key),section=sections.get(key.slice(0,key.lastIndexOf(':')));
    if(!field||!section)return [];
    const results=[];
    for(const [other,candidate] of fields){
      if(other===key)continue;
      const target=sections.get(other.slice(0,other.lastIndexOf(':'))),reasons=[];
      if(target===section&&field.topic_id&&field.topic_id===candidate.topic_id)reasons.push('Dasselbe Thema');
      if(target===section&&field.related_pair_id&&field.related_pair_id===candidate.related_pair_id)reasons.push('Zwei Seiten desselben gespeicherten Ambivalenzpaars');
      if(target===section&&((field.related_topic_ids||[]).includes(candidate.topic_id)||(candidate.related_topic_ids||[]).includes(field.topic_id)))reasons.push('Gespeicherter Themenverweis zwischen Muster und Gegenfall');
      if(field.item_id&&field.item_id===candidate.item_id)reasons.push('Derselbe gespeicherte Befund');
      const children=(candidate.parent_items||[]).filter(p=>p.id===field.item_id&&field.item_id);
      const parents=(field.parent_items||[]).filter(p=>p.id===candidate.item_id&&candidate.item_id);
      if(children.length)reasons.push('Befund geht laut Quellenregister hier ein: '+children.map(p=>p.reference).join(', '));
      if(parents.length)reasons.push('Zugrunde liegender Befund laut Quellenregister: '+parents.map(p=>p.reference).join(', '));
      const shared=(field.evidence||[]).filter(q=>q.id&&(candidate.evidence||[]).some(c=>c.id===q.id&&c.text===q.text));
      if(shared.length)reasons.push('Gemeinsame Originalzitate: '+[...new Set(shared.map(q=>q.id))].join(', '));
      if(reasons.length)results.push({target:other,section_id:target.id,label:target.title+' · '+(candidate.element_label||candidate.topic_id||candidate.label||'Deutung'),reasons});
    }
    function downstream(module,seen=new Set()){
      if(seen.has(module))return false;seen.add(module);
      const parents=data.review_dependencies?.[module]||[];
      return parents.includes(section.module_id)||parents.some(p=>downstream(p,seen));
    }
    if(section.module_id)for(const target of data.sections){
      const explicitElement=results.some(r=>r.section_id===target.id&&r.reasons.some(reason=>reason.startsWith('Befund geht laut Quellenregister')));
      if(target!==section&&target.module_id&&downstream(target.module_id)&&!explicitElement)results.push({target:'section:'+target.id,section_id:target.id,label:target.title,reasons:['Nachgelagertes Modul laut Ablaufplan; Zusammenhang einzelner Aussagen noch zu prüfen']});
    }
    return results;
  }
  const checks=[];
  function tasks(){
    const latest=new Map();
    for(const row of history)if(row.before!==row.after)latest.set(row.key,row);
    const result=[];
    for(const [key,row] of latest){
      for(const link of related(key)){
        const targetRevision=history.filter(r=>r.before!==r.after&&(link.target.startsWith('section:')?r.key.startsWith(link.section_id+':'):r.key===link.target)).at(-1)?.revision||0;
        const id=JSON.stringify([key,row.revision,link.target,targetRevision]);
        result.push({...link,id,source:key,revision:row.revision,checked:checks.some(c=>c.id===id)});
      }
    }
    return result;
  }
  function check(record){
    if(!tasks().some(t=>t.id===record.id))throw Error('Prüfaufgabe passt nicht mehr zum aktuellen Änderungsstand.');
    for(const k of ['reviewer','reason','at'])if(typeof record[k]!=='string'||!record[k].trim())throw Error('Name und begründetes Prüfergebnis sind erforderlich.');
    if(checks.some(c=>c.id===record.id))throw Error('Prüfung bereits dokumentiert.');
    checks.push({id:record.id,reviewer:record.reviewer,reason:record.reason,at:record.at});
  }
  // Old acknowledgements remain historical after a later edit; never approve a new revision.
  for(const record of data.report_review?.related_checks||[]){
    if(typeof record.id!=='string'||['reviewer','reason','at'].some(k=>typeof record[k]!=='string'||!record[k].trim()))throw Error('Ungültiger Prüfverlauf.');
    checks.push({...record});
  }
  return {fields,current,history,append,related,tasks,check,checks};
}
function reportJSON(value){return JSON.stringify(value).replace(/&/g,'\\u0026').replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');}
function installReportEditor(data){
  const review=createReportReview(data),pending=new Set();let dirty=false;
  const toolbar=el('div',undefined,'report-review-tools'),save=el('button','Bericht mit Änderungen speichern'),status=el('p',undefined,'hint');
  toolbar.id='report-review-tools';status.setAttribute('role','status');
  toolbar.append(el('p','Deutungen prüfen und berichtigen: Originalzitate, Quellenkennungen und berechnete Daten sind schreibgeschützt. Textkorrekturen verändern keine Analysedaten oder Folgemodule.'),save,status);
  document.getElementById('report-sections').before(toolbar);
  const followups=el('details',undefined,'related-review-tasks');toolbar.append(followups);
  const panels=new Map();
  function navigate(target,sectionId){
    const search=document.getElementById('report-search');search.value='';search.oninput?.();
    const section=document.getElementById(sectionId);if(!section)return;
    section.hidden=false;section.open=true;
    const panel=panels.get(target);if(panel)panel.open=true;
    const destination=panel||section;destination.scrollIntoView({behavior:'smooth',block:'start'});destination.querySelector('summary')?.focus();
  }
  function drawTasks(){
    const tasks=review.tasks(),open=tasks.filter(t=>!t.checked);
    followups.replaceChildren(el('summary',`Zusammenhängende Prüfstellen (${open.length} offen / ${tasks.length} gesamt)`));
    followups.append(el('p','Prüfstellen aus gespeicherten Befundketten (SWOT → Meta-SWOT), gleichen Themen, gemeinsamen Originalzitaten und dem Ablaufplan. Ein Herkunftsverweis belegt die Verwendung als Grundlage, nicht die Richtigkeit einer Deutung. Keine automatische Inhaltsprüfung und keine vollständige Erkennung aller Zusammenhänge. Bei einer Kontextumkehr auch SWOT-Einordnung, Zusammenfassungen und Empfehlungen prüfen. Gesperrte Zuordnungen und berechnete Tabellen werden durch eine Textänderung nicht neu berechnet.','hint'));
    if(!tasks.length)followups.append(el('p','Nach einer Textänderung erscheinen hier zugeordnete Prüfstellen. Ohne Verknüpfung bleibt die eigene Prüfung weiterer Berichtsteile erforderlich.'));
    for(const task of tasks){
      const item=el('details',undefined,'related-review-task'),title=el('summary',(task.checked?'Geprüft: ':'Offen: ')+task.label),go=el('button','Zur Prüfstelle');
      go.onclick=()=>navigate(task.target,task.section_id);
      const origin=el('button','Zur auslösenden Änderung '+task.revision);origin.onclick=()=>navigate(task.source,task.source.slice(0,task.source.lastIndexOf(':')));
      item.append(title,el('p',task.reasons.join(' · ')),origin,go);
      if(task.checked){const receipt=review.checks.find(c=>c.id===task.id);item.append(el('p',receipt.reviewer+' · '+receipt.at+' · '+receipt.reason));}
      else{
        const whoLabel=el('label','Geprüft von'),who=el('input');whoLabel.append(who);
        const whyLabel=el('label','Prüfergebnis / Begründung'),why=el('textarea');whyLabel.append(why);
        const done=el('button','Prüfung dokumentieren'),error=el('p');error.setAttribute('role','alert');
        done.onclick=()=>{try{review.check({id:task.id,reviewer:who.value.trim(),reason:why.value.trim(),at:new Date().toISOString()});dirty=true;drawTasks();update();}catch(e){error.textContent=e.message;}};
        item.append(whoLabel,whyLabel,done,error);
      }
      followups.append(item);
    }
    if(review.checks.length){
      const log=el('details');log.append(el('summary','Prüfverlauf einschließlich älterer Änderungsstände'));
      for(const receipt of review.checks){
        const current=tasks.some(t=>t.id===receipt.id);let label='Prüfstelle';
        try{const [source,revision,target]=JSON.parse(receipt.id);label='Änderung '+revision+' → '+(review.related(source).find(t=>t.target===target)?.label||'nicht mehr zuordenbare Prüfstelle');}catch(_){}
        log.append(el('p',label+' · '+(current?'Aktueller Stand: ':'Historischer Stand – spätere Änderungen nicht mitgeprüft: ')+receipt.reviewer+' · '+receipt.at+' · '+receipt.reason));
      }
      followups.append(log);
    }
  }
  drawTasks();
  function update(){status.textContent=`${review.fields.size} eindeutig zugeordnete Deutungsfelder, ${review.history.length} dokumentierte Änderungen. `+(dirty||pending.size?'Änderungen sind noch nicht als Datei gesichert.':'Zum dauerhaften Aufbewahren eine Berichtskopie speichern.');}
  function decorate(section,node,line){
    const key=section.id+':'+line,field=review.fields.get(key);if(!field)return;
    const panel=el('details',undefined,'report-edit-panel'),summary=el('summary','Deutung prüfen / bearbeiten'),badge=el('small',undefined,'review-badge');
    panels.set(key,panel);
    const labelText=el('label','Berichtstext (keine Zitate)'),input=el('textarea');input.value=review.current.get(key);input.rows=5;labelText.append(input);
    const labelName=el('label','Bearbeitet von'),name=el('input');labelName.append(name);
    const labelReason=el('label','Begründung / Prüfhinweis'),reason=el('textarea');reason.rows=2;labelReason.append(reason);
    const labelState=el('label','Prüfstatus'),state=el('select');
    for(const [value,text] of [['needs_review','Weiterer Prüfbedarf'],['edited','Menschlich bearbeitet'],['reviewed','Von mir anhand der Quellen geprüft']]){const option=el('option',text);option.value=value;state.append(option);}state.id='review-state-'+section.id+'-'+line;labelState.htmlFor=state.id;
    const original=el('details');original.append(el('summary','Unveränderter Modellvorschlag'),el('p',field.original));
    if(field.review_note)node.after(el('p','Dokumentierter Prüfbedarf am Originalvorschlag: '+field.review_note,'warning'));
    const sources=el('details');sources.append(el('summary','Zugeordnete Originalzitate (schreibgeschützt)'));
    if(field.evidence_note)sources.append(el('p',field.evidence_note,'hint'));
    if(!field.evidence?.length)sources.append(el('p','Für dieses Feld ist kein direktes Originalzitat im Export zugeordnet. Herkunft und Originalbericht unten prüfen; fehlende Belege werden nicht ergänzt.','hint'));
    for(const quote of field.evidence||[]){sources.append(el('p',[quote.person||'Person nicht dokumentiert',quote.id].join(' · ')),el('blockquote',quote.text||'Originaltext in diesem Export nicht verfügbar.'));}
    sources.open=true;
    const apply=el('button','Änderung übernehmen'),restore=el('button','Original als Entwurf einsetzen'),cancel=el('button','Entwurf verwerfen'),error=el('p'),history=el('details');error.setAttribute('role','alert');history.append(el('summary','Änderungsverlauf'));
    function draw(){
      const records=review.history.filter(r=>r.key===key),last=records.at(-1);
      if(last)node.textContent=last.after;
      badge.textContent=last?({'needs_review':'Prüfbedarf','edited':'Menschlich bearbeitet','reviewed':'Menschlich geprüft'}[last.status]+' · '+last.reviewer+' · '+last.at):'Modellvorschlag – noch nicht menschlich geprüft';
      history.replaceChildren(el('summary','Änderungsverlauf ('+records.length+')'));
      for(const row of records){const entry=el('details');entry.append(el('summary',row.at+' · '+row.reviewer),el('p','Begründung: '+row.reason),el('p','Vorher: '+row.before),el('p','Nachher: '+row.after));history.append(entry);}
    }
    const changed=()=>{pending.add(key);update();};input.oninput=name.oninput=reason.oninput=state.onchange=changed;
    restore.onclick=()=>{input.value=field.original;changed();};
    cancel.onclick=()=>{input.value=review.current.get(key);name.value='';reason.value='';pending.delete(key);error.textContent='';update();};
    apply.onclick=()=>{try{
      review.append({key,source_sha256:field.source_sha256,revision:review.history.length+1,before:review.current.get(key),after:input.value,reviewer:name.value.trim(),reason:reason.value.trim(),status:state.value,at:new Date().toISOString()});
      pending.delete(key);dirty=true;error.textContent='';draw();drawTasks();followups.open=true;update();
      followups.scrollIntoView({behavior:'smooth',block:'start'});
    }catch(e){error.textContent=e.message;}};
    panel.append(summary,original,sources,labelText,labelName,labelReason,labelState,state,apply,restore,cancel,error,history);
    node.after(badge,panel);draw();
  }
  function exportHTML(){
    if(pending.size)throw Error('Offene Entwürfe zuerst übernehmen oder verwerfen.');
    const doc=document.documentElement.cloneNode(true);
    doc.querySelector('#report-data').textContent=reportJSON({...data,report_review:{schema_version:1,history:review.history,related_checks:review.checks}});
    doc.querySelector('#report-sections').replaceChildren();doc.querySelector('#report-nav').replaceChildren();doc.querySelector('#report-warnings').replaceChildren();
    doc.querySelector('#report-review-tools')?.remove();doc.querySelector('#report-search').setAttribute('value','');
    return '<!doctype html>\n'+doc.outerHTML;
  }
  save.onclick=()=>{try{
    const html=exportHTML(),url=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'})),link=el('a');
    link.href=url;link.download='bericht_bearbeitet_'+new Date().toISOString().replace(/[:.]/g,'-')+'.html';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    status.textContent='Download angefordert. Die gespeicherte HTML-Kopie enthält Originale, Änderungen und Verlauf. Bitte die Datei im Downloadordner prüfen.';
    // A browser download request cannot confirm that a file actually reached disk.
  }catch(e){status.textContent=e.message;}};
  window.addEventListener('beforeunload',event=>{if(dirty||pending.size){event.preventDefault();event.returnValue='';}});
  update();return {decorate,exportHTML,review};
}
