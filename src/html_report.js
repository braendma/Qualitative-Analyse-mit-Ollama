'use strict';
function el(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
const reportData=JSON.parse(document.getElementById('report-data').textContent);
const reportSections=[],reportSearch=document.getElementById('report-search');
document.getElementById('metadata').textContent=`Lauf: ${reportData.run_id} · Erstellt: ${reportData.created_at} · Modell: ${reportData.model}`;
if(reportData.review_note){const n=document.getElementById('review-note');n.hidden=false;n.textContent=reportData.review_note;}
reportData.warnings.forEach(w=>document.getElementById('report-warnings').append(el('p',w,'warning')));
for(const section of reportData.sections){
  const box=el('details',undefined,'report-section');box.id=section.id;box.open=true;
  const summary=el('summary',section.title),content=el('div',undefined,'report-content');
  const media={};for(const [reference,key] of Object.entries(section.images))media[reference]=reportData.images[key];
  markdownReport(section.markdown,content,media);box.append(summary,content);document.getElementById('report-sections').append(box);
  const button=el('button',section.title,'nav-link');button.onclick=()=>{reportSearch.value='';filterReport();box.open=true;box.scrollIntoView({behavior:'smooth',block:'start'});summary.focus();};
  document.getElementById('report-nav').append(button);
  reportSections.push({box,text:(section.title+' '+section.markdown).toLocaleLowerCase('de-DE')});
}

// These counters describe saved model results, not later human review progress.
const charts=reportData.charts||{};
function chartSection(title,note){
  const box=el('details',undefined,'report-section');box.open=true;box.id='chart-'+reportSections.length;
  box.append(el('summary',title));const body=el('div',undefined,'report-content');body.append(el('p',note,'hint'));box.append(body);
  document.getElementById('report-sections').prepend(box);
  const button=el('button',title,'nav-link');button.onclick=()=>{reportSearch.value='';filterReport();box.open=true;box.scrollIntoView({behavior:'smooth'});};
  document.getElementById('report-nav').append(button);const item={box,text:title.toLowerCase()};reportSections.push(item);
  return {body,item};
}
function evidencePanel(body){const panel=el('div',undefined,'chart-evidence');panel.setAttribute('role','region');panel.setAttribute('aria-label','Textbelege');body.append(panel);return panel;}
function showEvidence(panel,rows){panel.replaceChildren(el('h3',rows.length+' zugehörige Textstellen'));
  for(const row of rows){const detail=el('details');detail.append(el('summary',row.person+' · '+(row.id||row.case_id)),el('p',row.text||'Text in diesem Lauf nicht gespeichert.'));if(row.human_codes)detail.append(el('p','Menschliche Codes: '+row.human_codes.join(' · ')));panel.append(detail);}
  panel.scrollIntoView({behavior:'smooth',block:'nearest'});
}
if(charts.review_cases?.length){
  const rows=charts.review_cases,{body,item}=chartSection('Prüfbedarf im Modellergebnis','Stand bei Abschluss des Modelllaufs. Zeigt die Fallklassifikation, nicht den aktuellen Bearbeitungsstand deiner manuellen Prüfung. Balken öffnen die zugehörigen Fälle.');
  const panel=evidencePanel(body),names={bestätigt:'Bestätigt',strittig:'Strittig',unklar:'Unklar',technischer_fehler:'Technischer Fehler'};
  for(const [key,name] of Object.entries(names)){const cases=rows.filter(r=>r.case_status===key),button=el('button',name+' · '+cases.length+' Fälle','chart-bar');
    const meter=el('meter');meter.min=0;meter.max=rows.length;meter.value=cases.length;meter.setAttribute('aria-label',name);button.prepend(meter);button.onclick=()=>showEvidence(panel,cases);body.insertBefore(button,panel);}
  item.text+=(JSON.stringify(rows)).toLocaleLowerCase('de-DE');
}
if(charts.person_categories?.length){
  const cells=charts.person_categories,{body,item}=chartSection('Personen und Kategorien','Codierzeilen je Person und vollständigem Codepfad. Mehrfachcodierungen zählen in mehreren Codepfaden; Häufigkeit ist kein Maß für inhaltliche Wichtigkeit. Eine Zahl öffnet die zugehörigen Textstellen.');
  const persons=[...new Set(cells.map(c=>c.person))],codes=[...new Set(cells.map(c=>c.code))], lookup=new Map(cells.map(c=>[JSON.stringify([c.person,c.code]),c]));
  const filter=el('input');filter.type='search';filter.placeholder='Codepfade filtern';filter.setAttribute('aria-label','Codepfade filtern');body.append(filter);
  const wrap=el('div',undefined,'table-wrap'),table=el('table'),head=el('tr');head.append(el('th','Codepfad'));persons.forEach(p=>head.append(el('th',p)));const thead=el('thead');thead.append(head);table.append(thead);const tbody=el('tbody');table.append(tbody);wrap.append(table);body.append(wrap);const panel=evidencePanel(body);
  const render=()=>{tbody.replaceChildren();for(const code of codes.filter(c=>c.toLocaleLowerCase('de-DE').includes(filter.value.trim().toLocaleLowerCase('de-DE')))){
    const tr=el('tr');tr.append(el('th',code));for(const person of persons){const cell=lookup.get(JSON.stringify([person,code])),td=el('td');if(cell){const b=el('button',String(cell.ids.length),'count-cell');b.setAttribute('aria-label',person+' · '+code+' · '+cell.ids.length+' Codierzeilen');b.onclick=()=>showEvidence(panel,cell.ids.map(id=>charts.evidence[id]));td.append(b);}else td.textContent='0';tr.append(td);}tbody.append(tr);}};
  filter.oninput=render;render();item.text+=JSON.stringify(cells).toLocaleLowerCase('de-DE');
}
function filterReport(){
  const query=reportSearch.value.trim().toLocaleLowerCase('de-DE');let matches=0;
  for(const item of reportSections){const visible=!query||item.text.includes(query);item.box.hidden=!visible;if(query&&visible)item.box.open=true;if(visible)matches++;}
  document.getElementById('search-status').textContent=query?`${matches} von ${reportSections.length} Berichtsteilen enthalten „${reportSearch.value.trim()}“.`:reportSections.length?`${reportSections.length} Berichtsteile. Über die Navigation direkt zu einem Abschnitt springen.`:'Für die gewählten Module liegen keine Markdown-Berichtsteile vor. Einzeldateien in der Ergebnisliste öffnen.';
}
reportSearch.oninput=filterReport;
for(const [id,value] of [['expand-all',true],['collapse-all',false]])document.getElementById(id).onclick=()=>reportSections.forEach(s=>{if(!s.box.hidden)s.box.open=value;});
let printState=null;
window.addEventListener('beforeprint',()=>{if(printState)return;printState=reportSections.map(s=>({open:s.box.open,hidden:s.box.hidden}));reportSections.forEach(s=>{s.box.open=true;s.box.hidden=false;});});
window.addEventListener('afterprint',()=>{if(printState){reportSections.forEach((s,i)=>Object.assign(s.box,printState[i]));printState=null;}});
document.getElementById('print-report').onclick=()=>window.print();
// The app keeps HTML in a sandbox. Printing is available from the downloaded file.
if(window.top!==window.self){document.getElementById('print-report').hidden=true;document.getElementById('print-hint').hidden=false;}
filterReport();
