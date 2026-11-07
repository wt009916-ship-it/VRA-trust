import test from 'node:test';
import assert from 'node:assert/strict';
import {createCadMonitor} from '../src/cad-current.js';
import {cadRecordMarkup} from '../src/cad-ui.js';
const id='cad_'+'a'.repeat(32), hash='h1';
const reply=(status='parsed')=>({checked_at:'2026-11-07T10:00:00Z',states:[{cad_id:id,status,inspection_hash:hash,reasons:status==='stale'?['source_unavailable']:[]}]});
const detail=()=>({cad_id:id,status:'parsed',hash,result:{quantity:24}});
const deferred=()=>{let resolve;return {promise:new Promise(r=>{resolve=r;}),resolve};};
function setup(overrides={}){
 const shown=[],unknown=[],checked=[];let reads=0;
 const m=createCadMonitor({ids:[id],fetchStates:async()=>reply(),fetchRecord:async()=>{reads++;return detail();},
 onRecord:r=>shown.push(r),onUnknown:(...args)=>unknown.push(args),onChecked:(...args)=>checked.push(args),...overrides});
 return {m,shown,unknown,checked,reads:()=>reads};
}
test('unchanged current state preserves selected detail; recovery refetches the record',async()=>{
 let state=reply();const t=setup({fetchStates:async()=>state});
 await t.m.refresh();await t.m.refresh();assert.equal(t.reads(),1);assert.equal(t.shown.length,1);
 state=reply('stale');await t.m.refresh();assert.deepEqual(t.unknown,[[id,'source_unavailable']]);
 state=reply();await t.m.refresh();assert.equal(t.reads(),2);assert.equal(t.shown.length,2);t.m.stop();
});
test('late parsed state cannot replace newer stale state',async()=>{
 const old=deferred();let calls=0;
 const t=setup({fetchStates:()=>++calls===1?old.promise:Promise.resolve(reply('stale'))});
 const first=t.m.refresh();await t.m.refresh();old.resolve(reply());await first;
 assert.equal(t.shown.length,0);assert.equal(t.reads(),0);assert.equal(t.unknown.length,1);t.m.stop();
});
test('late record cannot replace newer stale state',async()=>{
 const old=deferred(),started=deferred();let state=reply();
 const t=setup({fetchStates:async()=>state,fetchRecord:()=>{started.resolve();return old.promise;}});
 const first=t.m.refresh();await started.promise;state=reply('stale');await t.m.refresh();
 old.resolve(detail());await first;assert.equal(t.shown.length,0);assert.equal(t.unknown.length,1);t.m.stop();
});
test('timeout removes previously shown values and ignores later detail',async()=>{
 const old=deferred();let delayed=false;
 const t=setup({timeoutMs:15,fetchRecord:()=>delayed?old.promise:Promise.resolve(detail())});
 await t.m.refresh();t.m.invalidate('checking');delayed=true;await t.m.refresh();
 assert.equal(t.unknown.at(-1)[1],'verification_timeout');old.resolve(detail());await Promise.resolve();
 assert.equal(t.shown.length,1);t.m.stop();
});
test('network failure clears values and subsequent recovery requires fresh detail',async()=>{
 let fail=false;const t=setup({fetchStates:async()=>{if(fail)throw Error('offline');return reply();}});
 await t.m.refresh();fail=true;await t.m.refresh();assert.equal(t.unknown.at(-1)[1],'verification_unavailable');
 fail=false;await t.m.refresh();assert.equal(t.reads(),2);t.m.stop();
});
for(const invalid of [{states:[]},{...reply(),checked_at:'invalid'}, {...reply(),states:[{cad_id:'unexpected',status:'parsed'}]},
 {...reply(),states:[{...reply().states[0],inspection_hash:null}]}, {...reply(),states:[null]}]){
 test('malformed state reply clears values '+JSON.stringify(invalid),async()=>{
  const t=setup({fetchStates:async()=>invalid});await t.m.refresh();assert.equal(t.shown.length,0);
  assert.equal(t.unknown.at(-1)[1],'verification_unavailable');t.m.stop();
 });
}
for(const record of [{...detail(),status:'stale',result:null,stale_reasons:['source_unavailable']},
 {...detail(),hash:'changed'},{...detail(),cad_id:'different'},null]){
 test('state/detail race or malformed detail never renders '+JSON.stringify(record),async()=>{
  const t=setup({fetchRecord:async()=>record});await t.m.refresh();assert.equal(t.shown.length,0);
  assert.equal(t.unknown.length,1);t.m.stop();
 });
}
test('stopping a page prevents pending responses and future refreshes',async()=>{
 const pending=deferred();const t=setup({fetchStates:()=>pending.promise});
 const first=t.m.refresh();t.m.stop();pending.resolve(reply());await first;await t.m.refresh();
 assert.equal(t.shown.length,0);assert.equal(t.unknown.length,0);
});
test('explicit invalidation clears values and invalidates pending detail',async()=>{
 const pending=deferred(),started=deferred();
 const t=setup({fetchRecord:()=>{started.resolve();return pending.promise;}});
 const first=t.m.refresh();await started.promise;t.m.invalidate('page_hidden');pending.resolve(detail());await first;
 assert.equal(t.shown.length,0);assert.equal(t.unknown.at(-1)[1],'page_hidden');t.m.stop();
});
test('scope rejects duplicates and more than fifty IDs; empty page makes no request',async()=>{
 assert.throws(()=>createCadMonitor({ids:[id,id]}));assert.throws(()=>createCadMonitor({ids:Array.from({length:51},(_,i)=>String(i))}));
 let calls=0;const t=setup({ids:[],fetchStates:async()=>{calls++;}});await t.m.refresh();assert.equal(calls,0);t.m.stop();
});
test('stale markup discards even an accidentally supplied result and escapes source text',()=>{
 const html=cadRecordMarkup({cad_id:id,source:{name:'<img onerror=x>',hash:'abc',file_id:'file_abc'},
 status:'stale',stale_reasons:['source_binding_changed'],result:{secret_quantity:918273}},'/projects/test');
 assert.ok(!html.includes('918273'));assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));
 assert.ok(html.includes('原件与读取时的哈希不一致'));assert.ok(html.includes('数量暂不展示'));
 assert.ok(!html.includes('data-ifc-detail'));
});
