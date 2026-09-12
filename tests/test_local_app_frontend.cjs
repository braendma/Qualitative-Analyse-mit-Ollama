// Exercise the shipped browser script with delayed API replies and a minimal DOM.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function setup(){
  const nodes=new Map(), requests=[];
  function element(){return {
    value:'',hidden:false,checked:false,disabled:false,textContent:'',children:[],listeners:{},
    addEventListener(type,fn){this.listeners[type]=fn;},
    append(...children){this.children.push(...children);},
    replaceChildren(...children){this.children=children;},add(child){this.children.push(child);},
    removeAttribute(){},setAttribute(){},classList:{toggle(){}},scrollIntoView(){},
    async click(){await this.listeners.click({preventDefault(){}});}
  };}
  function node(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);}
  const context=vm.createContext({
    document:{addEventListener(){},getElementById:node,createElement:element,querySelectorAll:()=>[]},
    location:{port:'1234',hash:''},sessionStorage:{getItem:()=>''},history:{},
    Option:function(text,value){this.text=text;this.value=value;},
    setInterval(){},setTimeout(){},URL,URLSearchParams,
    fetch(url,options){return new Promise(resolve=>requests.push({url,options,reply(data){resolve({ok:true,json:async()=>data,blob:async()=>data});}}));}
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/local_app.js'),'utf8'),context);
  vm.runInContext("state={defaults:{llm:{},context:{},columns:{}},modules:[],projects:[]};project={id:'first',settings:{},uploads:{}};",context);
  return {node,requests,run:code=>vm.runInContext(code,context),loadIdentity:()=>vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/person_identity_ui.js'),'utf8'),context)};
}
const checkResult={segments:2,passages:1,persons:1,codes:1,modules:[]};
const settle=()=>new Promise(resolve=>setImmediate(resolve));

test('person grouping requires confirmation, counts unique IDs and clears approval after editing',async()=>{
  const app=setup();app.loadIdentity();
  assert.equal(app.run('personIdentityReady()'),false);
  const pending=app.node('person-preview').click();
  app.requests.find(r=>r.url==='/api/person-preview').reply({fingerprint:'first',documents:[{document:'Part A',rows:1},{document:'Part B',rows:2}]});
  await pending;
  const table=app.node('person-rows').children[0];
  for(const row of table.children.slice(1)){const input=row.children[2].children[0];input.value='P01';input.listeners.input();}
  assert.match(app.node('person-count').textContent,/2 Dokumentkennungen → 1 Personen/);
  assert.equal(app.run('personIdentityReady()'),false);
  app.node('person-confirmed').checked=true;
  assert.equal(app.run('personIdentitySettings().mapping["Part B"]'),'P01');
  table.children[1].children[2].children[0].listeners.input();
  assert.equal(app.run('personIdentityReady()'),false);
  app.run('resetPersonIdentity()');assert.equal(app.run('personIdentitySettings()'),null);
});

test('person preview response is ignored after a project switch',async()=>{
  const app=setup();app.loadIdentity();const pending=app.node('person-preview').click();
  app.run("project={id:'second',settings:{},uploads:{}};");
  app.requests.find(r=>r.url==='/api/person-preview').reply({fingerprint:'old',documents:[{document:'Old',rows:1}]});
  await pending;assert.equal(app.run('personIdentityReady()'),false);assert.equal(app.node('person-rows').children.length,0);
});

test('partial failure is visible during draining and after failure with reused work',()=>{
  const app=setup();
  for(const status of ['running','failed']){
    const card=app.run(`runCard({created:0,status:'${status}',modules:[{id:'swot',name:'SWOT'}],current:'swot',
      progress_detail:{unit:'categories',completed:3,total:8,reused:2,failed:1,requests:4}})`);
    const text=card.children.map(n=>n.textContent||'').join(' ');
    assert.match(text,/3 von 8 Kategorien/);
    assert.match(text,/2 davon aus geprüften Zwischenergebnissen/);
    assert.match(text,/1 Teilaufgabe\(n\) fehlgeschlagen/);
    assert.match(text,status==='running'?/Neue Teilaufgaben starten nicht/:/Wiederaufnahme/);
  }
});

test('runtime context block explains new inputs and a new configuration',()=>{
  const app=setup();
  const card=app.run(`runCard({created:0,status:'failed',modules:[],progress_detail:{
    context_blocked:true,context_required:33000,context_limit:16000}})`);
  const text=card.children.map(n=>n.textContent||'').join(' ');
  assert.match(text,/33000, eingestellt 16000/);
  assert.match(text,/neuen Lauf starten/);
});

test('context preflight uncertainties are visible after validating inputs',async()=>{
  const app=setup(),pending=app.run('saveAndValidate()');
  app.requests.find(r=>r.url==='/api/save').reply({...checkResult,context_check:{context:8192,answer_limit:512,note:'Konservative Grenze',checks:[],warnings:['Spätere Befunde unbekannt']}});
  await pending;
  const children=app.node('validation-result').children;
  assert.ok(children.some(n=>n.textContent==='Hinweis: Spätere Befunde unbekannt'));
});

test('parallel selection is restored per project and cloud always saves one request',()=>{
  const app=setup();
  app.run('project.settings.parallel_workers=3;loadFields();');
  assert.equal(app.node('parallel-workers').value,'3');
  app.node('provider').value='ollama_local';
  assert.equal(app.run('settings().parallel_workers'),3);
  app.node('provider').value='openai';
  assert.equal(app.run('settings().parallel_workers'),1);
});

test('a delayed validation does not modify or validate another project',async()=>{
  const app=setup(),pending=app.run('saveAndValidate()');
  app.run("project={id:'second',settings:{marker:'unchanged'},uploads:{}};");
  app.node('validation-result').hidden=true;
  app.requests.find(r=>r.url==='/api/save').reply(checkResult);
  await pending;
  assert.equal(app.run('project.settings.marker'),'unchanged');
  assert.equal(app.node('validation-result').hidden,true);
});

test('switching projects while validating never starts the other project',async()=>{
  const app=setup(),pending=app.node('start').click();
  app.run("project={id:'second',settings:{},uploads:{}};");
  app.requests.find(r=>r.url==='/api/save').reply(checkResult);
  await pending;
  assert.equal(app.requests.filter(r=>r.url==='/api/start').length,0);
  assert.match(app.node('message').textContent,/Projekt wurde/);
});

test('out-of-order project replies keep the most recently selected project',async()=>{
  const app=setup();app.node('viewer').hidden=false;
  const first=app.run("openProject('first')"),second=app.run("openProject('second')");
  app.requests.find(r=>r.url==='/api/project?project=second').reply({id:'second',name:'Second',settings:{},uploads:{}});
  await settle();
  app.requests.find(r=>r.url==='/api/jobs?project=second').reply({jobs:[],telegram:{last_status:''}});
  await second;
  app.requests.find(r=>r.url==='/api/project?project=first').reply({id:'first',name:'First',settings:{},uploads:{}});
  await first;
  assert.equal(app.run('project.id'),'second');
  assert.equal(app.node('projects').value,'second');
  assert.equal(app.node('viewer').hidden,true);
});

test('upload completion resets only the mapping for that file kind',()=>{
  const app=setup();
  app.run("project.settings={columns:{code:'custom'},book_columns:{definition:'Description'}};acceptUpload({},'first','segments');");
  assert.equal(app.run('project.settings.columns'),undefined);
  assert.equal(app.run('project.settings.book_columns.definition'),'Description');
});

test('a delayed report never replaces a newer preview or reopens a closed viewer',async()=>{
  const app=setup(),old=app.run("artifact({id:'j'},'old.txt',true)"),newer=app.run("artifact({id:'j'},'new.txt',true)");
  app.requests.find(r=>r.url.includes('name=new.txt')).reply({size:3,text:async()=>'new'});await newer;
  app.requests.find(r=>r.url.includes('name=old.txt')).reply({size:3,text:async()=>'old'});await old;
  assert.equal(app.node('viewer-name').textContent,'new.txt');
  const late=app.run("artifact({id:'j'},'late.txt',true)");app.run('closeViewer()');
  app.requests.find(r=>r.url.includes('name=late.txt')).reply({size:4,text:async()=>'late'});await late;
  assert.equal(app.node('viewer').hidden,true);
});

test('category columns are manually mapped and missing or duplicate required mappings block start',()=>{
  const app=setup();
  app.run("project.uploads={segments:{headers:['Segment','Person','Code'],rows:[]},codebook:{headers:['Code','Definition','Regeln'],rows:[]}};renderFiles();");
  assert.equal(app.node('book-columns-code').value,'');
  assert.equal(app.node('book-columns-definition').value,'');
  assert.equal(app.node('start').disabled,true);
  app.node('segment-columns-segment').value='Segment';app.node('segment-columns-person').value='Person';app.node('segment-columns-code').value='Code';
  app.node('book-columns-code').value='Code';app.node('book-columns-definition').value='Definition';
  app.run('updateStartGate()');assert.equal(app.node('start').disabled,false);
  app.node('book-columns-einschluss').value='Regeln';app.node('book-columns-ausschluss').value='Regeln';
  app.run('updateStartGate()');assert.equal(app.node('start').disabled,true);
  app.node('book-columns-ausschluss').value='';app.run('updateStartGate()');assert.equal(app.node('start').disabled,false);
  app.node('book-columns-definition').value='';app.run('updateStartGate()');assert.equal(app.node('start').disabled,true);
  assert.match(app.node('start-requirements').textContent,/Definition/);
});
