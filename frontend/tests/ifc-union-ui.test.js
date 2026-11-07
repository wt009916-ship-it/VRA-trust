import test from 'node:test';
import assert from 'node:assert/strict';
import {unionRecordMarkup,unionWorkspaceMarkup,unionQuantity} from '../src/ifc-union-ui.js';

const record={union_id:'union_ab',cad_id:'cad_ab',product_ids:[34,45],source:{name:'<img src=x onerror=x>',hash:'abc'},parser_hash:'v1',
 status:'measured',result:{status:'measured',sum_operand_volume_m3:48,union_volume_m3:36,overlap_deduction_m3:12,library_version:'3.5.4'}};
test('union displays three distinct quantities with scope and escaped source',()=>{
 const text=unionRecordMarkup(record,'/projects/project_ab');
 assert.ok(text.includes('48 m³')&&text.includes('36 m³')&&text.includes('12 m³'));
 assert.ok(text.includes('#34、#45')&&text.includes('不是材料净用量')&&text.includes('重叠重复扣除量'));
 assert.ok(!text.includes('<img ')&&text.includes('&lt;img'));
 assert.ok(text.includes('/ifc-unions/union_ab/report.html'));
});
test('stale and refused records never render stored numeric claims',()=>{
 for(const r of [{...record,status:'stale'},{...record,status:'unavailable',result:{...record.result,status:'unavailable',reason:'union_topology_unverified'}}]){
  const text=unionRecordMarkup(r,'/projects/project_ab');
  assert.ok(!text.includes('36 m³')&&!text.includes('48 m³'));
  assert.ok(text.includes('数量 —'));
 }
});
test('source selector offers only current IFC inspections',()=>{
 const sources=[{cad_id:'cad_a',status:'parsed',source:{name:'IFC'},result:{format:'IFC'}},
 {cad_id:'cad_b',status:'stale',source:{name:'old'},result:null},
 {cad_id:'cad_c',status:'parsed',source:{name:'DXF'},result:{format:'DXF'}}];
 const text=unionWorkspaceMarkup(sources);
 assert.ok(text.includes('value="cad_a"')&&!text.includes('value="cad_b"')&&!text.includes('value="cad_c"'));
 assert.ok(text.includes('multiple')&&text.includes('disabled'));
});
test('small nonzero geometry quantities never round to zero',()=>{
 assert.equal(unionQuantity(1e-10),'1.000000e-10');
 assert.equal(unionQuantity(0),'0');
 assert.equal(unionQuantity(null),'—');
});
