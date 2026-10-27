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


test('adding imports preserves existing equipment zone IDs', () => {
  const merged=mergeRooms([{id:'Plant_A',name:'Existing'}],[{id:'Plant_A',name:'Added'},{id:'Unique_B',name:'Unique'}]);
  assert.deepEqual(merged.map(r=>r.id),['Plant_A','R1','Unique_B']);
});

test('source shell and windows move together and the copied floor has its own display key', () => {
  const source={id:'R1',name:'Slope',source_locator:'Controlled source',storey_id:'source_floor',storey_name:'Level 1',
    polygon:[[0,0],[4,0],[4,4],[0,4]],holes:[[[1,1],[2,1],[2,2],[1,2]]],elevation_m:0,height_m:5,
    shell:[{points:[[0,0,3],[4,0,5],[4,4,5]]}],source_openings:[{points:[[0,1,1],[0,2,1],[0,2,2]]}]};
  const copied=duplicateRoom(source);
  assert.equal(roomArea({...source,shell:[]}),15);
  assert.equal(copied.shell[0].points[1][2],10);
  assert.equal(copied.source_openings[0].points[0][2],6);
  assert.equal(copied.storey_id,null);
  assert.equal(source.shell[0].points[1][2],5);
});


test('cantilever counts raised exposed floors while contained setbacks do not double count',()=>{
 const lower={polygon:[[0,0],[4,0],[4,4],[0,4]],elevation_m:0,height_m:3};
 const upper={polygon:[[2,0],[6,0],[6,4],[2,4]],elevation_m:3,height_m:3};
 assert.equal(roomArea({...lower,segments:[lower,upper]}),24);
 const contained={polygon:[[1,1],[3,1],[3,3],[1,3]],elevation_m:3,height_m:3};
 assert.equal(roomArea({...lower,segments:[lower,contained]}),16);
});
