'use strict';
let passageDraft=null, passagePage=0;
const passageSelected=new Set();
function renderPassageCandidates(){
  const candidates=passageDraft.preview.candidates, box=$('passage-candidates');box.replaceChildren();
  candidates.slice(passagePage*10,(passagePage+1)*10).forEach(c=>{
    const card=el('article',undefined,'card');
    const label=el('label',undefined,'checkbox'),input=el('input');input.type='checkbox';input.checked=passageSelected.has(c.id);
    input.onchange=()=>{if(input.checked)passageSelected.add(c.id);else passageSelected.delete(c.id);updatePassageCount();};
    label.append(input,el('span',`Dieselbe Textstelle: ${c.person} · ${c.group||'ohne Dokumentgruppe'} · Position ${c.start}–${c.end}`));
    card.append(label,el('blockquote',c.text),el('p','Codes: '+c.codes.join(' | ')),el('p','Datenzeilen: '+c.rows.join(', '),'hint'));
    if(c.duplicate_code)card.append(el('p','Ein Code kommt mehrfach vor. Prüfe, ob es getrennte Stellen oder doppelt exportierte Codierungen sind. Es werden keine Zeilen gelöscht.','hint'));
    box.append(card);
  });
  $('passage-page').textContent=candidates.length?`Seite ${passagePage+1} von ${Math.ceil(candidates.length/10)}`:'Keine identischen Kombinationen aus Dokument, Position und Text gefunden.';
  $('passage-prev').disabled=passagePage===0;$('passage-next').disabled=(passagePage+1)*10>=candidates.length;
  updatePassageCount();
}
function updatePassageCount(){
  $('passage-count').textContent=`${passageDraft.preview.count} Codierzeilen · ${passageDraft.preview.candidates.length} ${passageDraft.preview.candidates.length===1?"mögliche Gruppe":"mögliche Gruppen"} · ${passageSelected.size} bestätigt. Nicht bestätigte Zeilen erhalten jeweils eine eigene Passage-ID.`;
}
action($('passage-prepare'),async()=>{
  const pid=needProject(),captured=settings(),input=project.uploads.segments?.id;
  const preview=await api('passage-preview',{project:pid,columns:captured.columns});
  if(project?.id!==pid||project.uploads.segments?.id!==input)return;
  passageDraft={pid,input,settings:captured,preview};passagePage=0;passageSelected.clear();
  renderPassageCandidates();$('passage-dialog').showModal();
});
$('passage-prev').onclick=()=>{passagePage--;renderPassageCandidates();};
$('passage-next').onclick=()=>{passagePage++;renderPassageCandidates();};
$('passage-cancel').onclick=()=>$('passage-dialog').close();
action($('passage-apply'),async()=>{
  const draft=passageDraft;
  if(!draft||project?.id!==draft.pid||project.uploads.segments?.id!==draft.input)throw new Error('Eingaben geändert. Vorschläge erneut laden.');
  const updated=await api('passage-apply',{project:draft.pid,settings:draft.settings,fingerprint:draft.preview.fingerprint,confirmed:[...passageSelected]});
  $('passage-dialog').close();
  if(project?.id!==draft.pid)return;
  project=updated;loadFields();$('validation-result').hidden=true;
  message('Neue Arbeitskopie mit IDs gespeichert. Originaldatei und bestehende Läufe bleiben erhalten. Jetzt Einstellungen speichern & Eingaben prüfen.');
});
