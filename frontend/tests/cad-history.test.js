import test from 'node:test';
import assert from 'node:assert/strict';
import {createCadHistory} from '../src/cad-history.js';
const records=(n=20)=>Array.from({length:n},(_,i)=>({cad_id:'cad_'+i.toString(16).padStart(32,'0'),source:{name:'source.ifc'}}));
const response=(next=80,n=20)=>({records:records(n),snapshot:100,next_before:next,limit:20});
const pending=()=>{let resolve;return {promise:new Promise(r=>{resolve=r;}),resolve};};
function setup(fetchPage,extra={}){const events=[];const h=createCadHistory({fetchPage,onLoading:()=>events.push('clear'),onPage:(r,p)=>events.push(p),onError:e=>events.push(e.message),...extra});return {h,events};}
test('keyset pages refetch previous details and retain membership; reset removes snapshot',async()=>{
 const queries=[];const t=setup(async q=>{queries.push(q);return response(q.before===80?null:80,q.before===80?3:20);});
 await t.h.reset();await t.h.next();await t.h.previous();await t.h.reset();
 assert.deepEqual(queries,[{before:null,snapshot:null,limit:20},{before:80,snapshot:100,limit:20},{before:null,snapshot:100,limit:20},{before:null,snapshot:null,limit:20}]);
 assert.deepEqual(t.events.filter(x=>typeof x==='object').map(x=>x.page),[0,1,0,0]);t.h.stop();
});
test('late response after reset cannot restore a stale page',async()=>{
 const wait=pending();let n=0;const t=setup(()=>++n===1?wait.promise:Promise.resolve(response(null,1)));
 const first=t.h.reset();await t.h.reset();wait.resolve(response());await first;
 assert.equal(t.events.filter(x=>typeof x==='object').length,1);t.h.stop();
});
test('failure clears displayed scope and reset can recover',async()=>{
 let fail=false;const t=setup(async()=>{if(fail)throw Error('offline');return response();});
 await t.h.reset();fail=true;await t.h.next();assert.deepEqual(t.events.slice(-2),['clear','offline']);
 fail=false;await t.h.reset();assert.equal(t.events.at(-1).page,0);t.h.stop();
});
test('timeout clears data and late promise cannot revive it',async()=>{
 const wait=pending();const t=setup(()=>wait.promise,{timeoutMs:5});await t.h.reset();wait.resolve(response());
 await Promise.resolve();assert.equal(t.events.filter(x=>typeof x==='object').length,0);assert.match(t.events.at(-1),/超时/);t.h.stop();
});
test('disposed workspace ignores pending responses and further loads',async()=>{
 const wait=pending();const t=setup(()=>wait.promise);const task=t.h.reset();t.h.stop();wait.resolve(response());await task;await t.h.reset();assert.deepEqual(t.events,['clear']);
});
for(const bad of [{...response(),records:records(21)},{...response(),records:[...records(1),...records(1)]},{...response(),next_before:101},{...response(),snapshot:null},{...response(),next_before:0},response(80,1)]){
 test('invalid page never reaches display '+JSON.stringify(bad).slice(-50),async()=>{
  const t=setup(async()=>bad);await t.h.reset();assert.equal(t.events.filter(x=>typeof x==='object').length,0);assert.match(t.events.at(-1),/不完整/);t.h.stop();
 });
}
test('continuation rejects changed snapshot or nonadvancing cursor',async()=>{
 for(const next of [{...response(60),snapshot:101},response(80)]){
  let n=0;const t=setup(async()=>++n===1?response():next);await t.h.reset();await t.h.next();assert.match(t.events.at(-1),/不完整/);t.h.stop();
 }
});
