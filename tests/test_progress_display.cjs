const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function renderer(source){
 const text=fs.readFileSync(source,'utf8');
 const el=(tag,text,cls)=>({tag,text,cls,children:[],attributes:{},append(...items){this.children.push(...items)},setAttribute(k,v){this.attributes[k]=v}});
 const context=vm.createContext({el,Date});
 vm.runInContext(text.slice(text.indexOf('function renderProgressDetails'),text.indexOf('function badge')),context);
 return {render(d,status='running'){const card=el('article');context.renderProgressDetails(card,d,status);return card;},context,el};
}
const source=process.env.PROGRESS_UI_SOURCE||path.join(__dirname,'../src/local_app.js');
const read=card=>card.children.map(n=>n.text||'').join(' ');
test('unknown totals display activity with no fake zero-percent bar',()=>{
 const {render}=renderer(source),card=render({completed:0,requests:145,request_active:true});
 assert.equal(card.children.filter(n=>n.tag==='progress').length,0);
 assert.equal(card.children.filter(n=>n.cls==='module-activity').length,1);
 assert.match(read(card),/keine Gesamtzahl/);assert.match(read(card),/145 Modellantworten/);
});
test('known steps progress independently of model responses and clamp invalid counts',()=>{
 const {render}=renderer(source),card=render({completed:2,total:3,unit:'summaries',requests:99,phase:'overall_summary'});
 assert.equal(card.children.find(n=>n.tag==='progress').value,2);
 assert.match(read(card),/2 von 3 Zusammenfassungen bearbeitet · 66 %/);
 assert.match(read(card),/Gesamtzusammenfassung erstellen/);
 assert.equal(render({completed:12,total:3}).children.find(n=>n.tag==='progress').value,3);
 assert.equal(render({completed:-2,total:3}).children.find(n=>n.tag==='progress').value,0);
});
test('stopped unknown progress does not animate or claim an active request',()=>{
 const {render}=renderer(source),card=render({requests:4,request_active:true},'failed');
 assert.equal(card.children.filter(n=>n.cls==='module-activity').length,0);
 assert.doesNotMatch(read(card),/Modellanfrage.*aktiv|vorbereitet/);
});
test('stale progress is qualified instead of diagnosed as a failure',()=>{
 const {render}=renderer(source),card=render({updated_at:Date.now()/1000-240,requests:6});
 assert.match(read(card),/seit über drei Minuten unverändert/);
 assert.match(read(card),/eine Anfrage kann länger dauern/);
});
