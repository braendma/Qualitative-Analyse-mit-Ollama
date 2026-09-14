// Exercise the shipped browser script with delayed API replies and a minimal DOM.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function setup(){
  const nodes=new Map(), requests=[],timers=new Map();let timerId=0;
  function element(){return {
    value:'',hidden:false,checked:false,disabled:false,open:false,textContent:'',children:[],listeners:{},
    addEventListener(type,fn){this.listeners[type]=fn;},
    append(...children){this.children.push(...children);},
    replaceChildren(...children){this.children=children;},add(child){this.children.push(child);},
    removeAttribute(){},setAttribute(){},classList:{toggle(){}},scrollIntoView(){},
    showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();},
    async click(){await this.listeners.click({preventDefault(){}});}
  };}
  function node(id){if(!nodes.has(id)){const n=element();n.id=id;nodes.set(id,n);}return nodes.get(id);}
  const context=vm.createContext({
    document:{addEventListener(){},getElementById:node,createElement:element,querySelectorAll:()=>[]},
    location:{port:'1234',hash:''},sessionStorage:{getItem:()=>''},history:{},
    Option:function(text,value){this.text=text;this.value=value;},
    setInterval(){},setTimeout(fn){const id=++timerId;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);},URL,URLSearchParams,
    fetch(url,options){return new Promise((resolve,reject)=>requests.push({url,options,reply(data,ok=true){resolve({ok,json:async()=>data,blob:async()=>data});},fail(text='Connection failed'){reject(new Error(text));}}));}
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/local_app.js'),'utf8'),context);
  vm.runInContext("state={defaults:{llm:{},context:{},columns:{}},modules:[],projects:[]};project={id:'first',settings:{output_dir:'/synthetic/results'},uploads:{}};document.getElementById('output-dir').value=project.settings.output_dir;outputDirMode='explicit';",context);
  return {node,requests,run:code=>vm.runInContext(code,context),loadIdentity:()=>vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/person_identity_ui.js'),'utf8'),context),
    loadProviders:()=>vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/providers_ui.js'),'utf8'),context),
    flushTimers:()=>{const ready=[...timers.values()];timers.clear();for(const fn of ready)fn();}};
}
const checkResult={segments:2,passages:1,persons:1,codes:1,modules:[]};
const settle=()=>new Promise(resolve=>setImmediate(resolve));

test('an empty research destination blocks otherwise ready inputs and explicit selection clears that gate',()=>{
  const app=setup();
  app.run("project.uploads={segments:{headers:['Segment','Person','Code'],rows:[]},codebook:{headers:['Code','Definition'],rows:[]}};renderFiles();");
  app.node('segment-columns-segment').value='Segment';app.node('segment-columns-person').value='Person';app.node('segment-columns-code').value='Code';
  app.node('book-columns-code').value='Code';app.node('book-columns-definition').value='Definition';
  app.run('updateStartGate()');assert.equal(app.node('start').disabled,false);
  app.node('output-dir').value='   ';
  app.node('output-dir').listeners.input();
  assert.equal(app.node('start').disabled,true);
  assert.match(app.node('start-requirements').textContent,/Speicherort für Analyseergebnisse/);
  app.node('output-status').textContent='Previous check';
  app.node('output-dir').value='/synthetic/selected-folder';
  app.node('output-dir').listeners.input();
  assert.equal(app.node('output-status').textContent,'');
  assert.equal(app.node('start').disabled,false);
});

test('research destination is trimmed, saved and restored per project without a legacy default',async()=>{
  const app=setup();app.node('output-dir').value='  /synthetic/study results  ';
  const pending=app.run('saveAndValidate()');
  const request=app.requests.find(r=>r.url==='/api/save');
  assert.equal(JSON.parse(request.options.body).settings.output_dir,'/synthetic/study results');
  request.reply(checkResult);await pending;
  assert.equal(app.run('project.settings.output_dir'),'/synthetic/study results');
  app.run('loadFields()');assert.equal(app.node('output-dir').value,'/synthetic/study results');
  app.run("project={id:'legacy',settings:{},uploads:{}};loadFields();");
  assert.equal(app.node('output-dir').value,'');assert.equal(app.node('start').disabled,true);
  assert.equal(app.run('project.settings.output_dir'),undefined);
});

test('explicit folder check displays the verified path but does not save or start analysis',async()=>{
  const app=setup();app.node('output-dir').value=' /synthetic/chosen ';
  app.run("message('Ordner nicht vorhanden.',true)");
  const pending=app.node('output-check').click();
  const request=app.requests.find(r=>r.url==='/api/output-check');
  assert.deepEqual(JSON.parse(request.options.body),{project:'first',output_dir:'/synthetic/chosen'});
  request.reply({output_dir:'/synthetic/chosen-normalized',message:'Ordner ist beschreibbar.'});await pending;
  assert.equal(app.node('output-dir').value,'/synthetic/chosen-normalized');
  assert.equal(app.node('output-status').textContent,'Ordner ist beschreibbar.');
  assert.equal(app.node('message').textContent,'Ordner ist beschreibbar.');
  assert.equal(app.node('message').className,'');
  assert.equal(app.requests.some(r=>['/api/save','/api/start'].includes(r.url)),false);
  assert.equal(app.run('project.settings.output_dir'),'/synthetic/results');
});

test('late folder check cannot replace a newer path or another project choice',async()=>{
  for(const switchProject of [false,true]){
    const app=setup(),pending=app.node('output-check').click();
    if(switchProject)app.run("project={id:'second',settings:{output_dir:'/synthetic/second'},uploads:{}};loadFields();");
    else {app.node('output-dir').value='/synthetic/changed';app.node('output-dir').listeners.input();}
    const current=app.node('output-dir').value;app.node('output-status').textContent='Current choice';
    app.requests.find(r=>r.url==='/api/output-check').reply({output_dir:'/synthetic/stale-normalized',message:'Stale result'});
    await pending;
    assert.equal(app.node('output-dir').value,current);
    assert.equal(app.node('output-status').textContent,'Current choice');
    assert.equal(app.requests.some(r=>['/api/save','/api/start'].includes(r.url)),false);
  }
});

test('unavailable research storage explains recovery and hides resume until the folder returns',()=>{
  const app=setup();
  const allText=n=>[n,...n.children.flatMap(function visit(c){return [c,...c.children.flatMap(visit)];})].map(c=>c.textContent||'').join(' ');
  for(const status of ['paused','failed','interrupted']){
    const job={created:0,status,modules:[],research_path:'/synthetic/<img src=x>',output_error:'Ordner nicht verfügbar.'};
    const unavailable=app.run(`runCard(${JSON.stringify(job)})`),text=allText(unavailable);
    assert.match(text,/Ergebnisordner: \/synthetic\/<img src=x>/);
    assert.match(text,/ursprünglichen Ordner wieder/);
    assert.doesNotMatch(text,/Diesen Lauf fortsetzen/);
    delete job.output_error;
    assert.match(allText(app.run(`runCard(${JSON.stringify(job)})`)),/Diesen Lauf fortsetzen/);
  }
});

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
const folderReply=(path='/synthetic',more={})=>({path,parent:'/',roots:[{name:'Synthetic root',path:'/'}],directories:[],files:[],truncated:false,...more});
const lastRequest=(app,url)=>app.requests.filter(r=>r.url===url).at(-1);
async function openPicker(app,kind='directory',listing=folderReply()){
  const pending=app.run(`openLocalPicker(${JSON.stringify(kind)})`);
  lastRequest(app,'/api/local-browse').reply(listing);await pending;
}
const syntheticUpload=(name='Synthetic.csv')=>({name,count:1,headers:['Person','Segment','Code'],rows:[['P01','Synthetic statement','A']]});

test('local folder browsing navigates separately and only explicit acceptance changes the output',async()=>{
  const app=setup();await openPicker(app,'directory',folderReply('/synthetic',{directories:[{name:'Studie ä <img src=x>',path:'/synthetic/study'}]}));
  assert.equal(app.node('local-picker-dialog').open,true);
  assert.equal(app.node('output-dir').value,'/synthetic/results');
  assert.match(app.node('local-picker-list').children[0].children[0].textContent,/<img src=x>/);
  const navigate=app.node('local-picker-list').children[0].children[0].click();
  assert.equal(JSON.parse(lastRequest(app,'/api/local-browse').options.body).path,'/synthetic/study');
  lastRequest(app,'/api/local-browse').reply(folderReply('/synthetic/study'));await navigate;
  const choose=app.node('local-picker-choose').click();
  assert.deepEqual(JSON.parse(lastRequest(app,'/api/output-check').options.body),{project:'first',output_dir:'/synthetic/study'});
  lastRequest(app,'/api/output-check').reply({output_dir:'/synthetic/study',message:'Verified'});await choose;
  assert.equal(app.node('output-dir').value,'/synthetic/study');
  assert.equal(app.run('settings().output_dir_mode'),'explicit');
  assert.equal(app.node('local-picker-dialog').open,false);
  assert.equal(app.requests.some(r=>['/api/save','/api/start','/api/local-import'].includes(r.url)),false);
});

test('local picker ignores stale navigation, project changes, cancel and Escape including errors',async()=>{
  const app=setup();await openPicker(app);
  const old=app.run("browseLocal('/old')"),oldRequest=lastRequest(app,'/api/local-browse');
  const current=app.run("browseLocal('/new')");
  lastRequest(app,'/api/local-browse').reply(folderReply('/new',{truncated:true}));await current;
  oldRequest.reply(folderReply('/old',{directories:[{name:'OLD',path:'/old/sub'}]}));await old;
  assert.equal(app.node('local-picker-path').value,'/new');assert.equal(app.node('local-picker-list').children.length,0);
  assert.match(app.node('local-picker-status').textContent,/begrenzt/);
  for(const finish of ['cancel','escape','project']){
    await openPicker(app);
    const pending=app.run("browseLocal('/delayed')");
    if(finish==='cancel')await app.node('local-picker-cancel').click();
    if(finish==='escape'){app.node('local-picker-dialog').listeners.cancel();app.node('local-picker-dialog').close();}
    if(finish==='project')app.run("project={id:'second',settings:{},uploads:{}};");
    app.node('local-picker-status').textContent='Current';app.node('message').textContent='Unchanged';
    lastRequest(app,'/api/local-browse').reply({error:'STALE ERROR'},false);await pending;
    assert.equal(app.node('local-picker-status').textContent,'Current');assert.equal(app.node('message').textContent,'Unchanged');
    assert.equal(app.node('output-dir').value,'/synthetic/results');
  }
});

test('typing another path invalidates pending navigation and unavailable folders cannot be accepted',async()=>{
  const app=setup();await openPicker(app);
  const pending=app.run("browseLocal('/old')");app.node('local-picker-path').value='/typed';app.node('local-picker-path').listeners.input();
  lastRequest(app,'/api/local-browse').reply(folderReply('/old'));await pending;
  assert.equal(app.node('local-picker-path').value,'/typed');assert.equal(app.node('local-picker-choose').disabled,true);
  const newer=app.node('local-picker-open').click();lastRequest(app,'/api/local-browse').reply({error:'Kein Zugriff auf diesen Ordner'},false);await newer;
  assert.match(app.node('local-picker-status').textContent,/Kein Zugriff/);assert.equal(app.node('local-picker-choose').disabled,true);
  await app.node('local-picker-choose').click();assert.equal(app.requests.some(r=>r.url==='/api/output-check'),false);
});

test('local file selection imports only on confirmation and supplies the original folder as an automatic default',async()=>{
  const app=setup();app.node('output-dir').value='';
  await openPicker(app,'segments',folderReply('/synthetic/input',{files:[{name:'Datei ä <svg>.csv',path:'/synthetic/input/data.csv'}]}));
  await app.node('local-picker-list').children[0].children[0].click();
  assert.match(app.node('local-picker-selection').textContent,/<svg>/);assert.equal(app.requests.some(r=>r.url==='/api/local-import'),false);
  const choose=app.node('local-picker-choose').click();
  assert.equal(app.node('local-picker-cancel').disabled,true);await app.node('local-picker-cancel').click();
  let prevented=false;app.node('local-picker-dialog').listeners.cancel({preventDefault(){prevented=true;}});
  assert.equal(prevented,true);assert.equal(app.node('local-picker-dialog').open,true);
  assert.deepEqual(JSON.parse(lastRequest(app,'/api/local-import').options.body),{project:'first',kind:'segments',path:'/synthetic/input/data.csv'});
  lastRequest(app,'/api/local-import').reply({uploads:{segments:{...syntheticUpload(),source_path:'/synthetic/input/data.csv',source_directory:'/synthetic/input'}},source_path:'/synthetic/input/data.csv',suggested_output_dir:'/synthetic/input'});await choose;
  assert.equal(app.node('output-dir').value,'/synthetic/input');assert.equal(app.run('settings().output_dir_mode'),'input');
  assert.equal(app.run('project.uploads.segments.name'),'Synthetic.csv');assert.equal(app.node('preview-details').open,true);
  assert.equal(app.node('output-input-folder').disabled,false);assert.equal(app.node('local-picker-dialog').open,false);
  assert.equal(app.requests.some(r=>['/api/start','/api/save'].includes(r.url)),false);
});

test('local sheet selection reuses the dialog with canonical source and receipt without publishing client markers',async()=>{
  const app=setup();await openPicker(app,'codebook',folderReply('/synthetic',{files:[{name:'book.xlsx',path:'/synthetic/book.xlsx'}]}));
  await app.node('local-picker-list').children[0].children[0].click();const choose=app.node('local-picker-choose').click();
  lastRequest(app,'/api/local-import').reply({requires_sheet:true,sheets:['Categories','Other'],receipt:'synthetic-receipt',name:'book.xlsx',source_path:'/canonical/book.xlsx'});await choose;
  assert.equal(app.node('sheet-dialog').open,true);assert.equal(app.node('codebook-file').disabled,true);
  app.node('sheet-choice').value='Categories';const sheet=app.node('sheet-import').click();
  assert.deepEqual(JSON.parse(lastRequest(app,'/api/local-import').options.body),{project:'first',kind:'codebook',path:'/canonical/book.xlsx',receipt:'synthetic-receipt',sheet:'Categories'});
  lastRequest(app,'/api/local-import').reply({uploads:{codebook:syntheticUpload('book.xlsx')},source_path:'/canonical/book.xlsx',suggested_output_dir:'/canonical'});await sheet;
  assert.equal(app.run('project.uploads.codebook.name'),'book.xlsx');assert.equal(app.node('output-dir').value,'/synthetic/results');
  assert.equal(app.node('sheet-dialog').open,false);assert.equal(app.node('codebook-file').disabled,false);
});

test('sheet commit blocks cancellation and late failed import does not modify the next project or global message',async()=>{
  const app=setup();await openPicker(app,'segments',folderReply('/synthetic',{files:[{name:'data.xlsx',path:'/synthetic/data.xlsx'}]}));
  await app.node('local-picker-list').children[0].children[0].click();const choose=app.node('local-picker-choose').click();
  lastRequest(app,'/api/local-import').reply({requires_sheet:true,sheets:['One','Two'],receipt:'receipt',source_path:'/synthetic/data.xlsx'});await choose;
  const sheet=app.node('sheet-import').click();assert.equal(app.node('sheet-cancel').disabled,true);await app.node('sheet-cancel').click();
  let prevented=false;app.node('sheet-dialog').listeners.cancel({preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(app.node('sheet-dialog').open,true);
  app.run("project={id:'next',settings:{marker:'unchanged'},uploads:{}};");
  app.node('message').textContent='Current';lastRequest(app,'/api/local-import').reply({error:'OLD import failure'},false);await sheet;
  assert.equal(app.node('message').textContent,'Current');assert.equal(app.run('project.settings.marker'),'unchanged');
  assert.equal(app.run('Object.keys(project.uploads).length'),0);
});

test('automatic input folders track replacement local segments while explicit choices and browser uploads stay honest',()=>{
  const app=setup();app.node('output-dir').value='';
  const result=dir=>JSON.stringify({uploads:{segments:{...syntheticUpload(),source_directory:dir}},suggested_output_dir:dir});
  app.run(`acceptLocalUpload(${result('/one')},{project:'first',kind:'segments'})`);
  app.run(`acceptLocalUpload(${result('/two')},{project:'first',kind:'segments'})`);assert.equal(app.node('output-dir').value,'/two');
  app.node('output-dir').value='/chosen';app.node('output-dir').listeners.input();
  app.run(`acceptLocalUpload(${result('/three')},{project:'first',kind:'segments'})`);assert.equal(app.node('output-dir').value,'/chosen');
  app.run(`acceptBrowserUpload({segments:${JSON.stringify(syntheticUpload())}},'first','segments')`);assert.equal(app.node('output-dir').value,'/chosen');
  app.node('output-dir').value='';app.run(`acceptLocalUpload(${result('/four')},{project:'first',kind:'segments'})`);
  app.run(`acceptBrowserUpload({segments:${JSON.stringify(syntheticUpload())}},'first','segments')`);
  assert.equal(app.node('output-dir').value,'');assert.equal(app.run('settings().output_dir_mode'),'explicit');
  assert.equal(app.node('output-input-folder').disabled,true);assert.match(app.node('output-status').textContent,/ursprüngliche Ordner unbekannt/);
});

test('returning to the input folder checks availability and ignores a superseded source',async()=>{
  const app=setup();app.run(`project.uploads.segments=${JSON.stringify({...syntheticUpload(),source_directory:'/source'})};renderFiles();`);
  const first=app.node('output-input-folder').click();lastRequest(app,'/api/output-check').reply({output_dir:'/source',message:'Verified'});await first;
  assert.equal(app.node('output-dir').value,'/source');assert.equal(app.run('settings().output_dir_mode'),'input');
  const late=app.node('output-input-folder').click();app.run("project.uploads.segments.source_directory='/new-source';");
  app.node('message').textContent='Current';lastRequest(app,'/api/output-check').reply({error:'STALE'},false);await late;
  assert.equal(app.node('message').textContent,'Current');assert.equal(app.node('output-dir').value,'/source');
});

test('local roots, parent and home navigation use only the browse endpoint',async()=>{
  const app=setup();await openPicker(app);
  app.node('local-picker-roots').value='/drive';const root=app.node('local-picker-roots').listeners.change();
  assert.equal(JSON.parse(lastRequest(app,'/api/local-browse').options.body).path,'/drive');
  lastRequest(app,'/api/local-browse').reply(folderReply('/drive',{parent:null}));await root;
  assert.equal(app.node('local-picker-parent').disabled,true);
  const home=app.node('local-picker-home').click();assert.equal(JSON.parse(lastRequest(app,'/api/local-browse').options.body).path,'');
  lastRequest(app,'/api/local-browse').reply(folderReply('/home/example',{parent:'/home'}));await home;
  const parent=app.node('local-picker-parent').click();assert.equal(JSON.parse(lastRequest(app,'/api/local-browse').options.body).path,'/home');
  lastRequest(app,'/api/local-browse').reply(folderReply('/home'));await parent;
  assert.equal(app.requests.some(r=>['/api/local-import','/api/output-check','/api/save','/api/start'].includes(r.url)),false);
});

test('cancelling sheet selection before commit leaves uploads and selected destination unchanged',async()=>{
  const app=setup();await openPicker(app,'segments',folderReply('/synthetic',{files:[{name:'data.xlsx',path:'/synthetic/data.xlsx'}]}));
  await app.node('local-picker-list').children[0].children[0].click();const choose=app.node('local-picker-choose').click();
  lastRequest(app,'/api/local-import').reply({requires_sheet:true,sheets:['One','Two'],receipt:'receipt',source_path:'/synthetic/data.xlsx'});await choose;
  const before=app.requests.length;await app.node('sheet-cancel').click();
  assert.equal(app.requests.length,before);assert.equal(app.run('pendingUpload'),null);assert.equal(app.run('Object.keys(project.uploads).length'),0);
  assert.equal(app.node('output-dir').value,'/synthetic/results');assert.equal(app.node('segments-file').disabled,false);
});

test('late folder-check failures remain silent after the user chooses another destination',async()=>{
  const app=setup(),pending=app.node('output-check').click();app.node('output-dir').value='/new';app.node('message').textContent='Current';
  lastRequest(app,'/api/output-check').reply({error:'Stale folder failure'},false);await pending;
  assert.equal(app.node('message').textContent,'Current');assert.equal(app.node('output-dir').value,'/new');
});

const runtimeReply=(state='open',active=null,error='')=>({state,active,error});
const activeAttempt={project:'first',job:'synthetic-job',attempt:'attempt-1'};
async function shutdownView(app,data=runtimeReply()){
  const pending=app.node('shutdown-open').click();lastRequest(app,'/api/runtime').reply(data);await pending;
}

test('shutdown dialog reads current state and cancellation never requests shutdown',async()=>{
  const app=setup();await shutdownView(app);
  assert.equal(app.node('shutdown-dialog').open,true);assert.equal(app.node('shutdown-idle').hidden,false);
  assert.equal(app.node('shutdown-idle').disabled,false);assert.equal(app.node('shutdown-active-actions').hidden,true);
  await app.node('shutdown-cancel').click();assert.equal(app.node('shutdown-dialog').open,false);
  assert.equal(app.requests.some(r=>r.url==='/api/shutdown'),false);
  const html=fs.readFileSync(path.join(__dirname,'../src/local_app.html'),'utf8');
  assert.match(html,/Das Schließen dieses Browsertabs beendet das Programm und laufende Analysen nicht/);
});

test('idle shutdown waits for an explicit request and only confirmed closed state reports cleanup before closing',async()=>{
  const app=setup();await shutdownView(app);
  const pending=app.node('shutdown-idle').click();assert.deepEqual(JSON.parse(lastRequest(app,'/api/shutdown').options.body),{mode:'idle'});
  assert.equal(app.node('shutdown-cancel').disabled,true);
  let prevented=false;app.node('shutdown-dialog').listeners.cancel({preventDefault(){prevented=true;}});assert.equal(prevented,true);
  lastRequest(app,'/api/shutdown').reply(runtimeReply('stopping'));await pending;
  assert.match(app.node('shutdown-state').textContent,/Beenden angefordert/);
  assert.doesNotMatch(app.node('shutdown-state').textContent,/Bereinigung bestätigt/);
  assert.equal(app.node('start').disabled,true);
  const poll=app.run('refreshRuntime()');lastRequest(app,'/api/runtime').reply(runtimeReply('closed'));await poll;
  assert.match(app.node('shutdown-state').textContent,/Bereinigung bestätigt/);assert.match(app.node('shutdown-state').textContent,/Programm wird geschlossen/);assert.doesNotMatch(app.node('shutdown-state').textContent,/Programm beendet/);
});

test('pause-and-exit targets the displayed job attempt and closing the dialog does not undo the request',async()=>{
  const app=setup();await shutdownView(app,runtimeReply('open',activeAttempt));
  assert.equal(app.node('shutdown-idle').hidden,true);assert.equal(app.node('shutdown-active-actions').hidden,false);
  const pending=app.node('shutdown-pause').click();
  assert.deepEqual(JSON.parse(lastRequest(app,'/api/shutdown').options.body),{mode:'pause',...activeAttempt});
  lastRequest(app,'/api/shutdown').reply(runtimeReply('waiting_for_pause',activeAttempt));await pending;
  assert.match(app.node('shutdown-state').textContent,/aktuelle Modul wird abgeschlossen/);
  assert.equal(app.node('shutdown-pause').disabled,true);assert.equal(app.node('start').disabled,true);
  assert.equal(app.node('shutdown-cancel').textContent,'Dialog schließen');await app.node('shutdown-cancel').click();
  assert.equal(app.requests.filter(r=>r.url==='/api/shutdown').length,1);
  assert.match(app.node('runtime-status').textContent,/Pause angefordert/);
});

test('abort requires fresh explicit confirmation after the active attempt changes',async()=>{
  const app=setup();await shutdownView(app,runtimeReply('open',activeAttempt));
  await app.node('shutdown-abort').click();assert.equal(app.requests.some(r=>r.url==='/api/shutdown'),false);
  app.node('shutdown-abort-confirmed').checked=true;app.node('shutdown-abort-confirmed').listeners.change();
  const next={...activeAttempt,attempt:'attempt-2'},poll=app.run('refreshRuntime()');lastRequest(app,'/api/runtime').reply(runtimeReply('open',next));await poll;
  assert.equal(app.node('shutdown-abort-confirmed').checked,false);assert.equal(app.node('shutdown-abort').disabled,true);
  await app.node('shutdown-abort').click();assert.equal(app.requests.some(r=>r.url==='/api/shutdown'),false);
  app.node('shutdown-abort-confirmed').checked=true;app.node('shutdown-abort-confirmed').listeners.change();
  const abort=app.node('shutdown-abort').click();assert.deepEqual(JSON.parse(lastRequest(app,'/api/shutdown').options.body),{mode:'abort',...next,confirmed:true});
  lastRequest(app,'/api/shutdown').reply(runtimeReply('stopping',next));await abort;
});

test('a runtime reply requested before shutdown cannot reopen the start gate',async()=>{
  const app=setup();await shutdownView(app);
  const old=app.run('refreshRuntime()'),stale=lastRequest(app,'/api/runtime');
  const shutdown=app.node('shutdown-idle').click();lastRequest(app,'/api/shutdown').reply(runtimeReply('stopping'));await shutdown;
  stale.reply(runtimeReply());await old;
  assert.equal(app.run('runtimeState.state'),'stopping');assert.equal(app.node('start').disabled,true);
});

test('disconnect after accepted shutdown does not claim successful cleanup',async()=>{
  const app=setup();await shutdownView(app);
  const shutdown=app.node('shutdown-idle').click();lastRequest(app,'/api/shutdown').reply(runtimeReply('stopping'));await shutdown;
  const poll=app.run('pollApp()');lastRequest(app,'/api/runtime').fail();await poll;
  assert.match(app.node('runtime-status').textContent,/Beenden angefordert/);
  assert.match(app.node('runtime-status').textContent,/nicht mehr überprüfbar/);
  assert.doesNotMatch(app.node('runtime-status').textContent,/Bereinigung bestätigt|Programm beendet/);
});

test('unconfirmed shutdown failure blocks starting until a fresh server state resolves it',async()=>{
  const app=setup();await shutdownView(app);
  const shutdown=app.node('shutdown-idle').click();lastRequest(app,'/api/shutdown').fail('Network unavailable');await shutdown;
  assert.match(app.node('shutdown-state').textContent,/Beenden nicht bestätigt/);assert.equal(app.run('shutdownUncertain'),true);
  assert.equal(app.node('start').disabled,true);assert.equal(app.run('shutdownAccepted'),false);
  const refresh=app.node('shutdown-refresh').click();lastRequest(app,'/api/runtime').reply(runtimeReply('open'));await refresh;
  assert.equal(app.run('shutdownUncertain'),false);assert.equal(app.run('runtimeBlocksStart()'),false);
});

test('blocked shutdown remains visible and a shutdown during preflight prevents dispatch',async()=>{
  const app=setup();app.run(`applyRuntime(${JSON.stringify(runtimeReply('blocked',activeAttempt,'Synthetic cleanup failure'))})`);
  assert.match(app.node('runtime-status').textContent,/bleibt geöffnet/);assert.match(app.node('runtime-status').textContent,/Synthetic cleanup failure/);
  assert.equal(app.node('start').disabled,true);
  app.run(`applyRuntime(${JSON.stringify(runtimeReply())})`);
  const start=app.node('start').click();
  app.run(`applyRuntime(${JSON.stringify(runtimeReply('stopping'))})`);
  lastRequest(app,'/api/save').reply(checkResult);await start;
  assert.equal(app.requests.some(r=>r.url==='/api/start'),false);
  assert.match(app.node('message').textContent,/Programm wird beendet/);
});

test('Ollama status is a metadata-only check and leaves the selected model untouched',async()=>{
  const app=setup();app.node('provider').value='ollama_local';app.node('model').value='chosen-model';
  const checking=app.node('check-ollama').click();assert.match(app.node('ollama-status').textContent,/wird geprüft/);
  assert.equal(lastRequest(app,'/api/models').options.method,'GET');
  lastRequest(app,'/api/models').reply({models:['installed-a','installed-b']});await checking;
  assert.match(app.node('ollama-status').textContent,/Ollama erreichbar.*2 lokale Modelle/);
  assert.equal(app.node('model').value,'chosen-model');assert.equal(app.node('model-list').children.length,2);
  assert.equal(app.requests.some(r=>/model-test|start|ollama-capacity|provider-key/.test(r.url)),false);
  assert.ok(app.run('ollamaStatus.checkedAt')>0);
});

test('Ollama offline clears stale model choices, sanitizes errors and can be rechecked without installation',async()=>{
  const app=setup();app.node('provider').value='ollama_local';app.node('model').value='keep-model';
  const first=app.run('checkOllamaStatus()');lastRequest(app,'/api/models').reply({models:['old-model']});await first;
  const second=app.run('checkOllamaStatus()');lastRequest(app,'/api/models').fail('PRIVATE_NETWORK_STACK http://credential@host/');await second;
  assert.match(app.node('ollama-status').textContent,/Ollama nicht erreichbar/);
  assert.doesNotMatch(app.node('ollama-status').textContent,/PRIVATE|credential|http:/);
  assert.equal(app.node('model-list').children.length,0);assert.equal(app.node('model').value,'keep-model');
  const retry=app.node('check-ollama').click();lastRequest(app,'/api/models').reply({models:[]});await retry;
  assert.match(app.node('ollama-status').textContent,/Ollama erreichbar.*noch kein lokales Modell/);
  assert.equal(app.run('ollamaStatus.state'),'reachable');assert.equal(app.node('model').value,'keep-model');
});

test('old status replies cannot overwrite newer requests, another project or provider/host selection',async()=>{
  const app=setup();app.node('provider').value='ollama_local';
  const old=app.run('checkOllamaStatus()'),oldRequest=lastRequest(app,'/api/models');
  const newer=app.run('checkOllamaStatus()');lastRequest(app,'/api/models').reply({models:['new']});await newer;
  oldRequest.reply({models:['old']});await old;assert.equal(app.node('model-list').children[0].value,'new');
  for(const transition of ['project','provider','host']){
    app.run("project={id:'first',settings:{},uploads:{}};document.getElementById('provider').value='ollama_local';function providerSelection(){return {host:'http://127.0.0.1:11434'};}");
    const pending=app.run('checkOllamaStatus()');
    if(transition==='project')app.run("project={id:'next',settings:{},uploads:{}};");
    if(transition==='provider')app.node('provider').value='openai';
    if(transition==='host')app.run("providerSelection=()=>({host:'http://127.0.0.1:11435'});");
    app.node('ollama-status').textContent='Current status';app.node('model').value='new-choice';app.node('message').textContent='Current message';
    lastRequest(app,'/api/models').reply({error:'STALE ERROR'},false);await pending;
    assert.equal(app.node('ollama-status').textContent,'Current status');assert.equal(app.node('message').textContent,'Current message');
    assert.equal(app.node('model').value,'new-choice');
  }
});

test('offline Ollama blocks only selected local generative work, including its prerequisites',async()=>{
  const app=setup();app.node('provider').value='ollama_local';
  app.run("state.modules=[{id:'clusterer',name:'Cluster',depends_on:[],requires_model:true},{id:'summarizer',name:'Summary',depends_on:['clusterer'],requires_model:true},{id:'coverage',name:'Coverage',depends_on:[],requires_model:false}];project.uploads={segments:{headers:['Segment','Person','Code'],rows:[]},codebook:{headers:['Code','Definition'],rows:[]}};renderFiles();");
  app.node('segment-columns-segment').value='Segment';app.node('segment-columns-person').value='Person';app.node('segment-columns-code').value='Code';app.node('book-columns-code').value='Code';app.node('book-columns-definition').value='Definition';
  app.run("document.querySelectorAll=()=>[{value:'summarizer'}];updateModuleSelection();");
  const checking=app.run('checkOllamaStatus()');lastRequest(app,'/api/models').fail();await checking;
  assert.equal(app.node('start').disabled,true);assert.match(app.node('start-requirements').textContent,/erreichbares Ollama/);
  app.run("document.querySelectorAll=()=>[{value:'coverage'}];updateModuleSelection();");assert.equal(app.node('start').disabled,false);
  app.node('provider').value='openai';app.run("document.querySelectorAll=()=>[{value:'summarizer'}];updateModuleSelection();");assert.equal(app.node('start').disabled,false);
  app.node('provider').value='ollama_local';app.run('updateStartGate()');assert.equal(app.node('start').disabled,true);
  const retry=app.run('checkOllamaStatus()');lastRequest(app,'/api/models').reply({models:['installed']});await retry;assert.equal(app.node('start').disabled,false);
});

test('provider hook schedules a lightweight check after asynchronous privacy return to local',async()=>{
  const app=setup();app.loadProviders();app.node('provider').value='openai';app.node('gdpr-relevant').checked=false;
  app.run("project.settings.gdpr_relevant=false;state.defaults.llm.model='local-default';renderProvider();");app.flushTimers();
  assert.equal(app.requests.some(r=>r.url==='/api/models'),false);assert.equal(app.node('ollama-status').hidden,true);
  app.node('gdpr-relevant').checked=true;const privacy=app.node('gdpr-relevant').listeners.change();
  assert.equal(app.node('provider').value,'openai');lastRequest(app,'/api/privacy').reply({gdpr_relevant:true});await privacy;
  assert.equal(app.node('provider').value,'ollama_local');app.flushTimers();
  assert.ok(lastRequest(app,'/api/models'));lastRequest(app,'/api/models').reply({models:['local-default']});await settle();
  assert.match(app.node('ollama-status').textContent,/Ollama erreichbar/);assert.equal(app.node('ollama-status').hidden,false);
  assert.equal(app.requests.some(r=>r.url==='/api/model-test'||r.url==='/api/ollama-capacity'),false);
});

test('scheduled status does not block field rendering or repeat for an unchanged selection',async()=>{
  const app=setup();app.node('provider').value='ollama_local';app.run('loadFields()');
  assert.equal(app.node('output-dir').value,'/synthetic/results');assert.equal(app.requests.some(r=>r.url==='/api/models'),false);
  app.flushTimers();assert.equal(app.requests.filter(r=>r.url==='/api/models').length,1);
  lastRequest(app,'/api/models').reply({models:['one']});await settle();
  app.run('scheduleOllamaStatus()');app.flushTimers();assert.equal(app.requests.filter(r=>r.url==='/api/models').length,1);
});
