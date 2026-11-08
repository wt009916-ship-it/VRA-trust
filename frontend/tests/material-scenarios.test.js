import test from 'node:test';
import assert from 'node:assert/strict';
import {scenarioFormMarkup,scenarioPayload} from '../src/material-scenarios-ui.js';
const takeoff={takeoff_id:'takeoff_'+ 'a'.repeat(32),result:{layers:[{layer_id:10,material_name:'<img src=x onerror=alert(1)>',envelope_volume_m3:5.6}]}};
test('source form escapes IFC names and does not offer editable source quantity',()=>{
 const html=scenarioFormMarkup(takeoff,{building:{region:'US-CO'}});
 assert(!html.includes('<img'));
 assert(html.includes('&lt;img'));
 assert(!html.includes('name="quantity"'));
 assert(html.includes('实体比例'));
 assert(html.includes('共同碳核算边界'));
 assert(html.includes('排除不等于零排放'));
 assert(html.includes('data-add-transport'));
});
test('blank conversions stay unknown and source volume is never sent by client',()=>{
 const data=new FormData();data.set('include_10','on');data.set('a0_10_solid_fraction','0.5');
 const body=scenarioPayload(data,takeoff);
 assert.equal(body.alternatives[0].layers[0].solid_fraction,0.5);
 assert.equal(body.alternatives[1].layers[0].solid_fraction,null);
 assert.equal(body.alternatives[0].layers[0].density_kg_m3,null);
 assert(!JSON.stringify(body).includes('5.6'));
 assert.equal(body.boundaries.filter(b=>b.included).length,1);
});
test('excluded layers retain a shared explicit reason in both alternatives',()=>{
 const data=new FormData();data.set('exclude_10','Outside this material scope');
 const body=scenarioPayload(data,takeoff);
 assert.deepEqual(body.excluded_layers,[{layer_id:10,reason:'Outside this material scope'}]);
 assert(body.alternatives.every(a=>a.layers.length===0));
});
