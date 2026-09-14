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
  function node(id){if(!nodes.has(id)){const n=element();n.id=id;nodes.set(id,n);}return nodes.get(id);}
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

test('stability estimate counts fresh prerequisites and rejects invalid selection',()=>{
  const app=setup();
  app.run("state.modules=[{id:'clusterer',name:'Cluster',depends_on:[]},{id:'blind_coding',name:'Blind',depends_on:['clusterer']},{id:'stability',name:'Stabilität',depends_on:[]}];");
  assert.equal(app.run("stabilityEstimate(state.modules,new Set(['clusterer','blind_coding','stability']),['blind_coding'],3).executions"),6);
  assert.ok(app.run("stabilityEstimate(state.modules,new Set(['stability']),['blind_coding'],3).error"));
  assert.ok(app.run("stabilityEstimate(state.modules,new Set(['stability']),['stability'],3).error"));
  assert.ok(app.run("stabilityEstimate([{id:'custom',depends_on:[],starts_child_runs:true}],new Set(['custom']),['custom'],2).error"));
  for(const count of [0,1,21,2.5,NaN])assert.ok(app.run(`stabilityEstimate(state.modules,new Set(['clusterer']),['clusterer'],${count}).error`));
});

test('sensitivity counts the baseline and each variant without recursive diagnostics',()=>{
  const app=setup();
  app.run("state.modules=[{id:'clusterer',depends_on:[]},{id:'blind_coding',depends_on:['clusterer']},{id:'sensitivity',depends_on:[]}]; var selected=new Set(['clusterer','blind_coding','sensitivity']); var variantSettings={modules:['blind_coding'],repetitions:2,variants:[{id:'warm',llm:{temperature:.2}},{id:'context',llm:{num_ctx:12000}}]};");
  assert.equal(app.run('sensitivityEstimate(state.modules,selected,variantSettings).executions'),12);
  assert.equal(app.run('sensitivityEstimate(state.modules,selected,variantSettings).total_repetitions'),6);
  assert.ok(app.run("sensitivityEstimate(state.modules,selected,variantSettings,'ollama_cloud').error"));
  assert.ok(app.run("sensitivityEstimate(state.modules,selected,{...variantSettings,variants:[]}).error"));
  assert.ok(app.run("sensitivityEstimate(state.modules,selected,{...variantSettings,variants:[{id:'baseline',llm:{temperature:.2}}]}).error"));
  assert.ok(app.run("stabilityEstimate(state.modules,selected,['sensitivity'],2).error"));
});

test('sensitivity fields preserve false thinking, zero temperature and prompt placeholders',()=>{
  const app=setup();
  const result=JSON.parse(app.run("JSON.stringify(parseSensitivityVariant('check',{think:'false',temperature:'0',num_ctx:'',model:'mock'},JSON.stringify({blind_coding:{user:'{segment}'}})))"));
  assert.equal(result.llm.think,false);assert.equal(result.llm.temperature,0);assert.equal(result.llm.model,'mock');
  assert.equal(result.prompts.blind_coding.user,'{segment}');assert.equal(result.llm.num_ctx,undefined);
  assert.throws(()=>app.run("parseSensitivityVariant('check',{},'{broken')"));
  assert.throws(()=>app.run("parseSensitivityVariant('check',{temperature:'Infinity'},'')"));
  assert.throws(()=>app.run("parseSensitivityVariant('check',{temperature:'-0.1'},'')"));
  assert.throws(()=>app.run("parseSensitivityVariant('check',{num_ctx:'12.5'},'')"));
});

test('optional diagnostics stay off by default and explain their cost',()=>{
  const app=setup();
  app.run("state.modules=[{id:'clusterer',name:'Cluster',depends_on:[]},{id:'coverage',name:'Coverage',depends_on:[],enabled:false,cost_profile:{class:'NIEDRIG',recommendation:'für iterative Arbeit geeignet',note:'Keine Modellaufrufe'}}]; loadFields();");
  const modules=app.node('modules').children;
  assert.equal(modules[0].children[0].children[0].checked,true);
  assert.equal(modules[1].children[0].children[0].checked,false);
  const text=modules[1].children[0].children[1];
  assert.ok(text.children.some(n=>n.textContent.includes('Eigenaufwand: NIEDRIG')));
  app.run("project.settings.modules=['coverage']; loadFields();");
  assert.equal(app.node('modules').children[0].children[0].children[0].checked,false);
  assert.equal(app.node('modules').children[1].children[0].children[0].checked,true);
});

test('pure diagnostics explain model-free selection but generative stages remove that claim',()=>{
  const app=setup();
  app.run("state.modules=[{id:'clusterer',depends_on:[]},{id:'information_loss',depends_on:[],requires_model:false}]; document.querySelectorAll=()=>[{value:'information_loss'}]; updateModuleSelection();");
  assert.match(app.node('module-selection').textContent,/Kein Modell oder API-Schlüssel nötig/);
  app.run("document.querySelectorAll=()=>[{value:'information_loss'},{value:'clusterer'}]; updateModuleSelection();");
  assert.doesNotMatch(app.node('module-selection').textContent,/Kein Modell oder API-Schlüssel nötig/);
});

test('codebook diagnostic selection exposes synthetic help and model-free scope',()=>{
  const app=setup();
  app.run("state.modules=[{id:'codebook_diagnostics',name:'Codebook-Diagnostik',depends_on:[],requires_model:false,enabled:false}]; loadFields();");
  const option=app.node('modules').children[0];
  assert.equal(option.children[0].children[0].checked,false);
  assert.match(app.run('moduleHelp.codebook_diagnostics'),/Ändert keine Codes/);
  app.run("project.settings.modules=['codebook_diagnostics']; document.querySelectorAll=()=>[{value:'codebook_diagnostics'}]; loadFields(); updateModuleSelection();");
  assert.equal(app.node('modules').children[0].children[0].children[0].checked,true);
  assert.match(app.node('module-selection').textContent,/Kein Modell oder API-Schlüssel nötig/);
});

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


test('unclassified extensions and cost text stay understandable without HTML injection',()=>{
  const app=setup();
  app.run("state.modules=[{id:'custom',name:'Eigenes Modul',depends_on:[],cost_profile:null}]; loadFields();");
  const label=app.node('modules').children[0].children[0].children[1];
  assert.ok(label.children.some(n=>n.textContent.includes('nicht eingestuft')));
  app.run("state.modules[0].cost_profile={class:'HOCH',recommendation:'<img src=x>',note:'Eigenes Profil'}; loadFields();");
  const revised=app.node('modules').children[0].children[0].children[1];
  assert.ok(revised.children.some(n=>n.textContent.includes('<img src=x>')));
});


function moduleSelectors(app){
  app.run(`document.querySelectorAll=selector=>{
    const match=selector.match(/^\\[name=([^\\]]+)\\](:checked)?$/);if(!match)return [];
    const all=[],visit=n=>{if(n.name===match[1])all.push(n);for(const c of n.children||[])visit(c);};
    for(const id of ['modules','stability-targets','sensitivity-targets'])visit(document.getElementById(id));
    return all.filter(n=>!match[2]||n.checked);
  };`);
}
function finalModules(app){
  app.run(`state.modules=[{id:'clusterer',name:'Cluster',depends_on:[],requires_model:true},
    {id:'blind_coding',name:'Blind',depends_on:['clusterer'],requires_model:true},
    ...['coverage','information_loss','codebook_diagnostics','stability','sensitivity'].map(id=>({id,name:id,enabled:false,depends_on:[],requires_model:['stability','sensitivity'].includes(id),starts_child_runs:['stability','sensitivity'].includes(id)}))];
    state.defaults.stability={modules:['blind_coding'],repetitions:3};
    state.defaults.sensitivity={modules:['blind_coding'],repetitions:2,variants:[]};`);
}

test('combined effort counts each prerequisite per repetition and both independent series',()=>{
  const app=setup();finalModules(app);
  app.run(`var selected=new Set(state.modules.map(m=>m.id));var plans={
    stability:stabilityEstimate(state.modules,selected,['blind_coding'],3),
    sensitivity:sensitivityEstimate(state.modules,selected,{modules:['blind_coding'],repetitions:2,variants:[{id:'warm',llm:{temperature:.2}}]})};
    var combined=workflowEffort(state.modules,plans);renderEffortSummary(document.getElementById('effort-preview'),combined);`);
  assert.equal(app.run('combined.total_module_executions'),21);
  assert.equal(app.run('combined.additional_module_executions'),14);
  assert.equal(app.run("combined.modules.find(m=>m.id==='clusterer').total"),8);
  assert.equal(app.run('combined.model_calls_estimate'),null);
  assert.ok(app.node('effort-preview').children.some(n=>n.textContent.includes('Modulausführungen sind keine Modellanfragen')));
  assert.ok(app.run("workflowEffort(state.modules,{sensitivity:{error:'Varianten fehlen'}}).error"));
  assert.equal(app.run("workflowEffort([{id:'custom',name:'Custom',starts_child_runs:true}]).total_module_executions"),null);
  assert.equal(app.run("workflowEffort(state.modules.filter(m=>m.requires_model===false)).model_calls_estimate"),0);
});

test('final validation is explicit, preserves variants and never saves or starts by itself',async()=>{
  const app=setup();finalModules(app);moduleSelectors(app);app.run('loadFields()');
  assert.equal(app.run("document.querySelectorAll('[name=module]:checked').length"),2);
  app.run("project.settings.sensitivity={modules:['blind_coding'],repetitions:4,variants:[{id:'warm',llm:{temperature:.2,think:false}}]};loadFields();");
  const before=app.run('JSON.stringify(sensitivitySettings())'),requestsBefore=app.requests.length;
  await app.node('final-validation').click();
  assert.equal(app.run("document.querySelectorAll('[name=module]:checked').length"),7);
  assert.equal(app.run('JSON.stringify(sensitivitySettings())'),before);
  assert.equal(app.requests.length,requestsBefore);
  assert.equal(app.node('preset-status').hidden,false);
  assert.match(app.node('preset-status').textContent,/noch nicht gespeichert oder gestartet/);
  const once=app.run("JSON.stringify([...document.querySelectorAll('[name=module]:checked')].map(n=>n.value))");
  await app.node('final-validation').click();
  assert.equal(app.run("JSON.stringify([...document.querySelectorAll('[name=module]:checked')].map(n=>n.value))"),once);
  assert.equal(app.run('JSON.stringify(sensitivitySettings())'),before);
});

test('preset suggests a target for empty selections but missing variants still block start',async()=>{
  const app=setup();finalModules(app);moduleSelectors(app);
  app.run('state.defaults.stability.modules=[];state.defaults.sensitivity.modules=[];loadFields();');
  await app.node('final-validation').click();
  assert.equal(app.run("stabilitySettings().modules[0]"),'blind_coding');
  assert.equal(app.run("sensitivitySettings().modules[0]"),'blind_coding');
  assert.equal(app.node('start').disabled,true);
  assert.match(app.node('start-requirements').textContent,/Varianten/);
  assert.equal(app.run('sensitivityRows.length'),0);
  app.run("document.querySelectorAll('[name=module]').forEach(n=>n.checked=n.value==='coverage');updateModuleSelection();");
  assert.equal(app.run('sensitivityIssue'),'');
  assert.equal(app.run('stabilityIssue'),'');
  assert.equal(app.node('validation-result').hidden,true);
  assert.throws(()=>app.run("finalValidationSelection([],[],[],[])"));
});


test('changing the preset during preflight cannot start an outdated expensive selection',async()=>{
  const app=setup();finalModules(app);moduleSelectors(app);app.run('loadFields()');
  const pending=app.node('start').click();
  const save=app.requests.find(r=>r.url==='/api/save');assert.ok(save);
  await app.node('final-validation').click();
  save.reply(checkResult);await pending;
  assert.equal(app.requests.some(r=>r.url==='/api/start'),false);
  assert.equal(app.node('validation-result').hidden,true);
  assert.equal(app.node('start').disabled,true);
  assert.equal(app.run("document.querySelectorAll('[name=module]:checked').length"),7);
});
