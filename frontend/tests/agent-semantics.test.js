import test from 'node:test';
import assert from 'node:assert/strict';
import {checkedDeliveryMarkup} from '../src/agent-artifacts.js';

test('checked explanation retains whole period and area denominator, rounds display only',()=>{
  const answer={checked_statements:[{name:'Inventory',record_id:'lifecycle_test',facts:[{
    fact:'per_area',label:'评估期单位面积碳排',value:'17.661749999999998',unit:'kgCO2e/m2',
    period:'study_period',study_years:15,area_m2:100,source_path:'/result/kgco2e_m2_over_study_period'}]}]};
  const before=JSON.stringify(answer),html=checkedDeliveryMarkup(answer);
  for(const text of ['17.66175 kgCO2e/m2','整个评估期 15 年','面积分母 100 m²','/result/kgco2e_m2_over_study_period','完整覆盖度'])assert.ok(html.includes(text),text);
  assert.equal(JSON.stringify(answer),before);
});

test('empty stale explanations render no old facts and untrusted strings escape',()=>{
  assert.equal(checkedDeliveryMarkup(null),'');
  const html=checkedDeliveryMarkup({checked_statements:[{name:'<svg onload=alert(1)>',record_id:'<script>',facts:[{
    value:null,label:'<img>',unit:'<iframe>',period:'steady_state',study_years:null,area_m2:null,source_path:'<svg>'}]}]});
  assert.ok(!html.includes('<svg')&&!html.includes('<img')&&!html.includes('<script')&&!html.includes('<iframe'));
  assert.ok(html.includes('—'));
  assert.equal(checkedDeliveryMarkup({checked_statements:[],artifacts:[]}), '');
});
