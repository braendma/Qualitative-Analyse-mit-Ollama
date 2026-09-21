/* Transport boundary shared by coding and review. */
class ProjectAutosave {
 constructor(config,onStatus){this.config=config;this.onStatus=onStatus;this.revision=0;this.pending=null;this.sending=false;this.ready=false;this.key='qa-coding-'+(config?.backupKey||'standalone');this.failed=false;this.conflict=false;this.storageError=''}
 backup(project){try{localStorage.setItem(this.key,JSON.stringify({revision:this.revision,project}));this.storageError='';return true}catch(e){this.storageError=e.message;return false}}
 failure(message){this.failureReason=message;this.onStatus('NICHT auf Datenträger gespeichert: '+message+(this.storageError?' Browser-Sicherung ebenfalls fehlgeschlagen: '+this.storageError:' Browser-Sicherung bleibt erhalten.')+' Aktuellen Stand zusätzlich als JSON sichern. Bei Konflikt auch Browser-Rettung herunterladen; danach neu laden.')}
 async load(){
  let backup=null;try{backup=JSON.parse(localStorage.getItem(this.key))}catch(e){this.storageError=e.message}
  if(!this.config){this.ready=true;this.onStatus('Offline-Dateiansicht: Browser-Zwischensicherung. Für dauerhafte Speicherung JSON herunterladen oder Arbeitsserver verwenden.');return backup?.project||null}
  const response=await fetch(this.config.projectEndpoint,{cache:'no-store'});if(!response.ok)throw Error('Gespeichertes Projekt nicht erreichbar.');const v=await response.json();this.revision=v.revision;this.ready=true;
  if(backup&&Coding.canonical(backup.project)===Coding.canonical(v.project)){try{localStorage.removeItem(this.key)}catch{}backup=null}
  if(backup&&backup.revision===v.revision){this.pending=backup.project;this.onStatus('Noch nicht übertragene Browser-Eingaben wiederhergestellt.');this.flush();return backup.project}
  if(backup){this.failed=true;this.conflict=true;window.unresolvedCodingBackup=backup;this.failure('Anderer Browser-Zwischenstand vorhanden.');let current=null;try{current=JSON.parse(localStorage.getItem(this.key+'-current'))}catch{}return current?.project||v.project}
  this.onStatus(v.recovery||'Projekt vom Datenträger geladen.');return v.project
 }
 save(project){
  if(!this.ready)throw Error('Projekt wird noch geladen.');this.pending=structuredClone(project);
  // Preserve conflicting drafts across further edits and reloads.
  if(this.conflict){try{localStorage.setItem(this.key+'-current',JSON.stringify({revision:this.revision,project:this.pending}))}catch(e){this.storageError=e.message}this.failure('Speicherkonflikt besteht weiter.');return}
  this.backup(this.pending);
  if(!this.config){this.onStatus(this.storageError?'Browser-Zwischensicherung fehlgeschlagen: '+this.storageError+'. Jetzt als JSON sichern.':'Im Browser zwischengespeichert. Für eine Datei JSON herunterladen.');return}
  if(this.failed){this.failure(this.failureReason||'Vorheriger Speicherfehler besteht weiter.');return}
  this.onStatus(this.storageError?'Browser-Sicherung fehlgeschlagen; Speicherung auf Datenträger wird versucht …':'Speichert …');this.flush()
 }
 async flush(){
  if(this.sending||!this.pending||!this.config||this.failed)return;this.sending=true;const value=this.pending;this.pending=null;
  const revision=this.revision,mutation_id=crypto.randomUUID();
  try{
   const response=await fetch(this.config.projectEndpoint,{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':this.config.token},body:JSON.stringify({revision,mutation_id,project:value})});const result=await response.json();if(!response.ok)throw Error(result.error||'Speichern fehlgeschlagen');this.revision=result.revision;
   if(this.pending){this.backup(this.pending)}else{try{localStorage.removeItem(this.key)}catch{}this.onStatus('Automatisch auf Datenträger gespeichert · Revision '+this.revision);window.dispatchEvent(new Event('project-saved'))}
  }catch(e){this.pending=this.pending||value;this.failed=true;this.failure(e.message)}finally{this.sending=false;if(this.pending&&!this.failed)this.flush()}
 }
}
if(typeof module!=='undefined')module.exports=ProjectAutosave;
