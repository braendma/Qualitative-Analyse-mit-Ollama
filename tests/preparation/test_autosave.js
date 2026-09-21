'use strict';
const assert=require('node:assert/strict'),Autosave=require('../../src/preparation/autosave'),Coding=require('../../src/preparation/coding_core');
global.Coding=Coding;global.window={dispatchEvent(){}};
const values=new Map();global.localStorage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
const response=(project,revision=0,ok=true)=>({ok,json:async()=>({project,revision,error:'Speicherkonflikt'})});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 let status='';const config={backupKey:'test',projectEndpoint:'/review-state',token:'test'};
 let calls=0;global.fetch=async()=>{calls++;return calls===1?response({decisions:[]}):response(null,0,false)};
 const a=new Autosave(config,s=>status=s);await a.load();a.save({decisions:['accept']});await tick();assert(a.failed);assert.match(status,/NICHT/);
 a.save({decisions:['reject']});await tick();assert.equal(calls,2);assert.match(status,/NICHT/);assert.match(status,/Speicherkonflikt/);assert.deepEqual(JSON.parse(values.get(a.key)).project,{decisions:['reject']});
 global.fetch=async()=>response({decisions:['disk']},2);const b=new Autosave(config,s=>status=s);await b.load();assert(b.conflict);const original=values.get(b.key);b.save({decisions:['new-local']});assert.equal(values.get(b.key),original);assert.match(status,/Speicherkonflikt/);
 const c=new Autosave(config,s=>status=s);assert.deepEqual(await c.load(),{decisions:['new-local']});assert.deepEqual(window.unresolvedCodingBackup.project,{decisions:['reject']});
 values.clear();values.set(a.key,JSON.stringify({revision:1,project:{decisions:['disk']}}));const d=new Autosave(config,s=>status=s);await d.load();assert(!d.failed);assert(!values.has(d.key));
 values.clear();let finish;calls=0;global.fetch=async(url,options)=>{calls++;if(!options?.method)return response({decisions:[]});if(calls===2)return new Promise(resolve=>finish=()=>resolve(response(null,1)));assert.equal(JSON.parse(options.body).revision,1);return response(null,2)};
 const e=new Autosave(config,s=>status=s);await e.load();e.save({decisions:['first']});e.save({decisions:['latest']});finish();await tick();assert.equal(e.revision,2);assert(!e.pending);assert(!values.has(e.key));assert.match(status,/auf Datenträger gespeichert/);
 global.localStorage.setItem=()=>{throw Error('quota')};const f=new Autosave(null,s=>status=s);await f.load();f.save({decisions:['local']});assert.match(status,/fehlgeschlagen/);
 console.log('Autosave: HTTP failure, persistent error, conflict draft retention/reload, lost response, concurrent edits and unavailable browser storage passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
