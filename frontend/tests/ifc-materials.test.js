import test from 'node:test';
import assert from 'node:assert/strict';
import {ifcMaterialMarkup} from '../src/ifc-ui.js';

test('material sources remain escaped and do not invent quantity',()=>{
 const html=ifcMaterialMarkup({status:'declared',associations:[{relation_id:12,owner_id:4,scope:'instance',selection:'effective_declaration',material:{type:'IfcMaterial',id:7,name:'<img src=x onerror=alert(1)>'}}]});
 assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img'));
 assert.ok(html.includes('材料工程量尚未测定'));assert.ok(html.includes('#12'));
});
test('unknown layer thickness is not formatted as zero',()=>{
 const html=ifcMaterialMarkup({status:'ambiguous',associations:[{scope:'type',relation_id:8,owner_id:3,selection:'ambiguous',material:{type:'IfcMaterialLayer',id:5,thickness:{raw:50,value_m:null,status:'missing_unit'},material:{type:'IfcMaterial',id:2,name:'Board'}}}]});
 assert.ok(html.includes('材料关联存在冲突'));assert.ok(html.includes('缺少对应单位'));
 assert.ok(html.includes('— m'));assert.ok(!html.includes('0.000000 m'));
});
