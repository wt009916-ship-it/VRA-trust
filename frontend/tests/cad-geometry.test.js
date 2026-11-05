import test from 'node:test';
import assert from 'node:assert/strict';
import {dxfProjection,geometryMarkup} from '../src/cad-ui.js';

test('CAD projection preserves XY proportions and labels incomplete rendering',()=>{
  const html=dxfProjection({objects:[{type:'LINE',path:['<img>'],preview_points:[[0,0,0],[3,4,0]]}]});
  assert.ok(html.includes('30,470 345,50'));
  assert.ok(html.includes('&lt;img&gt;'));
  assert.ok(html.includes('非完整图纸渲染'));
  assert.ok(!html.includes('<img>'));
});

test('CAD missing quantities remain unavailable and unsupported entities stay visible',()=>{
  const html=geometryMarkup({objects:[{type:'POINT',path:['AA'],layer:'unknown',length_m:null,area_m2:null,geometry_status:'unsupported'}],visited_entities:1,issue_count:1,coverage:'partial',expanded_counts:{POINT:1},limitations:[],issues:[{reason:'unsupported_entity:POINT'}]});
  assert.ok(html.includes('<td>—</td><td>—</td>'));assert.ok(html.includes('unsupported'));assert.ok(html.includes('部分信息未取得'));
});
