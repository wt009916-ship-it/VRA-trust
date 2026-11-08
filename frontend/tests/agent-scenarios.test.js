import test from 'node:test';
import assert from 'node:assert/strict';
import {scenarioArtifactMarkup} from '../src/agent-artifacts.js';
import {validateReadRequests,readRecordLabel,readKinds} from '../src/agent-requests.js';
const base={kind:'scenario_review',record_id:'scenario_'+'a'.repeat(32),project_id:'project_'+'b'.repeat(32),name:'A <img> / B',scope:'Declared comparison',input:{functional_scope:'Same wall',study_years:30,currency:'USD'}};
test('scenario selector handles actual list response and keeps explicit read scope',()=>{
 assert.ok(readKinds.scenario);assert.match(readRecordLabel({names:['A','B']},'scenario'),/A \/ B.*执行时核验/);
 assert.equal(validateReadRequests([{request_key:'x',kind:'scenario',purpose:'results',record_id:base.record_id}],{mode:'local_model',allowCompute:false,objective:'open_ended'})[0].record_id,base.record_id);
 assert.throws(()=>validateReadRequests([{request_key:'x',kind:'cost',purpose:'results',record_id:base.record_id}],{mode:'local_model',allowCompute:false,objective:'open_ended'}));
});
test('stale or incomplete comparison withdraws all cached numeric output',()=>{
 for(const status of ['stale','incomplete']){const html=scenarioArtifactMarkup({...base,status,verified:false,result:{comparison:{cost_difference:'UNSAFE_9988'}}});assert.ok(!html.includes('UNSAFE_9988'));assert.ok(!html.includes('<img>'));assert.ok(html.includes('&lt;img&gt;'));assert.match(html,/material-scenarios\/scenario_/);}
});
test('comparison displays sign direction, excluded stage and whole-period scope',()=>{
 const alt=name=>({name,cost:{material_total:'120.50'},carbon:{boundary_total_kgco2e:123,stages:{production:{included:true,kgco2e:123},transport:{included:false,kgco2e:null}}}});
 const html=scenarioArtifactMarkup({...base,status:'calculated',verified:true,result:{alternatives:[alt('A'),alt('B')],comparison:{cost_difference:'-5.25',carbon_reduction_kgco2e:'-10'}}});
 for(const word of ['替换－基准','基准－替换','未纳入，不等于零','整个评估期','-5.25','-10'])assert.ok(html.includes(word),word);
});


test('undefined source percentage shows reason without inventing zero or executable markup',async()=>{
 const {checkedDeliveryMarkup}=await import('../src/agent-artifacts.js');
 const html=checkedDeliveryMarkup({checked_statements:[{name:'A',record_id:base.record_id,facts:[{
   fact:'cost_reduction_pct',label:'减少比例',value:null,unit:'%',period:'quote_date',study_years:null,area_m2:null,
   source_path:'/result/comparison/cost_reduction_pct',unavailable_reason:'分母为零 <img onerror="bad()">'}]}]});
 assert.match(html,/— %/);assert.match(html,/不可计算：分母为零/);assert.ok(!html.includes('<img'));
 assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('>0 %'));assert.ok(!html.includes('None'));
});
