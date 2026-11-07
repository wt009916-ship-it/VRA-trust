import test from 'node:test';
import assert from 'node:assert/strict';
import {openingMarkup} from '../src/ifc-ui.js';
test('empty native mesh is unknown rather than certified zero',()=>{
  const html=openingMarkup({mesh_status:'empty_mesh'});
  assert.ok(html.includes('体积保持未知')&&html.includes('不能将空网格'));
});
test('opening ambiguity retains escaped relation locators and refusal',()=>{
  const html=openingMarkup({opening_relationships:{issues:['duplicate_void_relationship','<img>'],relations:[{relation_id:9,host_id:3,opening_id:'<x>'}]}});
  assert.ok(html.includes('暂不交付')&&html.includes('重复开洞关系')&&html.includes('关系 #9')&&html.includes('宿主 #3'));
  assert.ok(!html.includes('<img>')&&!html.includes('<x>'));
  assert.ok(openingMarkup({opening_relationships:{issues:[],relations:[]}}).includes('不代表几何相交'));
});
