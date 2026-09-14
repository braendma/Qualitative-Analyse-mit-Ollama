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
const descendants=card=>card.children.flatMap(n=>[n,...descendants(n)]);
const fullText=card=>descendants(card).map(n=>n.text||'').join(' ');
test('series and current child keep independent denominators and original timestamps',()=>{
 const {render}=renderer(source),card=render({module:'sensitivity',phase:'repetitions',unit:'repetitions',completed:1,total:6,requests:0,series_current:{configuration_number:1,configuration_total:3,repetition_number:2,repetition_total:2,modules_completed:0,modules_total:1,state:'running',module:'blind_coding',detail:{completed:3,total:8,unit:'passages',requests:4,active_requests:1,updated_at:Date.now()/1000-240}}});
 const bars=descendants(card).filter(n=>n.tag==='progress');
 assert.deepEqual(bars.map(n=>[n.value,n.max]),[[1,6],[3,8]]);
 assert.match(fullText(card),/Einstellung: 1\/3/);assert.match(fullText(card),/Wiederholung dieser Einstellung: 2\/2/);
 assert.match(fullText(card),/4 Modellantworten/);assert.doesNotMatch(fullText(card),/0 Modellantworten/);
 assert.match(fullText(card),/seit über drei Minuten unverändert/);
});
test('unknown child totals and finishing are distinct from a zero or active request',()=>{
 const {render}=renderer(source);
 const d={module:'stability',phase:'repetitions',unit:'repetitions',completed:0,total:2,series_current:{state:'running',module:'swot',detail:{requests:5}}};
 let card=render(d);assert.equal(descendants(card).filter(n=>n.tag==='progress').length,1);assert.match(fullText(card),/keine Gesamtzahl/);
 d.series_current.state='finishing';card=render(d);assert.match(fullText(card),/Ergebnis- und Prozessprüfung folgt/);assert.equal(descendants(card).filter(n=>n.cls==='module-activity').length,0);
 d.series_current.state='unavailable';card=render(d);assert.match(fullText(card),/nicht verlässlich lesbar/);assert.doesNotMatch(fullText(card),/5 Modellantworten/);
});
test('nested private labels, impossible numbers and recursive payloads never render',()=>{
 const {render}=renderer(source),d={module:'stability',phase:'repetitions',completed:0,total:2,series_current:{configuration_number:999999999,configuration_total:999999999,state:'PRIVATE',module:'PRIVATE',name:'PRIVATE',detail:{total:8,requests:999999999,phase:'PRIVATE',unit:'PRIVATE',series_current:{module:'PRIVATE'}}}};
 let card=render(d);assert.doesNotMatch(fullText(card),/PRIVATE|999999999/);assert.equal(descendants(card).filter(n=>n.tag==='progress').length,1);
 d.series_current.state='running';d.series_current.module='swot';card=render(d);assert.doesNotMatch(fullText(card),/0 von 8/);assert.equal(descendants(card).filter(n=>n.tag==='progress').length,1);
});
