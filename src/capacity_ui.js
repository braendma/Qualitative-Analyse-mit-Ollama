'use strict';
let capacityRevision=0, capacityTimer;
function capacitySnapshot(){
  return JSON.stringify({project:project?.id,provider:$('provider').value,model:$('model').value,
    context:$('num-ctx').value,private:$('gdpr-relevant').checked});
}
function scheduleCapacity(){
  capacityRevision++;clearTimeout(capacityTimer);
  const local=$('provider').value==='ollama_local';
  $('capacity-panel').hidden=!local;
  $('parallel-workers').disabled=!local;
  $('capacity-result').textContent='Modell und Kontextfenster wählen. Die Prüfung startet kein Modell.';
  if(local && $('model').value.trim())capacityTimer=setTimeout(checkCapacity,650);
}
async function checkCapacity(){
  if($('provider').value!=='ollama_local')return;
  const revision=++capacityRevision, snapshot=capacitySnapshot();
  $('capacity-result').textContent='Freien Speicher und lokale Modellmetadaten prüfen …';
  try{
    const result=await api('ollama-capacity',{selection:{...providerSelection(),num_ctx:Number($('num-ctx').value)}});
    if(revision!==capacityRevision || snapshot!==capacitySnapshot())return;
    const gib=value=>(value/1073741824).toLocaleString('de-DE',{maximumFractionDigits:1});
    const lines=[result.reason,`Modell: ${result.model} · Kontext: ${result.num_ctx.toLocaleString('de-DE')} Tokens · Stand: ${new Date(result.checked_at*1000).toLocaleTimeString('de-DE')}`];
    for(const gpu of result.hardware.gpus)lines.push(`${gpu.name}: ${gib(gpu.free_bytes)} von ${gib(gpu.total_bytes)} GiB VRAM frei`);
    if(result.hardware.ram_available_bytes!=null)lines.push(`RAM verfügbar: ${gib(result.hardware.ram_available_bytes)} GiB (CPU-Auslagerung nicht mitgerechnet)`);
    const box=$('capacity-result');box.replaceChildren();
    for(const line of lines){const p=document.createElement('p');p.textContent=line;box.append(p);}
    const details=document.createElement('details'), summary=document.createElement('summary');
    summary.textContent='Berechnung und Grenzen';details.append(summary);
    for(const note of result.notes){const p=document.createElement('p');p.textContent=note;details.append(p);}
    box.append(details);
  }catch(error){
    if(revision===capacityRevision && snapshot===capacitySnapshot())$('capacity-result').textContent='Nicht bestimmbar: '+error.message;
  }
}
for(const id of ['model','num-ctx'])$(id).addEventListener('input',scheduleCapacity);
for(const id of ['provider','gdpr-relevant'])$(id).addEventListener('change',scheduleCapacity);
$('capacity-check').addEventListener('click',checkCapacity);
