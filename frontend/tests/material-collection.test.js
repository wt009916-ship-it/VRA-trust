import test from 'node:test';
import assert from 'node:assert/strict';
import {materialCollectionMarkup} from '../src/material-collection-ui.js';
import {unionWorkspaceMarkup} from '../src/ifc-union-ui.js';

const record={materialset_id:'materialset_a',product_ids:[12,34],source:{name:'<unsafe>'},status:'measured',result:{status:'measured',materials:[{material_id:7,material_name:'A<script>',source_sum_m3:48,overlap_deduction_m3:12,union_envelope_m3:36}]}};
test('material result preserves entity identity and exposes counted-once quantities',()=>{
 const html=materialCollectionMarkup(record,'/projects/p');
 assert.ok(html.includes('去重包络 m³')&&html.includes('36')&&html.includes('#7'));
 assert.ok(html.includes('&lt;script&gt;')&&!html.includes('<unsafe>'));
 assert.ok(html.includes('/ifc-material-collections/materialset_a/report.html'));
 assert.ok(html.includes('不能直接当作采购净量'));
});
test('stale and unavailable states cannot expose old material amounts',()=>{
 for(const status of ['stale','unavailable']){
  const html=materialCollectionMarkup({...record,status},'/projects/p');
  assert.ok(!html.includes('<table>')&&!html.includes('>36<'));
  assert.ok(html.includes('数量 —'));
 }
});
test('shared selection markup retains union defaults and permits distinct help labels',()=>{
 assert.ok(unionWorkspaceMarkup([]).includes('2–64'));
 const html=unionWorkspaceMarkup([],{heading:'材料核验',description:'2–16面墙',helpId:'material-help',buttonLabel:'核算材料包络'});
 assert.ok(html.includes('材料核验')&&html.includes('2–16面墙')&&html.includes('id="material-help"'));
 assert.ok(!html.includes('2–64'));
});
