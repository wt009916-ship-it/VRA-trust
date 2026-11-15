import test from 'node:test';
import assert from 'node:assert/strict';
import {ifcObjectMarkup} from '../src/ifc-ui.js';
import {materialCollectionMarkup} from '../src/material-collection-ui.js';

test('beam and column expose actual material calculation while unsupported equipment does not',()=>{
 for(const type of ['IfcBeam','IfcBeamStandardCase','IfcColumn','IfcColumnStandardCase']){
  const html=ifcObjectMarkup({id:17,type,name:'<bad>',quantities:[],properties:[]},null);
  assert.match(html,/data-layer-product="17"/);assert.match(html,/计算构件材料包络/);assert.ok(!html.includes('<bad>'));
 }
 assert.ok(!ifcObjectMarkup({id:2,type:'IfcPump',quantities:[],properties:[]},null).includes('data-layer-product'));
});
test('mixed material result names the actual supported member scope without procurement claim',()=>{
 const html=materialCollectionMarkup({status:'measured',product_ids:[1,2],materialset_id:'materialset_a',source:{name:'mixed'},result:{status:'measured',materials:[]}},'/projects/p');
 assert.match(html,/明确单材或可核验复合分区的梁柱/);assert.match(html,/不能直接当作采购净量/);
});
