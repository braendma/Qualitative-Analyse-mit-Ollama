const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const setup=()=>{
 const el=(tag,text)=>({tag,text,children:[],append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items}});
 const context=vm.createContext({el,document:{createTextNode:text=>({text})}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/report_viewer.js'),'utf8'),context);
 return {el,run:context.sourceReferenceDetails};
};
const text=n=>[n.text||'',...n.children?.map(text)||[]].join(' ');
test('provenance shows exact original text as inert text and distinguishes model summary',()=>{
 const {el,run}=setup(),root=el('div');
 run(root,'**Herkunftsdetails:** `N1`',{N1:{title:'Quellengruppe 1',labels:['SWOT'],summary:'Modellbefund',note:'Keine bestätigten Belege',segment_ids:['S1','missing']}},{S1:{person:'P1',text:'<script>example</script>'}});
 assert.match(text(root),/Zwischenzusammenfassung \(Modellergebnis\)/);
 assert.match(text(root),/<script>example<\/script>/);
 assert.match(text(root),/1 referenzierte Textstellen sind/);
 assert.equal(root.children[0].tag,'details');
});
test('unresolved reference does not display a fabricated quotation',()=>{
 const {el,run}=setup(),root=el('div');run(root,'**Analytische Quellen:** UNKNOWN',{});
 assert.match(text(root),/Herkunft nicht auflösbar/);assert.match(text(root),/Kein direkt zugeordnetes Originalzitat/);
});
