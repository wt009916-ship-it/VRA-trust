import test from 'node:test';
import assert from 'node:assert/strict';
import { polygonArea, mergeRooms, roomArea, duplicateRoom } from '../src/model-ui.js';

test('floor area handles concave footprints and either winding', () => {
  const lShape = [[0,0],[6,0],[6,2],[2,2],[2,5],[0,5]];
  assert.equal(polygonArea(lShape), 18);
  assert.equal(polygonArea([...lShape].reverse()), 18);
});

test('stepped spaces count their base once and copy every elevation without changing the source', () => {
  const room={name:'Stair',source_locator:'IFC fixture',elevation_m:0,height_m:6,
    polygon:[[0,0],[4,0],[4,4],[0,4]],
    segments:[{polygon:[[0,0],[4,0],[4,4],[0,4]],elevation_m:0,height_m:3},
      {polygon:[[0,0],[3,0],[3,4],[0,4]],elevation_m:3,height_m:3}],
    boundary_hints:[{points:[[0,0,0],[4,0,0],[4,0,3]]}]};
  assert.equal(roomArea(room),16);
  const copied=duplicateRoom(room);
  assert.deepEqual(copied.segments.map(s=>s.elevation_m),[6,9]);
  assert.equal(copied.boundary_hints[0].points[2][2],9);
  assert.equal(room.boundary_hints[0].points[2][2],3);
  assert.match(copied.source_locator,/人工复制/);
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
