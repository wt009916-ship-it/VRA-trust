import test from 'node:test';
import assert from 'node:assert/strict';
import {propertyEditors,previewMarkup,retrofitResultMarkup,matchingRuns,annualComparisonMarkup} from '../src/retrofit-ui.js';

test('missing dynamic material properties are required and never guessed',()=>{
 const html=propertyEditors({status:'calculated',result:{layers:[{name:'<img src=x>',thickness_m:.2,effective_conductivity_w_mk:.5}]}});
 assert.ok(html.includes('&lt;img'));
 for(const field of ['density_kg_m3','specific_heat_j_kg_k','thermal_absorptance','solar_absorptance','visible_absorptance','property_source'])assert.ok(html.includes(`name="${field}"`));
 assert.ok(!html.includes('value="1200"'));assert.ok(!html.includes('<img'));
 assert.ok(!propertyEditors({status:'stale',result:{layers:[{}]}}).includes('<input'));
 assert.ok(!propertyEditors({status:'calculated',result:{layers:Array(11).fill({})}}).includes('<input'));
});

test('preview shows exact surface mapping, outside-inside order and explicit unselected consent',()=>{
 const html=previewMarkup({changes:{changed_reference_count:1,added_object_count:3,changes:[{surface_name:'<wall>',old_construction:'Old',new_construction:'New'}],assignments:[{layers_outside_to_inside:[{thermal_layer_name:'Outer'},{thermal_layer_name:'Inner'}]}]},limitations:['<unsafe>']});
 assert.ok(html.includes('&lt;wall&gt;')&&!html.includes('<unsafe>'));
 assert.ok(html.includes('Outer → Inner')&&html.includes('不写入 Rsi/Rse'));
 assert.ok(html.includes('data-generate disabled'));assert.ok(!html.includes('checked'));
});

const record={project_id:'p',retrofit_id:'retrofit_a',status:'generated',input:{name:'<name>'},changes:{changed_reference_count:4},evidence_review:{review_state:'pending'},dependencies:{source_file:{hash:'a'}},derived_file:{hash:'b'}};
test('current pending derivative is labelled scenario; stale record cannot offer model download',()=>{
 assert.ok(retrofitResultMarkup(record,'/projects/p').includes('pending'));
 assert.ok(retrofitResultMarkup(record,'/projects/p').includes('&lt;name&gt;'));
 for(const status of ['stale','rejected','unverified'])assert.ok(!retrofitResultMarkup({...record,status},'/projects/p').includes('model.idf'));
});

test('only successful exact-file same-project runs can be selected',()=>{
 const good={project_id:'p',scheme_id:'R1',status:'succeeded',provenance:{model_hash:'b'},run_id:'r1'};
 const rows=[good,{...good,status:'stale'},{...good,project_id:'q'},{...good,provenance:{model_hash:'old'}},{...good,scheme_id:'R2'}];
 assert.deepEqual(matchingRuns(rows,record,'R1'),[good]);
 assert.deepEqual(matchingRuns(rows,record,'baseline'),[]);
});

test('annual comparison displays native energy and distinct saving, never from thermal U',()=>{
 const payload={comparison:{results:[{scheme_id:'R1',status:'succeeded',metrics:{annual_energy_kwh:56272.58},saving_rate_pct:1.609718}],note:'<scenario only>'}};
 const html=annualComparisonMarkup(payload);
 assert.ok(html.includes('1.61%')||html.includes('1.61')||html.includes('1.610'));
 assert.ok(html.includes('全年节能率')&&html.includes('&lt;scenario only&gt;'));
 assert.ok(!annualComparisonMarkup({comparison:{results:[{...payload.comparison.results[0],status:'stale'}]}}).includes('<table>'));
});
