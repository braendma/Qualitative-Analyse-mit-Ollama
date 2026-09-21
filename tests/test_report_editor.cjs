const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ctx=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/report_editor.js'),'utf8'),ctx);
const create=ctx.createReportReview;
function fixture(){return {sections:[{id:'section-1',markdown:'Deutung\n> Zitat',editable_fields:{'0':{original:'Deutung',original_markdown:'Deutung',source_sha256:'bound',evidence:[{id:'S',text:'Zitat'}]}}}]};}
function change(state,extra={}){return {key:'section-1:0',source_sha256:'bound',revision:state.history.length+1,before:state.current.get('section-1:0'),after:'Korrigiert',reviewer:'Prüfer',reason:'Verneinung anhand S ergänzt',at:'2026-09-21T00:00:00Z',status:'edited',...extra};}
test('correction, reopening and restoration preserve original quotes and full history',()=>{
  const data=fixture(),original=JSON.stringify(data),s=create(data);s.append(change(s));
  const reopened=create({...data,report_review:{history:s.history}});
  assert.equal(reopened.current.get('section-1:0'),'Korrigiert');
  reopened.append(change(reopened,{after:'Deutung',reason:'Zurücksetzen'}));
  assert.equal(reopened.history.length,2);assert.equal(reopened.history[0].after,'Korrigiert');
  assert.equal(JSON.stringify(data),original);
});
test('quote edits, source mismatches, stale revisions and incomplete review are rejected',()=>{
  const s=create(fixture());
  for(const extra of [{key:'section-1:1'},{source_sha256:'other'},{before:'wrong'},{revision:5},{reason:''},{reviewer:''},{status:'auto_approved'}])assert.throws(()=>s.append(change(s,extra)));
  assert.equal(s.history.length,0);
});
test('HTML serialization cannot terminate the data script or execute entered markup',()=>{
  const text='</script><script>alert(1)</script> & \u2028';
  const encoded=ctx.reportJSON({text});assert.ok(!encoded.includes('<'));assert.equal(JSON.parse(encoded).text,text);
});
