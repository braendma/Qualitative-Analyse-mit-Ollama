const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function setup(){
  const nodes=new Map(),all=[],requests=[];
  const element=tag=>{const n={tag,value:'',hidden:false,checked:false,disabled:false,textContent:'',children:[],listeners:{},attributes:{},addEventListener(k,f){this.listeners[k]=f;},append(...c){this.children.push(...c);},replaceChildren(...c){this.children=c;},add(c){this.children.push(c);},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(){},classList:{toggle(){}},scrollIntoView(){}};all.push(n);return n;};
  const node=id=>{if(!nodes.has(id)){const n=element('div');n.id=id;nodes.set(id,n);}return nodes.get(id);};
  const descend=n=>n.children.flatMap(c=>[c,...descend(c)]);
  const context=vm.createContext({document:{getElementById:node,createElement:element,addEventListener(){},querySelectorAll(selector){if(selector.startsWith('[name=module]'))return descend(node('modules')).filter(n=>n.name==='module'&&(!selector.endsWith(':checked')||n.checked));return [];}},location:{port:'1234',hash:''},sessionStorage:{getItem:()=>''},history:{},Option:function(t,v){this.text=t;this.value=v;},setInterval(){},setTimeout(){},URL,URLSearchParams,fetch(url,options){return new Promise(resolve=>requests.push({url,options,reply(data){resolve({ok:true,json:async()=>data});}}));}});
  const run=code=>vm.runInContext(code,context);
  run(fs.readFileSync(path.join(__dirname,'../src/local_app.js'),'utf8'));
  run("state={defaults:{llm:{},context:{},columns:{}},modules:[],projects:[]};project={id:'first',settings:{},uploads:{}};");
  return {node,run,requests,all,descend,read:n=>[n,...descend(n)].map(c=>c.textContent).join(' '),selectors:()=>descend(node('modules')).filter(n=>n.name==='analysis-perspective')};
}
const cap=(implemented=true)=>({eligible:true,implemented,available_modes:implemented?['qualitative','frequency','both']:['qualitative'],reason:implemented?'Unterstützt.':'Noch nicht integriert.'});
const moduleRow=(id,implemented=true,deps=[])=>({id,name:id,depends_on:deps,perspective_capability:cap(implemented)});
const load=(app,modules,settings={})=>{app.run(`state.modules=${JSON.stringify(modules)};project.settings=${JSON.stringify(settings)};loadFields();`);};
const snapshot=app=>JSON.parse(app.run('JSON.stringify(perspectiveSettings())'));

test('server capabilities control selectors; legacy unset means qualitative without mutating defaults',()=>{
 const app=setup();load(app,[moduleRow('clusterer'),moduleRow('meta_swot',false),{id:'custom',name:'custom',depends_on:[]}]);
 assert.equal(app.selectors().length,1);assert.equal(app.selectors()[0].value,'qualitative');assert.deepEqual(snapshot(app),{});
 assert.equal(app.run('Object.hasOwn(project.settings,"analysis_perspectives")'),false);
 app.run('state.defaults.analysis_perspectives={clusterer:"qualitative",meta_swot:"qualitative"};loadFields();');
 app.selectors()[0].value='both';app.selectors()[0].listeners.change();
 assert.equal(app.run('state.defaults.analysis_perspectives.clusterer'),'qualitative');
});

test('perspective change invalidates check and settings saves the new mode',()=>{
 const app=setup();load(app,[moduleRow('clusterer')]);const before=app.run('settingsRevision');
 app.node('validation-result').hidden=false;const select=app.selectors()[0];select.value='both';select.listeners.change();
 assert.ok(app.run('settingsRevision')>before);assert.equal(app.node('validation-result').hidden,true);
 assert.equal(app.run('settings().analysis_perspectives.clusterer'),'both');
});

test('disabled module selections persist and automatically required prerequisites are counted',()=>{
 const app=setup();load(app,[moduleRow('clusterer'),moduleRow('summarizer',true,['clusterer'])],{modules:['summarizer'],analysis_perspectives:{clusterer:'both'}});
 assert.match(app.read(app.node('perspective-status')),/clusterer \(Beide Perspektiven\)/);
 app.run("document.querySelectorAll('[name=module]').forEach(n=>n.checked=false);updateModuleSelection();");
 assert.equal(snapshot(app).clusterer,'both');assert.equal(app.node('perspective-status').hidden,true);
});

test('unsupported imported modes remain visible, preserved and block start until explicitly corrected',()=>{
 const app=setup();load(app,[moduleRow('meta_swot',false)],{analysis_perspectives:{meta_swot:'both'}});
 assert.match(app.read(app.node('perspective-status')),/nicht verfügbar/);assert.equal(app.node('start').disabled,true);
 assert.equal(snapshot(app).meta_swot,'both');assert.equal(app.selectors()[0].value,'__unavailable__');
 app.selectors()[0].value='qualitative';app.selectors()[0].listeners.change();
 assert.equal(snapshot(app).meta_swot,'qualitative');assert.equal(app.run('perspectiveIssue'),'');
});

test('unknown and noneligible imports can be explicitly removed without resetting unrelated fields',()=>{
 const app=setup();load(app,[moduleRow('clusterer')],{analysis_perspectives:{obsolete:'frequency',clusterer:'both'}});
 app.node('model').value='unsaved-model';app.node('context-project').value='unsaved-context';
 assert.match(app.read(app.node('perspective-status')),/obsolete/);
 const button=app.descend(app.node('perspective-status')).find(n=>n.tag==='button');button.listeners.click();
 assert.deepEqual(snapshot(app),{clusterer:'both'});assert.equal(app.node('model').value,'unsaved-model');assert.equal(app.node('context-project').value,'unsaved-context');
 assert.equal(app.run('document.querySelectorAll("[name=module]:checked").length'),1);
});

test('malformed imported mappings and per-module values are not silently discarded',()=>{
 for(const raw of [['both'],'both',false,42]){const app=setup();load(app,[moduleRow('clusterer')],{analysis_perspectives:raw});assert.deepEqual(snapshot(app),raw);assert.match(app.read(app.node('perspective-status')),/Zuordnung/);assert.equal(app.node('start').disabled,true);}
 for(const raw of [null,['both'],false,'unknown']){const app=setup();load(app,[moduleRow('clusterer')],{analysis_perspectives:{clusterer:raw}});assert.deepEqual(snapshot(app).clusterer,raw);assert.match(app.read(app.node('perspective-status')),/Ungültige/);}
 const app=setup();load(app,[moduleRow('clusterer')],{analysis_perspectives:null});assert.deepEqual(snapshot(app),{});
});

test('reused built-in ID in a custom script gets no availability override',()=>{
 const app=setup();const row=moduleRow('clusterer',false);row.script='custom.py';row.perspective_capability={eligible:false,implemented:false,available_modes:[],reason:'Eigenes Modul.'};
 load(app,[row]);assert.equal(app.selectors().length,0);
 load(app,[row],{analysis_perspectives:{clusterer:'frequency'}});assert.equal(app.selectors()[0].disabled,true);assert.match(app.read(app.node('perspective-status')),/keine Analyseperspektive/);
});

test('unknown imported HTML is rendered as text and mode availability cannot be forged by a selection event',()=>{
 const app=setup();load(app,[moduleRow('clusterer',false)],{analysis_perspectives:{clusterer:'<img src=x onerror=alert(1)>'}});
 assert.match(app.read(app.node('perspective-status')),/<img/);assert.ok(app.all.every(n=>!Object.hasOwn(n,'innerHTML')));
 app.selectors()[0].value='both';app.selectors()[0].listeners.change();assert.match(snapshot(app).clusterer,/<img/);
});

test('project reload replaces choices instead of carrying them into another project',()=>{
 const app=setup();load(app,[moduleRow('clusterer')],{analysis_perspectives:{clusterer:'both'}});
 app.run('project={id:"second",settings:{},uploads:{}};loadFields();');assert.deepEqual(snapshot(app),{});assert.equal(app.selectors()[0].value,'qualitative');
});

test('explanation covers one shared basis, variable costs, derived SWOT and distinct persons',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../src/local_app.html'),'utf8');assert.match(html,/id="perspective-help"/);assert.match(html,/Beide teilen pro Modul eine Zählbasis/);assert.match(html,/acht Aussagen und drei Personen/);assert.match(html,/SWOT-Befunde sind analytisch abgeleitet/);assert.match(html,/keine erfundenen Themenhäufigkeiten/);
 const app=setup();load(app,[moduleRow('swot')],{analysis_perspectives:{swot:'both'}});assert.match(app.read(app.node('perspective-status')),/Kontext und Reparaturen/);assert.match(app.read(app.node('perspective-status')),/Wiederholungsserien/);
});
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('a perspective edit during validation cannot validate or start the stale selection',async()=>{
 const app=setup();load(app,[moduleRow('clusterer')]);
 const pending=app.run("saveAndValidate('first')");const rejected=assert.rejects(pending,/Einstellungen während der Prüfung geändert/);await settle();
 const request=app.requests.find(r=>r.url.includes('/api/save'));assert.ok(request);
 const select=app.selectors()[0];select.value='both';select.listeners.change();
 request.reply({segments:1,persons:1,codes:1,modules:[]});await rejected;
 assert.equal(app.node('validation-result').hidden,true);assert.equal(app.requests.filter(r=>r.url.includes('/api/start')).length,0);assert.equal(snapshot(app).clusterer,'both');
});

test('verified effort displays shared bases without inventing a number of model requests',async()=>{
 const app=setup();load(app,[moduleRow('clusterer')],{analysis_perspectives:{clusterer:'both'}});
 const pending=app.run("saveAndValidate('first')");await settle();
 app.requests.find(r=>r.url.includes('/api/save')).reply({segments:1,persons:1,codes:1,modules:[],effort:{main_module_executions:1,additional_module_executions:0,total_module_executions:1,series:[],modules:[],unplanned_child_modules:[],analysis_perspectives:{additional_work_required:true,shared_assignment_bases:1,additional_frequency_interpretation_phases:1,additional_model_calls:null}}});await pending;
 assert.match(app.read(app.node('validation-result')),/1 gemeinsame Zählbasis/);assert.match(app.read(app.node('validation-result')),/zusätzlichen Modellanfragen ist vorab nicht verlässlich bekannt/);
});
