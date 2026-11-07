import test from 'node:test';
import assert from 'node:assert/strict';
import {associationMarkup,createAssociationReader} from '../src/drawing-associations.js';

const id='drawingassociation_'+'a'.repeat(32),hash='b'.repeat(64);
const record=()=>({drawingassociation_id:id,hash,status:'review_required',stale_reasons:[],sources:[],reviews:{},notice:'仅标注关系',result:{relations:[],coverage:[],limitations:[]}});
const deferred=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve:v=>resolve(v)};};

test('stale view removes old annotations, numbers and report links',()=>{
 const html=associationMarkup({...record(),status:'stale',result:{relations:[{mark:'SECRET 950'}]}},'/projects/p');
 assert.ok(!html.includes('950')&&!html.includes('report.html')&&html.includes('已撤下'));
});

test('source text is escaped, conflicts cannot be confirmed and unknown is not zero',()=>{
 const r=record();r.result.relations=[{relation_id:'link_'+'c'.repeat(24),mark:'<img onerror=x>',issues:['dimension_conflict'],state:'review_required',
  observations:[],comparisons:[{role:'width',values_m:['0.9',null],state:'unknown'}]}];
 const html=associationMarkup(r,'/projects/p');
 assert.ok(!html.includes('<img')&&html.includes('&lt;img')&&html.includes('0.9 / —'));
 assert.ok(html.includes('value="association_confirmed" disabled'));
});

test('no automatic relation is not proof of no information',()=>{
 const html=associationMarkup(record(),'/projects/p');assert.ok(html.includes('不代表图纸之间没有关联'));
});

test('late response cannot resurrect invalidated data',async()=>{
 const d=deferred(),seen=[],unknown=[];
 const reader=createAssociationReader({fetchRecord:()=>d.promise,onRecord:r=>seen.push(r),onUnknown:r=>unknown.push(r)});
 const task=reader.select(id);reader.invalidate('source changed');d.resolve(record());await task;
 assert.equal(seen.length,0);assert.equal(unknown.at(-1),'source changed');reader.stop();
});

test('network failure withdraws and a new verified response restores',async()=>{
 const seen=[],unknown=[];let fail=false;
 const reader=createAssociationReader({fetchRecord:async()=>{if(fail)throw Error('offline');return record();},onRecord:r=>seen.push(r),onUnknown:r=>unknown.push(r)});
 await reader.select(id);fail=true;await reader.refresh();assert.equal(unknown.at(-1),'offline');
 fail=false;await reader.refresh();assert.equal(seen.length,2);reader.stop();
});

test('timeout withdraws and wrong identifier or stale numeric payload is refused',async()=>{
 const unknown=[],seen=[];let next=()=>new Promise(()=>{});
 const reader=createAssociationReader({fetchRecord:()=>next(),onRecord:r=>seen.push(r),onUnknown:r=>unknown.push(r),timeoutMs:8});
 await reader.select(id);assert.equal(unknown.at(-1),'核验超时');
 next=async()=>({...record(),drawingassociation_id:'other'});await reader.refresh();
 next=async()=>({...record(),status:'stale'});await reader.refresh();assert.equal(seen.length,0);reader.stop();
});

test('unchanged polls preserve review form, source staleness replaces it',async()=>{
 const seen=[];let value=record();
 const reader=createAssociationReader({fetchRecord:async()=>value,onRecord:r=>seen.push(r),onUnknown:()=>{}});
 await reader.select(id);await reader.refresh();assert.equal(seen.length,1);
 value={...value,status:'stale',result:null,stale_reasons:['drawing_changed']};await reader.refresh();assert.equal(seen.length,2);
 reader.stop();await reader.refresh();assert.equal(seen.length,2);
});
