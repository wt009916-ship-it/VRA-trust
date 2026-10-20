import test from 'node:test';
import assert from 'node:assert/strict';
import { polygonArea, mergeRooms } from '../src/model-ui.js';

test('floor area handles concave footprints and either winding', () => {
  const lShape = [[0,0],[6,0],[6,2],[2,2],[2,5],[0,5]];
  assert.equal(polygonArea(lShape), 18);
  assert.equal(polygonArea([...lShape].reverse()), 18);
});

test('merging independent imports creates unique room IDs and isolates candidate history', () => {
  const existing = [{id:'R1',name:'Ground',polygon:[[0,0],[5,0],[0,5]],elevation_m:0}];
  const candidate = [{id:'R1',name:'Upper',polygon:[[0,0],[5,0],[0,5]],elevation_m:3,source_locator:'IFC GlobalId=fixture'}];
  const merged = mergeRooms(existing,candidate);
  assert.deepEqual(merged.map(r=>r.id), ['R1','R2']);
  assert.equal(merged[1].elevation_m, 3);
  assert.equal(merged[1].source_locator, 'IFC GlobalId=fixture');
  merged[1].polygon[0][0] = 10;
  assert.equal(candidate[0].polygon[0][0], 0);
  assert.equal(candidate[0].id, 'R1');
  assert.deepEqual(existing[0].polygon[0], [0,0]);
});
