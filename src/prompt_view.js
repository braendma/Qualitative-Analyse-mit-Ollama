'use strict';
let promptRequest=0,promptData=null,promptReturnFocus=null;

function closePromptView(){
  promptRequest++;promptData=null;
  if($('prompt-dialog').open)$('prompt-dialog').close();
}

function renderPromptModule(){
  const box=$('prompt-content');box.replaceChildren();
  const module=promptData?.modules.find(m=>m.id===$('prompt-module').value);
  if(!module)return;
  box.append(el('p',module.note));
  for(const template of module.templates){
    const article=el('article',undefined,'card');
    article.append(el('h3',template.key));
    for(const [key,label] of [['system','Systemanweisung'],['user','Aufgabentext']]){
      const pre=el('pre',template[key]||'In dieser Konfiguration nicht belegt.');pre.tabIndex=0;
      article.append(el('h4',label),pre);
    }
    article.append(el('p','Platzhalter: '+(template.placeholders.map(k=>'{'+k+'}').join(', ')||'keine'),'hint'));
    box.append(article);
  }
  const placeholders=new Set(module.templates.flatMap(t=>t.placeholders));
  for(const rule of promptData.rules.filter(r=>placeholders.has(r.key))){
    const detail=el('details',undefined,'card'),pre=el('pre',rule.text);pre.tabIndex=0;
    detail.append(el('summary','Gemeinsame Regel: {'+rule.key+'}'),pre);box.append(detail);
  }
}

async function showModulePrompts(module,job=null){
  const pid=needProject(),request=++promptRequest;
  promptReturnFocus=document.activeElement;promptData=null;
  $('prompt-module').replaceChildren();$('prompt-content').textContent='Vorlagen werden geladen …';
  $('prompt-source').textContent='';
  if(!$('prompt-dialog').open)$('prompt-dialog').showModal();
  try{
    const query=new URLSearchParams({project:pid});if(job)query.set('job',job);
    const data=await api('prompts?'+query);
    if(request!==promptRequest||project?.id!==pid||!$('prompt-dialog').open)return;
    promptData=data;$('prompt-source').textContent=data.source;
    for(const item of data.modules)$('prompt-module').add(new Option(item.name,item.id));
    if(data.modules.some(m=>m.id===module))$('prompt-module').value=module;
    renderPromptModule();
  }catch(error){if(request===promptRequest&&project?.id===pid)$('prompt-content').textContent='Prompt-Ansicht nicht verfügbar: '+error.message;}
}
$('prompt-module').addEventListener('change',renderPromptModule);
$('prompt-close').addEventListener('click',closePromptView);
$('prompt-dialog').addEventListener('close',()=>{promptRequest++;promptData=null;if(promptReturnFocus?.isConnected)promptReturnFocus.focus();});
