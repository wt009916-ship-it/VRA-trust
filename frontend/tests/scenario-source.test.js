import test from 'node:test';
import assert from 'node:assert/strict';
import {createScenarioSourceGuard,scenarioSourceMatches} from '../src/scenario-source.js';
const source={takeoff_id:'t1',hash:'record-hash',status:'measured',result:{status:'measured',layers:[{layer_id:3}]}};
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {resolve,promise};};
function setup(read=async()=>source,timeoutMs=50){const states=[];const guard=createScenarioSourceGuard({read,validate:r=>scenarioSourceMatches(r,source),onState:s=>states.push(s),timeoutMs});return {guard,states};}
test('requires fresh matching measured record, not old initial status',async()=>{
 const t=setup();assert.equal(t.guard.current(),false);assert.equal(await t.guard.refresh(),source);assert.equal(t.guard.current(),true);t.guard.stop();assert.equal(t.guard.current(),false);
});
test('same source id cannot conceal changed hash, missing data or a wrong record',()=>{
 for(const r of [null,{...source,status:'stale'},{...source,hash:'different'},{...source,takeoff_id:'t2'}, {...source,result:null},{...source,result:{status:'measured',layers:[]}}, {...source,result:{status:'unavailable',layers:[{}]}}])assert.equal(scenarioSourceMatches(r,source),false);
 const c={materialset_id:'m1',hash:'collection',status:'measured',result:{status:'measured',materials:[{material_id:2}]}};
 assert.equal(scenarioSourceMatches(c,c),true);assert.equal(scenarioSourceMatches(source,c),false);
});
test('late success cannot override a newer stale observation',async()=>{
 const old=deferred();let calls=0;const t=setup(()=>++calls===1?old.promise:Promise.resolve({...source,status:'stale',result:null}));
 const first=t.guard.refresh();await t.guard.refresh();old.resolve(source);assert.equal(await first,null);assert.equal(t.guard.current(),false);assert.equal(t.states.at(-1),'stale');t.guard.stop();
});
test('network failure withdraws permission and requires a new successful GET',async()=>{
 let offline=false;const t=setup(async()=>{if(offline)throw Error('offline');return source;});
 await t.guard.refresh();offline=true;assert.equal(await t.guard.refresh(),null);assert.equal(t.guard.current(),false);assert.equal(t.states.at(-1),'unavailable');
 offline=false;await t.guard.refresh();assert.equal(t.guard.current(),true);t.guard.stop();
});
test('timeout remains bounded even if the reader ignores abort; late result does not reopen',async()=>{
 const old=deferred();const t=setup(()=>old.promise,15);assert.equal(await t.guard.refresh(),null);assert.equal(t.states.at(-1),'timeout');old.resolve(source);await Promise.resolve();assert.equal(t.guard.current(),false);t.guard.stop();
});
test('hidden page invalidates an in-flight success until a new check',async()=>{
 const old=deferred();let calls=0;const t=setup(()=>++calls===1?old.promise:Promise.resolve(source));
 const first=t.guard.refresh();t.guard.invalidate('hidden');old.resolve(source);assert.equal(await first,null);assert.equal(t.states.at(-1),'hidden');assert.equal(t.guard.current(),false);
 await t.guard.refresh();assert.equal(t.guard.current(),true);t.guard.stop();
});
test('closed form cannot receive a late state or perform future reads',async()=>{
 const old=deferred();let calls=0;const t=setup(()=>{calls++;return old.promise;});const first=t.guard.refresh();t.guard.stop();const count=t.states.length;old.resolve(source);await first;await t.guard.refresh();assert.equal(t.states.length,count);assert.equal(calls,1);
});
