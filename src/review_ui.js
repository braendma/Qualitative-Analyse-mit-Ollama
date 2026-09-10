'use strict';
let reviewState=null,reviewRequest=0;
function reviewComplete(r){return r.decision!=='unresolved'&&r.note.trim()&&r.reviewer.trim();}
function blankDecision(c){return {case_id:c.case_id,decision:'unresolved',final_codes:[],note:'',reviewer:''};}
function closeReview(){
  if(reviewState?.pending.size)throw new Error('Ungespeicherte Prüfentscheidungen: zuerst speichern oder den Entwurf sichern und die Seite neu laden.');
  reviewRequest++;if(reviewState)clearTimeout(reviewState.timer);reviewState=null;$('review-panel').hidden=true;
}
function downloadReviewDraft(s){
  const payload={schema_version:1,source_fingerprint:s.queue.source_fingerprint,decisions:[...s.rows.values()]};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})),a=el('a');a.href=url;a.download='review_decisions_draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
}
async function flushReview(s){
  if(s.saving)return s.saving;
  s.saving=(async()=>{
    while(s.pending.size){
      const [id,row]=s.pending.entries().next().value;
      try{
        const response=await api('review-save',{project:s.pid,job:s.job.id,revision:s.revision,decision:row});
        s.revision=response.revision;
        if(s.pending.get(id)===row)s.pending.delete(id);
        s.error='';if(reviewState===s)reviewStats(s);
      }catch(e){s.error=e.message;if(reviewState===s)reviewStats(s);return;}
    }
  })();
  try{await s.saving;}finally{s.saving=null;if(reviewState===s)reviewStats(s);}
}
function queueReview(s,row){
  s.rows.set(row.case_id,row);s.pending.set(row.case_id,JSON.parse(JSON.stringify(row)));reviewStats(s);
  clearTimeout(s.timer);s.timer=setTimeout(()=>flushReview(s),600);
}
function reviewStats(s){
  if(reviewState!==s)return;
  const critical=s.queue.cases.filter(c=>c.needs_review),open=critical.filter(c=>!reviewComplete(s.rows.get(c.case_id))).length;
  $('review-status').textContent=s.error?'Speichern fehlgeschlagen: '+s.error+' Entwurf lokal sichern und Seite neu laden.':s.pending.size?'Änderungen werden gespeichert …':`Im Projekt gespeichert · Prüfversion ${s.revision}`;
  $('review-count').textContent=`${critical.length-open} von ${critical.length} kritischen Fällen abgeschlossen. Abschluss benötigt Entscheidung, Begründung und prüfende Person.`;
  const ready=!open&&!s.pending.size&&!s.error;
  $('review-next').hidden=!ready;$('review-next').textContent=ready?'Die kritischen Fälle sind geprüft. Du kannst jetzt einen Folgelauf vorbereiten oder optional Kategorienvorschläge erstellen lassen.':'';
  $('review-followup').disabled=!ready;$('review-refine').disabled=!ready||![...s.rows.values()].some(reviewComplete);
}
function drawReview(s){
  const filter=$('review-search').value.toLocaleLowerCase('de-DE'),critical=$('review-critical').checked;
  const filtered=s.queue.cases.filter(c=>(!critical||c.needs_review)&&JSON.stringify(c).toLocaleLowerCase('de-DE').includes(filter));
  const pages=Math.max(1,Math.ceil(filtered.length/20));s.page=Math.min(s.page,pages-1);
  $('review-cases').replaceChildren();$('review-page').textContent=`${filtered.length} Fälle · Seite ${s.page+1} von ${pages}`;
  $('review-prev').disabled=s.page===0;$('review-more').disabled=s.page===pages-1;
  filtered.slice(s.page*20,s.page*20+20).forEach(c=>{
    let r=s.rows.get(c.case_id);const card=el('article',undefined,'card'),decision=el('select'),codes=el('select'),note=el('textarea'),who=el('input');
    card.append(el('h3',c.case_id+' · '+c.case_status),el('p',c.person),el('blockquote',c.text));
    card.append(el('p','Ursprüngliche Codes: '+c.human_codes.join(', ')),el('p','Modellvorschlag: '+(c.predicted_codes.join(', ')||'keine Zuordnung')));
    const details=el('details');details.append(el('summary','Modellbegründung und Belege'));c.model_reasons.forEach(t=>details.append(el('p',t)));
    details.append(el('pre',JSON.stringify({verification:c.verification,related_audits:c.related_audits},null,2)));card.append(details);
    for(const [value,title] of [['unresolved','Noch offen'],['keep_human','Ursprüngliche Codes beibehalten'],['accept_model','Modellcodes übernehmen'],['custom','Codes selbst festlegen']])decision.add(new Option(title,value));
    decision.value=r.decision;codes.multiple=true;codes.size=5;
    s.queue.codebook.forEach(c=>{const option=new Option(c.code,c.code);option.selected=r.final_codes.includes(c.code);codes.add(option);});codes.disabled=r.decision!=='custom';
    note.value=r.note;note.maxLength=12000;who.value=r.reviewer;who.maxLength=200;
    for(const [title,input] of [['Deine Entscheidung',decision],['Finale Codes (Mehrfachauswahl mit Strg/⌘)',codes],['Begründung / Notiz',note],['Geprüft von',who]]){const label=el('label',title);label.append(input);card.append(label);}
    const edit=()=>{r={...r,note:note.value,reviewer:who.value};queueReview(s,r);};
    note.oninput=edit;who.oninput=edit;
    decision.onchange=()=>{r={...r,decision:decision.value,final_codes:decision.value==='keep_human'?[...c.human_codes]:decision.value==='accept_model'?[...c.predicted_codes]:[]};codes.disabled=r.decision!=='custom';[...codes.options].forEach(o=>o.selected=r.final_codes.includes(o.value));edit();};
    codes.onchange=()=>{r={...r,final_codes:[...codes.selectedOptions].map(o=>o.value)};edit();};
    $('review-cases').append(card);
  });reviewStats(s);
}
async function openReview(job){
  const pid=needProject();await finishReviewSave();closeViewer();const request=++reviewRequest;
  const loaded=await api('review?'+new URLSearchParams({project:pid,job:job.id}));
  if(project?.id!==pid||request!==reviewRequest)return;
  const rows=new Map(loaded.queue.cases.map(c=>[c.case_id,blankDecision(c)]));loaded.draft.decisions.forEach(r=>rows.set(r.case_id,r));
  reviewState={pid,job,queue:loaded.queue,rows,revision:loaded.draft.revision,pending:new Map(),saving:null,error:'',page:0};
  $('review-panel').hidden=false;$('review-search').value='';$('review-critical').checked=true;show('results');drawReview(reviewState);$('review-panel').scrollIntoView({behavior:'smooth'});
}
async function finishReviewSave(){
  if(!reviewState)return;const s=reviewState;clearTimeout(s.timer);await flushReview(s);
  if(s.pending.size||s.error)throw new Error('Ungespeicherte Prüfentscheidungen: zuerst speichern oder den Entwurf sichern. '+s.error);
}
function initReviews(){
  window.addEventListener('beforeunload',e=>{if(reviewState?.pending.size){e.preventDefault();e.returnValue='';}});
  for(const id of ['review-search','review-critical'])$(id).addEventListener('input',()=>{if(reviewState){reviewState.page=0;drawReview(reviewState);}});
  action($('review-prev'),async()=>{if(reviewState){reviewState.page--;drawReview(reviewState);}});
  action($('review-more'),async()=>{if(reviewState){reviewState.page++;drawReview(reviewState);}});
  action($('review-save'),()=>finishReviewSave());
  action($('review-draft'),async()=>{if(reviewState)downloadReviewDraft(reviewState);});
  action($('review-close'),async()=>{await finishReviewSave();closeReview();});
  action($('review-xlsx'),async()=>{
    const s=reviewState;if(!s)return;await finishReviewSave();
    const response=await fetch('/api/review-export?'+new URLSearchParams({project:s.pid,job:s.job.id,format:'xlsx'}),{headers:{'X-App-Token':token}});
    if(!response.ok)throw new Error((await response.json()).error);
    const url=URL.createObjectURL(await response.blob()),a=el('a');a.href=url;a.download='Pruefentscheidungen.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  });
  action($('review-followup'),async()=>{
    const s=reviewState;await finishReviewSave();if(!s||reviewState!==s)return;
    const preview=await api('followup-preview',{project:s.pid,job:s.job.id});if(reviewState!==s)return;
    s.preview=preview;$('followup-info').textContent=`Fälle mit geänderten Codes: ${preview.changed}. Fälle ohne finale Zuordnung: ${preview.uncoded}. `+preview.note;
    $('followup-changes').replaceChildren();preview.changes.forEach(c=>$('followup-changes').append(el('p',`${c.case_id}: ${c.before.join(', ')} → ${c.after.join(', ')||'keine Zuordnung'}`)));
    $('followup-exclusions').checked=false;$('followup-exclusion-label').hidden=!preview.uncoded;$('followup-dialog').showModal();
  });
  action($('followup-confirm'),async()=>{
    const s=reviewState;if(!s||!s.preview)return;
    if(s.preview.uncoded&&!$('followup-exclusions').checked)throw new Error('Ausschluss der unzugeordneten Fälle bitte ausdrücklich bestätigen.');
    const result=await api('followup-prepare',{project:s.pid,job:s.job.id,revision:s.preview.review_revision,accept_exclusions:$('followup-exclusions').checked});
    $('followup-dialog').close();if(project?.id!==s.pid)return;
    await openProject(s.pid);show('analysis');message(`Neue Eingabeversion mit ${result.preview.changed} geänderten Fällen vorbereitet. Module prüfen und den neuen Lauf ausdrücklich starten.`);
  });
  $('followup-cancel').onclick=()=>$('followup-dialog').close();
  action($('review-refine'),async()=>{await finishReviewSave();if(reviewState){$('refinement-dialog').showModal();}});
  $('refinement-cancel').onclick=()=>$('refinement-dialog').close();
  action($('refinement-confirm'),async()=>{
    const s=reviewState;if(!s)return;await finishReviewSave();
    await api('refinement-start',{project:s.pid,job:s.job.id,revision:s.revision});$('refinement-dialog').close();
    if(project?.id===s.pid){message('Separater Lauf für Kategorienvorschläge gestartet. Ergebnisse erscheinen bei den Läufen.');await refreshJobs();}
  });
}
