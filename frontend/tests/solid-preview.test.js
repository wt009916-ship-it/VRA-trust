import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {shellGeometry,storeyKey} from '../src/solid-preview.js';

test('sloped preview tessellation retains actual plane and area',()=>{
  const faces=[{points:[[0,0,3],[4,0,5],[4,4,5],[0,4,3]]}];
  const geometry=shellGeometry(faces,THREE),p=geometry.getAttribute('position');
  let area=0;
  for(let i=0;i<p.count;i+=3){
    const a=new THREE.Vector3().fromBufferAttribute(p,i),b=new THREE.Vector3().fromBufferAttribute(p,i+1),c=new THREE.Vector3().fromBufferAttribute(p,i+2);
    for(const v of [a,b,c])assert.ok(Math.abs(v.y-(3+v.x/2))<1e-6);
    area+=b.sub(a).cross(c.sub(a)).length()/2;
  }
  assert.ok(Math.abs(area-Math.sqrt(20)*4)<1e-6);
  assert.equal(storeyKey({storey_id:'actual_floor',elevation_m:99}),'actual_floor');
  assert.equal(storeyKey({elevation_m:3}),'z:3');
  geometry.dispose();
});
