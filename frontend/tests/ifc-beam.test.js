import test from 'node:test';
import assert from 'node:assert/strict';
import {profileMarkup,reviewedProfile,bindIfcBeamProfile} from '../src/ifc-beam-ui.js';
const record={status:'extracted',beamprofile_id:'beamprofile_fixture',hash:'a'.repeat(64),file_snapshot:{hash:'source'},result:{product_id:70,name:'<script>malicious()</script>',section_profile:{kind:'i_section'},section_properties:{area_m2:.0156,ix_m4:.0009208,iy_m4:.00003387,dimensions_m:{h:.6}},source:{profile_type:'IfcIShapeProfileDef'},extrusion_length_m:10,axes_world:{x:[1,0,0]}}};
test('current profile renders source, units and declared geometry, escaping input',()=>{const html=profileMarkup(record);assert(html.includes('m⁴'));assert(html.includes('不是跨度'));assert(html.includes('&lt;script&gt;'));assert(!html.includes('<script>'));assert(html.includes('非实测'));});
test('stale and unsupported records cannot leak a cached section value',()=>{for(const status of ['stale','unsupported']){const html=profileMarkup({...record,status});assert(!html.includes('m⁴'));assert(html.includes('截面值不展示'));assert.throws(()=>reviewedProfile({...record,status},'x',true,'Explicit source and axis review basis for test'));}});
test('review requires explicit principal axis and real boolean consent',()=>{for(const [axis,consent,basis] of [['z',true,'long review basis '.repeat(3)],['x','true','long review basis '.repeat(3)],['y',false,'long review basis '.repeat(3)],['x',true,'short']])assert.throws(()=>reviewedProfile(record,axis,consent,basis));const p=reviewedProfile(record,'y',true,'Independent geometry review with explicit axis');assert.equal(p.bending_axis,'y');assert.equal(p.expected_profile_hash,record.hash);assert(!('span' in p));assert(!('elastic_modulus' in p));assert(!('actor_user_id' in p));});

function harness(t,fetcher){
 const elements=new Map();const host={isConnected:true,innerHTML:'',querySelector(key){if(!elements.has(key))elements.set(key,{value:'',checked:false,disabled:false,innerHTML:'',textContent:''});return elements.get(key);}};
 const changes=[];t.mock.method(globalThis,'fetch',fetcher);
 const old=globalThis.document;globalThis.document={hidden:false};t.after(()=>{globalThis.document=old;});
 const control=bindIfcBeamProfile(host,'/projects/p',fn=>fn(),(r,locked)=>changes.push({r,locked}));t.after(()=>control.clear());
 return {host,control,changes,element:k=>host.querySelector(k)};
}
const json=value=>Promise.resolve(new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}}));
function consent(h){h.element('[data-ifc-confirm]').checked=true;h.element('[data-ifc-axis]').value='x';h.element('[data-ifc-basis]').value='Explicit independent geometry and bending axis review';}
test('restoring a source rechecks server and requires fresh consent',async t=>{
 let calls=0;const h=harness(t,()=>{calls++;return json(record);});
 await h.control.restore({beamprofile_id:record.beamprofile_id,hash:record.hash});
 assert.equal(h.element('[data-ifc-confirm]').checked,false);await assert.rejects(h.control.review());
 consent(h);const result=await h.control.review();assert.equal(result.expected_profile_hash,record.hash);assert(calls>=3);
});
test('source becomes stale between selection and submit: old metrics disappear and submission refused',async t=>{
 let value=record;const h=harness(t,()=>json(value));await h.control.restore({beamprofile_id:record.beamprofile_id,hash:record.hash});consent(h);
 value={...record,status:'stale'};await assert.rejects(h.control.review());
 assert(!h.element('[data-ifc-values]').innerHTML.includes('m⁴'));assert.equal(h.changes.at(-1).r.status,'stale');
});
test('failed current-state request clears values and confirmation',async t=>{
 let fail=false;const h=harness(t,()=>fail?Promise.reject(new Error('connection lost')):json(record));
 await h.control.restore({beamprofile_id:record.beamprofile_id,hash:record.hash});consent(h);fail=true;
 await assert.rejects(h.control.review());assert.equal(h.element('[data-ifc-confirm]').checked,false);assert(!h.element('[data-ifc-values]').innerHTML.includes('m⁴'));
});
test('late source response cannot restore a cleared selection',async t=>{
 let resolve;const h=harness(t,()=>new Promise(r=>{resolve=r;}));const waiting=h.control.restore({beamprofile_id:record.beamprofile_id,hash:record.hash});h.control.clear();resolve(new Response(JSON.stringify(record),{status:200}));await waiting;
 assert.equal(h.control.capture(),null);assert.equal(h.element('[data-ifc-values]').innerHTML,'');assert.equal(h.changes.at(-1).locked,false);
});
test('detached workspace ignores a pending response',async t=>{
 let resolve;const h=harness(t,()=>new Promise(r=>{resolve=r;}));const waiting=h.control.restore({beamprofile_id:record.beamprofile_id,hash:record.hash});const before=h.changes.length;h.host.isConnected=false;resolve(new Response(JSON.stringify(record),{status:200}));await waiting;assert.equal(h.changes.length,before);
});
