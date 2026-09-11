'use strict';
function providerSelection(){return {provider:$('provider').value,gdpr_relevant:$('gdpr-relevant').checked,model:$('model').value};}
function renderProvider(){
  const privateData=$('gdpr-relevant').checked, p=$('provider').value, cloud=p!=='ollama_local';
  $('cloud-fields').disabled=privateData;$('key-fields').hidden=!cloud;$('check-ollama').hidden=cloud;
  $('provider-badge').textContent=state?.providers?.[p]?.name||'Ollama · lokal';
  $('processing-badge').textContent=cloud?'Cloud freigegeben · '+$('provider-badge').textContent:'Verarbeitung auf diesem PC';
  $('provider-help').textContent=cloud?'Exakten Modellnamen aus deinem Anbieter-Konto eintragen. API-Nutzung kann kostenpflichtig sein.'+(p==='huggingface'?' Hugging Face kann Anfragen an weitere Inference Provider routen.':''):'Ollama starten und ein installiertes lokales Modell auswählen.';
  $('temperature').disabled=cloud&&!p.startsWith('ollama');$('think').disabled=$('temperature').disabled;
  const info=state?.provider_keys?.providers?.[p];
  $('provider-key-state').textContent=info?.has_key?'Schlüssel vorhanden · '+(info.persist?'unter Windows geschützt gespeichert.':'nur für diese Sitzung.'):'Noch kein Schlüssel gespeichert.';
  $('persist-provider-key').disabled=!state?.provider_keys?.can_persist;
  $('persist-provider-key').checked=Boolean(info?.persist);
  if(typeof scheduleCapacity==='function')scheduleCapacity();
}
function loadProviderFields(){
  const s=project.settings||{};$('gdpr-relevant').checked=s.gdpr_relevant!==false;
  $('provider').value=$('gdpr-relevant').checked?'ollama_local':(s.provider||'ollama_local');
  $('provider-key').value='';$('provider-key-file').value='';renderProvider();
}
$('gdpr-relevant').addEventListener('change',async()=>{
  const pid=project?.id, wanted=$('gdpr-relevant').checked;
  $('gdpr-relevant').disabled=true;
  try{
    if(!pid)throw new Error('Zuerst ein Projekt auswählen.');
    await api('privacy',{project:pid,gdpr_relevant:wanted});
    if(project?.id!==pid)return;
    project.settings.gdpr_relevant=wanted;
    if(wanted){$('provider').value='ollama_local';$('model').value=state.defaults.llm.model;project.settings.provider='ollama_local';}
    $('provider-key').value='';renderProvider();
  }catch(err){if(project?.id===pid)$('gdpr-relevant').checked=!wanted;message(err.message,true);renderProvider();}
  finally{$('gdpr-relevant').disabled=false;}
});
$('provider').addEventListener('change',()=>{
  $('provider-key').value='';$('provider-key-file').value='';$('model-list').replaceChildren();
  $('model').value=$('provider').value==='ollama_local'?state.defaults.llm.model:'';renderProvider();
});
$('provider-key-file').addEventListener('change',async()=>{
  const file=$('provider-key-file').files[0], provider=$('provider').value,pid=project?.id;
  try{if(!file)return;if(file.size>4096)throw new Error('Schlüsseldatei darf höchstens 4 KB groß sein.');
    const value=(await file.text()).trim();
    if(project?.id===pid&&$('provider').value===provider&&!$('gdpr-relevant').checked)$('provider-key').value=value;
  }catch(err){message(err.message,true);}finally{$('provider-key-file').value='';}
});
async function storeProviderKey(remove=false){
  const pid=needProject(),provider=$('provider').value;
  const values={project:pid,provider,key:remove?'':$('provider-key').value,persist:$('persist-provider-key').checked,remove};
  try{state.provider_keys=await api('provider-key',values);if(project?.id===pid&&$('provider').value===provider)renderProvider();message(remove?'API-Schlüssel entfernt.':'API-Schlüssel gespeichert.');}
  finally{$('provider-key').value='';}
}
action($('save-provider-key'),()=>storeProviderKey());action($('remove-provider-key'),()=>storeProviderKey(true));
