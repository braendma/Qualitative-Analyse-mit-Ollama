// Adjacent confirmed assignments are one speaker turn, retaining original source ranges.
const assert=require('node:assert/strict'),R=require('../../src/preparation/reading_core'),P=require('../../src/preparation/reading_people');
const text='🙂 Hallo\n\nnoch einmal\n\nAntwort';
const words=Array.from(text.matchAll(/\S+/gu),(m,i)=>({text:m[0],from:m.index,to:m.index+m[0].length,source_token_index:i,anchor:i,start:i,end:i+1,exact:true}));
let project={text,people:[{id:'a',label:'P1',name:'Alex'},{id:'b',label:'P2',name:'Alex'}],speaker_overrides:[]};
project=P.assign(project,words,0,2,'a',false,'one');project=P.assign(project,words,2,4,'a',false,'two');project=P.assign(project,words,4,5,'b',false,'three');
let applied=P.apply(words,project),merged=R.paragraphs(text,applied,text.indexOf('einmal')+3);
assert.equal(merged.text,'🙂 Hallo noch einmal\n\nAntwort');assert.equal(merged.cursor,merged.text.indexOf('einmal')+3);
assert.deepEqual(P.blocks(merged.words,R.speakerKey),[{first:0,last:4},{first:4,last:5}]);
assert.deepEqual(merged.words.map(({from,to,...w})=>w),applied.map(({from,to,...w})=>w));assert.equal(project.speaker_overrides.length,3);
assert.equal(R.paragraphs(merged.text,merged.words).text,merged.text);
assert.deepEqual(P.apply(merged.words,project).map(w=>w.person_confirmed),[true,true,true,true,true]);
// Same label/name with different IDs, actual P1/P2/P1, exclusions and unreviewed text must stay distinct.
for(const tweak of [w=>{w[2].exclude=true;w[3].exclude=true},w=>{w[2].person_confirmed=false;w[3].person_confirmed=false},w=>{w[2].assignment_needs_review=true;w[3].assignment_needs_review=true},w=>{w[2].reading_person_id='b';w[3].reading_person_id='b';w[4].reading_person_id='a'}]){
 const w=structuredClone(applied);tweak(w);assert.equal(P.blocks(w,R.speakerKey).length,3);assert.equal(R.paragraphs(text,w).text,text);
}
const within=structuredClone(applied);within[2].reading_region_id='one';within[3].reading_region_id='one';assert.equal(R.paragraphs(text,within).text,text);
const changed=R.localEditWords(text,text.replace('noch','anders'),applied),review=P.apply(changed,project);assert.equal(review[2].person_confirmed,false);assert.equal(P.blocks(review,R.speakerKey).length,3);
console.log('Same-person merge: one turn, stable words/UTF-16 cursor/audio/provenance, idempotence, exclusions, review state and genuine changes passed.');
