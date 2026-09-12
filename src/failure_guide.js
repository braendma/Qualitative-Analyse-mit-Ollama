'use strict';

// Only built-in destinations: error text never becomes a selector, URL or action.
const failureDestinations = Object.freeze({
  memory: {target:'parallel-workers',title:'Speicherbedarf verringern',text:'Weniger gleichzeitige Anfragen benötigen weniger Kontextspeicher. Alternativ kannst du ein kleineres Modell wählen. Prüfe danach die Speicherschätzung erneut. Eine Änderung gilt für einen neuen Lauf.'},
  context: {target:'num-ctx',title:'Kontextfenster und Antwortlimit prüfen',text:'Eingabe und Antwort müssen gemeinsam in das Kontextfenster passen. Vergrößere den Kontext nur, wenn Modell und Speicher dies erlauben. Das Antwortlimit nicht beliebig verkleinern: Sonst können Antworten unvollständig werden.'},
  call_budget: {target:'synthesis-max-calls',title:'Aufrufbudget der Gesamtsynthese prüfen',text:'Diese Grenze zählt Modellaufrufe für die Verdichtung, keine Token. Orientiere dich am Mindestbedarf der Fehlermeldung und berücksichtige weitere Verdichtungsrunden sowie Antwortreparaturen. Ein höheres Limit kann bei Cloud-Anbietern zusätzliche Kosten verursachen.'},
  reduction: {target:'model',title:'Modell und Verdichtung prüfen',text:'Das Modell hat die Zwischenbefunde nicht ausreichend verkürzt. Prüfe seine Eignung und die Kontextgröße. Bei wiederholtem Fehler das Modulprotokoll prüfen; ein bloßes Erhöhen des Aufrufbudgets garantiert keine erfolgreiche Verdichtung.'},
  response: {target:'max-tokens',title:'Antwortlimit und Modell prüfen',text:'Prüfe im Modulprotokoll, ob die Antwort abgeschnitten wurde oder ungültige Inhalte enthielt. Ein höheres Antwortlimit hilft nur bei zu kurzen Antworten und braucht Platz im Kontext. Bei ungültigen Belegverweisen auch Modell und strukturierte Ausgabe prüfen; Belege nicht löschen, um die Prüfung zu umgehen.'},
  credentials: {target:'provider-key',title:'Zugang beim gewählten Anbieter prüfen',text:'Prüfe Anbieter und Berechtigung des API-Schlüssels. Einen geänderten Schlüssel mit „Schlüssel speichern“ sichern, bevor du die Verbindung prüfst. Die Freigabe für Cloud-Verarbeitung bleibt unverändert; bei lokaler Verarbeitung ist kein Cloud-Schlüssel erforderlich.'},
  connection: {target:'setup-check',title:'Verbindung und Einrichtung prüfen',text:'Prüfe, ob Ollama beziehungsweise der ausgewählte Anbieter erreichbar ist. Die Systemprüfung startet keine Modellanfrage. Ein positives Ergebnis garantiert noch nicht, dass eine lange Analyseanfrage gelingt.'},
  quota: {target:'provider',title:'Kontingent beim Anbieter prüfen',text:'Prüfe Kontingent und Ratenbegrenzung im Konto des ausgewählten Anbieters. Die lokale Systemprüfung kann verfügbares Guthaben nicht zuverlässig bestätigen. Warten kann genügen; ein größeres Kontextfenster oder Aufrufbudget behebt keine Kontingentsperre.'}
});
let failureGuideContext=null;

function closeFailureGuide(){
  const previous=failureGuideContext;
  failureGuideContext=null;
  $('failure-guide').hidden=true;
  if(previous){
    previous.target.classList.remove('failure-setting-target');
    previous.target.removeAttribute('aria-describedby');
    if(previous.described)previous.target.setAttribute('aria-describedby',previous.described);
    previous.wide?.classList.remove('failure-setting-wide');
  }
}

function openFailureGuide(kind,help,job){
  if(!project || !Object.hasOwn(failureDestinations,kind))return;
  closeFailureGuide();
  const plan=failureDestinations[kind];
  let target=$(plan.target);
  // Hidden cloud controls and local parallelism never become enabled by opening help.
  if(kind==='memory' && $('provider').value!=='ollama_local')target=$('model');
  if((kind==='credentials'||kind==='quota') && (target.disabled||target.closest('fieldset[disabled]')||target.closest('[hidden]')))target=$('setup-check');
  show('analysis');
  for(let parent=target.parentElement;parent;parent=parent.parentElement){if(parent.tagName==='DETAILS')parent.open=true;}
  const guide=$('failure-guide');
  target.after(guide);
  const wide=target.parentElement.parentElement?.classList.contains('mapping')?target.parentElement:null;
  failureGuideContext={project:project.id,job:job.id,target,wide,described:target.getAttribute('aria-describedby')};
  if(wide)wide.classList.add('failure-setting-wide');
  target.classList.add('failure-setting-target');
  target.setAttribute('aria-describedby',((failureGuideContext.described||'')+' failure-guide-explanation').trim());
  $('failure-guide-title').textContent=plan.title;
  $('failure-guide-cause').textContent=help.cause||'Hinweise zum fehlgeschlagenen Modul';
  $('failure-guide-explanation').textContent=plan.text;
  $('failure-guide-result').replaceChildren();
  guide.hidden=false;
  target.focus({preventScroll:true});
  target.scrollIntoView({block:'center',behavior:'instant'});
}

function addFailureAction(box,help,job){
  if(typeof help.kind!=='string'||!Object.hasOwn(failureDestinations,help.kind))return;
  const button=el('button','Passende Einstellung öffnen','small secondary');
  button.type='button';button.setAttribute('aria-controls','failure-guide');
  button.addEventListener('click',()=>openFailureGuide(help.kind,help,job));
  box.append(button);
}

async function runFailureGuideCheck(system=false){
  const context=failureGuideContext;
  if(!context||project?.id!==context.project)return;
  const button=$(system?'failure-guide-system':'failure-guide-validate');
  button.disabled=true;
  const isCurrent=()=>failureGuideContext===context&&project?.id===context.project;
  $('failure-guide-result').textContent='Prüfung läuft …';
  try{
    if(system){
      const result=await api('setup-check',{project:context.project,model:$('model').value,selection:providerSelection()});
      if(!isCurrent())return;
      const box=$('failure-guide-result');box.replaceChildren();
      for(const check of result.checks||[])box.append(el('p',(check.ok?'✓ ':'✗ ')+check.name+': '+check.detail));
      box.append(el('p','Kein Modellaufruf. Kontingent und fachliche Antwortqualität sind damit nicht bestätigt.','hint'));
    }else{
      await saveAndValidate(context.project);
      if(!isCurrent())return;
      $('failure-guide-result').textContent='Eingaben gültig und aktuelle Einstellungen gespeichert. Kein Lauf gestartet. Bei geänderten Einstellungen anschließend „Prüfen & neuen Lauf starten“ verwenden; „Diesen Lauf fortsetzen“ behält die alten Einstellungen. Später entstehende Syntheserunden werden erst während des Laufs auf ihr Aufrufbudget geprüft.';
    }
  }catch(error){if(isCurrent())$('failure-guide-result').textContent='Prüfung nicht abgeschlossen: '+error.message;}
  finally{button.disabled=false;}
}
$('failure-guide-close').addEventListener('click',()=>{const target=failureGuideContext?.target;closeFailureGuide();target?.focus();});
$('failure-guide-validate').addEventListener('click',()=>runFailureGuideCheck());
$('failure-guide-system').addEventListener('click',()=>runFailureGuideCheck(true));
$('failure-guide-inputs').addEventListener('click',()=>show('check'));
