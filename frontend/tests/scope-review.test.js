import test from 'node:test';
import assert from 'node:assert/strict';
import {reviewUseScope} from '../src/scope-review.js';

test('batch review explicitly changes only a selected source storey and preserves IDs',()=>{
  const rooms=[{id:'Equipment_A',storey_id:'ground',conditioned:null,include_floor_area:null},{id:'Roof_B',storey_id:'roof',conditioned:null,include_floor_area:null}];
  const r=reviewUseScope(rooms,{storey:'roof',conditioned:false,include_floor_area:false,note:'Controlled roof scope review'});
  assert.deepEqual(r.affected,['Roof_B']);assert.equal(r.rooms[1].conditioned,false);assert.equal(r.rooms[0].conditioned,null);assert.equal(rooms[1].conditioned,null);assert.match(r.note,/roof/);
});
test('whole building use is an explicit review and missing basis or no choice is refused',()=>{
  const rooms=[{id:'A',conditioned:true,include_floor_area:true},{id:'B',conditioned:true,include_floor_area:true}];
  assert.throws(()=>reviewUseScope(rooms,{conditioned:false,note:''}),/依据/);
  assert.throws(()=>reviewUseScope(rooms,{note:'Controlled scope evidence'}),/至少/);
  const r=reviewUseScope(rooms,{conditioned:null,note:'Controlled explicit reset of use'});
  assert.equal(r.affected.length,2);assert.ok(r.rooms.every(x=>x.conditioned===null&&x.include_floor_area===true));
});
