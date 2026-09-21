const assert=require('node:assert/strict'),R=require('../../src/preparation/reading_core');
const words=[{text:'Hallo',from:0,to:5,start:0,end:1,anchor:0,exact:true,speaker_label:'P1'},{text:'Welt',from:6,to:10,start:1,end:2,anchor:1,exact:true,speaker_label:'P2'}];
let result=R.localEditWords('Hallo Welt','Hallo 🙂 neu Welt',words);assert.equal(result[0].exact,true);assert.equal(result[1].start,null);assert.equal(result[1].exact,false);assert.equal(result[1].anchor,1);assert.equal(result.at(-1).from,13);assert.equal(result.at(-1).speaker_label,'P2');assert.equal(R.atCursor(result,14).text,'Welt');assert.equal(R.atCursor(result,100).text,'Welt');
result=R.localEditWords('Hallo Welt','Hallo Wält',words);assert.equal(result[1].end,null);assert.equal(result[1].speaker_label,'P2');assert.equal(words[1].text,'Welt');
console.log('Reading core: UTF-16 edits, conservative new-word anchors, stable source labels and cursor lookup passed.');
const grouped=R.paragraphs('Hallo Welt',words.map((w,i)=>({...w,speaker:i?'B':'A'})),10);assert.equal(grouped.text,'Hallo\n\nWelt');assert.equal(grouped.cursor,11);assert.equal(grouped.words[1].from,7);
const same=R.paragraphs('Hallo Welt',words.map(w=>({...w,speaker:'A'})),10);assert.equal(same.text,'Hallo Welt');assert.equal(same.words.length,2);
const edited=R.localEditWords('Hallo Welt','Hallo ',words);assert.equal(edited.length,1);assert.equal(edited[0].exact,true);assert.deepEqual(R.localEditWords('Hallo Welt','',words),[]);
function sample(text,keys){return Array.from(text.matchAll(/\S+/gu),(m,i)=>({text:m[0],from:m.index,to:m.index+m[0].length,speaker:keys[i],anchor:i,exact:true,start:i,end:i+1}))}
let text='Wie\n\nließ sich das Studium\n\ndann\n\nverbinden\n\nGut';let mixed=sample(text,[null,'A','A','A','A',null,'A','B']);
let smooth=R.smoothUnknownBreaks(text,mixed);assert.equal(smooth,'Wie ließ sich das Studium dann verbinden\n\nGut');assert.deepEqual(smooth.match(/\S+/g),text.match(/\S+/g));assert.equal(mixed[0].speaker,null);
let normalized=R.paragraphs('Wie ließ dann verbinden Gut',sample('Wie ließ dann verbinden Gut',[null,'A',null,'A','B']));assert.equal(normalized.text,'Wie ließ dann verbinden\n\nGut');assert.equal(normalized.words[0].speaker,null);assert.equal(normalized.words[2].speaker,null);
assert.equal(R.smoothUnknownBreaks('A\n\nB',sample('A\n\nB',['A','A'])),'A\n\nB');
console.log('Unknown inline boundaries: stable source labels, known speaker changes, explicit smoothing and preserved user paragraphs passed.');

const boundaryText='Ende Wie\n\nließ sich Studium';const boundaryWords=sample(boundaryText,['P2',null,'P1','P1','P1']);const beforeBindings=boundaryWords.map(w=>[w.speaker,w.start,w.end,w.exact]);const fixed=R.formatParagraphs(boundaryText,boundaryWords,boundaryText.indexOf('ließ')+2,true);assert.equal(fixed.text,'Ende\n\nWie ließ sich Studium');assert.equal(fixed.words[1].speaker,null);assert.deepEqual(fixed.words.map(w=>[w.speaker,w.start,w.end,w.exact]),beforeBindings);assert.equal(fixed.cursor,fixed.text.indexOf('ließ')+2);assert.equal(R.paragraphs('Ende Wie ließ',sample('Ende Wie ließ',['P2',null,'P1'])).text,'Ende\n\nWie ließ');
console.log('Known P2 -> unknown Wie -> known P1: paragraph before unknown lead-in, unchanged timing/person mappings, cursor retained.');
