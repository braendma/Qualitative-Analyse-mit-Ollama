const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const setup=()=>{
 const el=(tag,text)=>({tag,text,children:[],append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items}});
 const context=vm.createContext({el,document:{createTextNode:text=>({text})}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/report_viewer.js'),'utf8'),context);
 return {el,run:context.sourceReferenceDetails,inline:context.reportInline,markdown:context.markdownReport};
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

test('escaped diagnostic labels are readable without becoming executable HTML or formatting',()=>{
 const {el,inline}=setup(),root=el('p');
 inline(root,'A &gt; B &amp; C \\*\\*Sondercode\\*\\* &lt;script&gt;Text&lt;/script&gt; &#128578; &amp;gt;');
 const visible=root.children.map(n=>n.text||'').join('');
 assert.equal(visible,'A > B & C **Sondercode** <script>Text</script> 🙂 &gt;');
 assert.ok(root.children.every(n=>!n.tag));
 const formatted=el('p');inline(formatted,'**A &gt; B** und `&gt;`');
 assert.equal(formatted.children.find(n=>n.tag==='strong').text,'A > B');
 assert.equal(formatted.children.find(n=>n.tag==='code').text,'&gt;');
});

test('escaped pipe stays inside its diagnostic table cell',()=>{
 const {el,markdown}=setup(),root=el('div');
 markdown('| Code | Wert |\n|---|---|\n| A \\| B &gt; C | 1 |',root);
 const table=root.children[0].children[0];
 assert.equal(table.children[1].children.length,2);
 assert.equal(text(table.children[1].children[0]).trim(),'A | B > C');
});
