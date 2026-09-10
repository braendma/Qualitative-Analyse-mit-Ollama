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
