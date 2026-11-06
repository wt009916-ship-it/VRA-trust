import test from 'node:test';
import assert from 'node:assert/strict';
import {ifcObjectMarkup,ifcMarkup,topologyMarkup} from '../src/ifc-ui.js';

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

test('Rejected shell orientation leaves volume unknown and separates diagnostic integrals',()=>{
  const html=ifcObjectMarkup({id:1,type:'IfcWall'},{status:'partial_mesh',volume_m3:null,surface_area_m2:60,
    topology:{status:'rejected',reason:'incompatible_shell_orientation',shells:[{shell:0,depth:0,signed_volume_m3:27,orientation_consistent:true},{shell:1,depth:1,signed_volume_m3:1,orientation_consistent:false}]}});
  assert.ok(html.includes('体积 — m³'));
  assert.ok(html.includes('内外壳方向与嵌套关系不一致'));
  assert.ok(html.includes('不是可直接计价的工程量'));
  assert.ok(html.includes('非并集面积'));
  assert.ok(!html.includes('通过当前网格检查'));
});

test('Topology failure, work exhaustion and absent receipt never render success',()=>{
  for(const reason of ['topology_pairs_budget','topology_nodes_budget','topology_ray_tests_budget','ambiguous_shell_containment_rays']){
    const html=topologyMarkup({status:'not_verified',reason});
    assert.ok(html.includes('体积不交付'));assert.ok(!html.includes('通过当前网格检查'));
  }
  assert.ok(topologyMarkup(null).includes('未提供网格拓扑核验回执'));
  const html=topologyMarkup({status:'rejected',reason:'<img src=x onerror=alert(1)>',triangle_indices:[4,8]});
  assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));
  assert.ok(html.includes('从0开始'));assert.ok(html.includes('4、8'));
});

test('Successful topology remains approximate and bounded to one product',()=>{
  const html=topologyMarkup({status:'checked',shells:[]});
  assert.ok(html.includes('仍为近似几何量'));assert.ok(html.includes('需工程复核'));
  assert.ok(html.includes('不自动修补'));assert.ok(html.includes('不合并其他构件'));
});

test('IFC coverage reports unknown shapes and does not sum host and openings',()=>{
  const rows=[{id:1,type:'IfcWall',status:'measured_mesh',volume_m3:22}, {id:2,type:'IfcOpeningElement',status:'partial_mesh',volume_m3:null}];
  const html=ifcMarkup({objects:rows,ifc_geometry:{objects:rows,limitations:[]}},'cad_test');
  assert.ok(html.includes('1个存在几何缺口'));assert.ok(html.includes('不相加为建筑总量'));
  assert.ok(html.includes('体积未知'));assert.ok(html.includes('<td>—</td>'));
});
