const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ctx=vm.createContext({});vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/report_editor.js'),'utf8'),ctx);
function fixture(){
 const section=(id,module,topic,quote)=>({id,module_id:module,title:module,markdown:module,editable_fields:{0:{original:module,original_markdown:module,source_sha256:module,topic_id:topic,evidence:quote?[{id:quote,text:'Original '+quote}]:[]}}});
 return {sections:[section('a','swot','T','S'),section('b','meta','other','S'),section('c','synthesis','T','Z'),section('d','unrelated','T','Z')],review_dependencies:{swot:[],meta:['swot'],synthesis:['meta'],unrelated:[]}};
}
function edit(s,key='a:0',after='Menschliche Deutung'){return s.append({key,source_sha256:s.fields.get(key).source_sha256,revision:s.history.length+1,before:s.current.get(key),after,reviewer:'Mensch',reason:'Kontextumkehr',status:'reviewed',at:'2026-09-21'});}
test('shared evidence and transitive downstream links, no invented cross-module topic identity',()=>{
 const data=fixture(),before=JSON.stringify(data),s=ctx.createReportReview(data),links=s.related('a:0');
 assert.deepEqual(Array.from(links,x=>x.target).sort(),['b:0','section:b','section:c']);
 assert.match(links[0].reasons[0],/Originalzitate/);assert.equal(JSON.stringify(data),before);
});
test('missing evidence does not imply no dependencies; cycles terminate and conflicting quote text is not a match',()=>{
 const data=fixture();data.sections[1].editable_fields[0].evidence[0].text='Widerspruch';data.review_dependencies.swot=['synthesis'];
 const s=ctx.createReportReview(data);assert.deepEqual(Array.from(s.related('a:0'),x=>x.target),['section:b','section:c']);
});
test('acknowledgement requires explicit review, persists offline, and later source edit reopens tasks',()=>{
 const data=fixture(),s=ctx.createReportReview(data);edit(s);const task=s.tasks()[0];
 assert.ok(s.tasks().every(t=>!t.checked));assert.throws(()=>s.check({id:task.id,reviewer:'',reason:'x',at:'today'}));
 s.check({id:task.id,reviewer:'A',reason:'Empfehlung bleibt passend',at:'today'});
 const reopened=ctx.createReportReview({...data,report_review:{history:s.history,related_checks:s.checks}});
 assert.equal(reopened.tasks()[0].checked,true);edit(reopened,'a:0','Zweite Korrektur');
 assert.ok(reopened.tasks().every(t=>!t.checked));assert.throws(()=>reopened.check({id:task.id,reviewer:'A',reason:'alt',at:'today'}));
 assert.equal(reopened.checks.length,1);
});
test('target edits invalidate previous checks; restoring original still triggers review; status only does not',()=>{
 const s=ctx.createReportReview(fixture());edit(s);const t=s.tasks()[0];s.check({id:t.id,reviewer:'A',reason:'okay',at:'today'});
 edit(s,'b:0','Neue Folgedeutung');assert.equal(s.tasks().find(x=>x.source==='a:0'&&x.target==='b:0').checked,false);
 edit(s,'a:0','swot');assert.ok(s.tasks().some(x=>x.source==='a:0'&&x.revision===3));
 const n=s.tasks().length;edit(s,'a:0','swot');assert.equal(s.tasks().length,n);assert.ok(s.tasks().some(x=>x.source==='a:0'&&x.revision===3));
});
test('same topic within module connects even without quote; legacy reports degrade honestly',()=>{
 const data=fixture();data.sections[0].markdown+='\nWeitere Deutung';data.sections[0].editable_fields[1]={original:'Weitere Deutung',original_markdown:'Weitere Deutung',source_sha256:'next',topic_id:'T',evidence:[]};
 assert.ok(ctx.createReportReview(data).related('a:0').some(x=>x.target==='a:1'));
 delete data.review_dependencies;for(const s of data.sections)delete s.module_id;
 assert.ok(ctx.createReportReview(data).related('a:0').some(x=>x.target==='b:0'));
});
test('exact SWOT registry link points to one Meta element instead of its whole module',()=>{
 const data=fixture();data.sections[0].editable_fields[0].item_id='swot-finding:exact';
 data.sections[1].editable_fields[0].parent_items=[{id:'swot-finding:exact',reference:'S0001'}];
 const s=ctx.createReportReview(data),links=s.related('a:0');
 assert.ok(links.some(x=>x.target==='b:0'&&x.reasons.some(r=>r.includes('S0001'))));
 assert.ok(!links.some(x=>x.target==='section:b'));assert.ok(links.some(x=>x.target==='section:c'));
 assert.ok(!links.some(x=>x.target==='d:0'));
 assert.ok(s.related('b:0').some(x=>x.target==='a:0'&&x.reasons.some(r=>r.includes('Zugrunde liegender'))));
});
test('explicit contrast and ambiguity relations work without any shared quote',()=>{
 const data=fixture(),section=data.sections[0];section.markdown+='\nGegenfall';
 section.editable_fields[0].related_topic_ids=['C'];section.editable_fields[1]={original:'Gegenfall',original_markdown:'Gegenfall',source_sha256:'case',topic_id:'C',evidence:[]};
 let state=ctx.createReportReview(data);assert.ok(state.related('a:0').find(x=>x.target==='a:1').reasons.some(r=>r.includes('Gegenfall')));
 delete section.editable_fields[0].related_topic_ids;for(const f of Object.values(section.editable_fields))f.related_pair_id='pair';
 state=ctx.createReportReview(data);assert.ok(state.related('a:0').find(x=>x.target==='a:1').reasons.some(r=>r.includes('Ambivalenzpaar')));
});
