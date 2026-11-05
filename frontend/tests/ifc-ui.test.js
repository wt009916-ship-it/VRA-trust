import test from 'node:test';
import assert from 'node:assert/strict';
import {ifcObjectMarkup,ifcMarkup} from '../src/ifc-ui.js';

test('IFC declarations keep conflicts and missing units distinct from measured volume',()=>{
  const product={id:1,name:'<script>unsafe</script>',type:'IfcWall',global_id:'ref',types:[],properties:[],
    spatial_relations:[{parent_name:'Level 1',parent_id:39,relation_type:'IfcRelAggregates',relation_id:38297}],
    quantities:[{set:'Qto',path:['Volume'],source_id:42,scope:'instance',value:99,value_si:null,si_unit:'m3',status:'missing_unit',selection:'ambiguous'}]};
  const html=ifcObjectMarkup(product,{status:'measured_mesh',surface_area_m2:52,volume_m3:24});
  assert.ok(html.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('缺少对应单位'));assert.ok(html.includes('来源冲突'));
  assert.ok(html.includes('体积 24 m³'));assert.ok(html.includes('网格表面积'));
  assert.ok(html.includes('Level 1 #39 · IfcRelAggregates #38297'));
});

test('IFC coverage reports unknown shapes and does not sum host and openings',()=>{
  const rows=[{id:1,type:'IfcWall',status:'measured_mesh',volume_m3:22}, {id:2,type:'IfcOpeningElement',status:'partial_mesh',volume_m3:null}];
  const html=ifcMarkup({objects:rows,ifc_geometry:{objects:rows,limitations:[]}},'cad_test');
  assert.ok(html.includes('1个存在几何缺口'));assert.ok(html.includes('不相加为建筑总量'));
  assert.ok(html.includes('体积未知'));assert.ok(html.includes('<td>—</td>'));
});
