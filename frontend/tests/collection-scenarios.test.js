import test from 'node:test';
import assert from 'node:assert/strict';
import {scenarioFormMarkup,scenarioPayload,scenarioSourceShape} from '../src/material-scenarios-ui.js';
const source={materialset_id:'materialset_'+'a'.repeat(32),result:{materials:[{material_id:3932,material_name:'Stud <unsafe>',union_envelope_m3:1.84266524},{material_id:3941,material_name:'Board',union_envelope_m3:.64092704}]}};
test('collection form uses material entity identity and server-only volume',()=>{
 const html=scenarioFormMarkup(source,{building:{region:'US-CO'}});
 assert.ok(html.includes('从多构件去重材料建立两套方案')&&html.includes('来源材料实体 #3932'));
 assert.ok(!html.includes('来源层 #')&&!html.includes('<unsafe>'));
 assert.ok(!html.includes('name="union_envelope_m3"'));
 assert.equal(scenarioSourceShape(source).endpoint,'/collection-scenarios');
});
test('collection payload excludes duplicated layer aliases and preserves missing values',()=>{
 const data=new FormData();data.set('include_3932','on');data.set('a0_3932_solid_fraction','.05');
 data.set('exclude_3941','Explicit shared omitted material');
 data.set('carbon_transport_0_1_id','haul');data.append('carbon_transport_0_1_layers','3932');
 const body=scenarioPayload(data,source);
 assert.equal(body.materialset_id,source.materialset_id);
 assert.ok(!('takeoff_id' in body)&&!('excluded_layers' in body));
 assert.deepEqual(body.excluded_materials,[{source_material_id:3941,reason:'Explicit shared omitted material'}]);
 assert.equal(body.alternatives[0].materials[0].source_material_id,3932);
 assert.equal(body.alternatives[0].materials[0].solid_fraction,.05);
 assert.equal(body.alternatives[1].materials[0].solid_fraction,null);
 assert.deepEqual(body.alternatives[0].transport_legs[0].material_ids,[3932]);
 assert.ok(!JSON.stringify(body).includes('layer_id')&&!JSON.stringify(body).includes('1.84266524'));
});
