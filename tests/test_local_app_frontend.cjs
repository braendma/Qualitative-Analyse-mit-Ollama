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
    removeAttribute(){},classList:{toggle(){}},scrollIntoView(){},
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
  return {node,requests,run:code=>vm.runInContext(code,context)};
}
const checkResult={segments:2,passages:1,persons:1,codes:1,modules:[]};
const settle=()=>new Promise(resolve=>setImmediate(resolve));

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
