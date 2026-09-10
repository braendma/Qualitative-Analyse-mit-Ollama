'use strict';
// Rendering uses text nodes only. Raw HTML, remote images and executable links stay inert.
function reportInline(node,text){
  const pattern=/(\*\*([^*]+)\*\*|`([^`]+)`)/g;let end=0,match;
  while((match=pattern.exec(text))){node.append(document.createTextNode(text.slice(end,match.index)));node.append(el(match[2]?'strong':'code',match[2]||match[3]));end=pattern.lastIndex;}
  node.append(document.createTextNode(text.slice(end)));
}
function markdownReport(text,root){
  root.replaceChildren();const lines=text.split(/\r?\n/);let fenced=false,code=[];
  const cells=line=>line.replace(/^\s*\||\|\s*$/g,'').split(/(?<!\\)\|/).map(x=>x.trim().replace(/\\\|/g,'|'));
  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    if(/^\s*```/.test(line)){if(fenced){root.append(el('pre',code.join('\n')));code=[];}fenced=!fenced;continue;}
    if(fenced){code.push(line);continue;}
    if(!line.trim())continue;
    if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){
      const table=el('table'),head=el('tr');cells(line).forEach(x=>{const n=el('th');reportInline(n,x);head.append(n);});table.append(head);i++;
      while(i+1<lines.length&&lines[i+1].includes('|')&&lines[i+1].trim()){const row=el('tr');cells(lines[++i]).forEach(x=>{const n=el('td');reportInline(n,x);row.append(n);});table.append(row);}
      const wrap=el('div',undefined,'table-wrap');wrap.append(table);root.append(wrap);continue;
    }
    const heading=line.match(/^(#{1,6})\s+(.+)/),item=line.match(/^\s*[-*]\s+(.+)/);
    const node=el(heading?'h'+Math.min(heading[1].length+1,6):line.startsWith('>')?'blockquote':'p');
    reportInline(node,heading?heading[2]:item?'• '+item[1]:line.replace(/^>\s?/,''));root.append(node);
  }
  if(code.length)root.append(el('pre',code.join('\n')));
}
function searchableRows(rows,root){
  root.replaceChildren();const input=el('input'),label=el('label','Tabelle durchsuchen'),body=el('div'),navigation=el('div',undefined,'actions');
  input.type='search';label.append(input);root.append(label,body,navigation);let page=0;
  const display=x=>typeof x==='object'?JSON.stringify(x):String(x??'');
  const indexed=rows.map(r=>({row:r,text:JSON.stringify(r).toLocaleLowerCase('de-DE')}));
  function draw(){
    const found=indexed.filter(r=>r.text.includes(input.value.toLocaleLowerCase('de-DE'))),count=Math.max(1,Math.ceil(found.length/50));page=Math.min(page,count-1);
    const keys=[...new Set(found.slice(page*50,page*50+50).flatMap(r=>Object.keys(r.row)))];body.replaceChildren();navigation.replaceChildren();
    const table=el('table'),head=el('tr');keys.forEach(k=>head.append(el('th',k)));table.append(head);
    found.slice(page*50,page*50+50).forEach(({row})=>{const tr=el('tr');keys.forEach(k=>tr.append(el('td',display(row[k]))));table.append(tr);});
    const wrap=el('div',undefined,'table-wrap');wrap.append(table);body.append(wrap);
    for(const [text,delta,disabled] of [['Zurück',-1,page===0],['Weiter',1,page===count-1]]){const b=el('button',text,'secondary small');b.disabled=disabled;b.onclick=()=>{page+=delta;draw();};navigation.append(b);}
    navigation.append(el('span',`${found.length} Zeilen · Seite ${page+1} von ${count}`));
  }
  input.oninput=()=>{page=0;draw();};draw();
}
