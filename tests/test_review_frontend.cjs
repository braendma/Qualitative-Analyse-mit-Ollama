const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function setup(){
  const requests=[],nodes=new Map();
  const context=vm.createContext({setTimeout,clearTimeout,
    $:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},
    api:(route,data)=>new Promise((resolve,reject)=>requests.push({route,data,resolve,reject}))});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/review_ui.js'),'utf8'),context);
  vm.runInContext("var s={pid:'p',job:{id:'j'},revision:0,pending:new Map(),rows:new Map(),saving:null,error:'',queue:{cases:[]}};",context);
  return {requests,run:code=>vm.runInContext(code,context)};
}
test('an edit made during an in-flight save survives and uses the next revision',async()=>{
  const app=setup();app.run("s.pending.set('one',{case_id:'one',note:'first'});");
  const saved=app.run('flushReview(s)');
  app.run("s.pending.set('one',{case_id:'one',note:'second'});");
  app.requests[0].resolve({revision:1});await new Promise(r=>setImmediate(r));
  assert.equal(app.requests[1].data.revision,1);assert.equal(app.requests[1].data.decision.note,'second');
  app.requests[1].resolve({revision:2});await saved;
  assert.equal(app.run('s.pending.size'),0);assert.equal(app.run('s.revision'),2);
});
test('a save conflict keeps the unsaved draft and blocks closing the review',async()=>{
  const app=setup();app.run("s.pending.set('one',{case_id:'one',note:'unsaved'});");
  const saved=app.run('flushReview(s)');app.requests[0].reject(new Error('Concurrent revision'));await saved;
  assert.equal(app.run('s.pending.size'),1);assert.match(app.run('s.error'),/Concurrent/);
  app.run('reviewState=s;');assert.throws(()=>app.run('closeReview()'),/Ungespeicherte/);
  assert.equal(app.run('reviewState===s'),true);
});
test('several pending cases are serialized instead of overwriting each other',async()=>{
  const app=setup();app.run("s.pending.set('one',{case_id:'one'});s.pending.set('two',{case_id:'two'});");
  const saved=app.run('flushReview(s)');assert.equal(app.requests.length,1);
  app.requests[0].resolve({revision:1});await new Promise(r=>setImmediate(r));
  assert.equal(app.requests[1].data.decision.case_id,'two');assert.equal(app.requests[1].data.revision,1);
  app.requests[1].resolve({revision:2});await saved;assert.equal(app.run('s.pending.size'),0);
});
