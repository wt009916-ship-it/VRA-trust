import test from 'node:test';
import assert from 'node:assert/strict';
import {checkedDeliveryMarkup, staleReasonMarkup, selectedReadProgressMarkup} from '../src/agent-artifacts.js';

test('failed and partial tasks retain selected unread targets without claiming complete intent coverage',()=>{
 for(const task of [{status:'failed',unresolved_selected_reads:['thermal_<script>']},
  {status:'succeeded',answer:{unresolved_selected_reads:['operation_<script>']}}]) {
  const html=selectedReadProgressMarkup(task);
  assert.ok(html.includes('仍有 1 个') && html.includes('不代表原问题已经完整拆解'));
  assert.ok(!html.includes('<script>') && html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('W/(m²') && !html.includes('计算已完成'));
 }
 assert.equal(selectedReadProgressMarkup({unresolved_selected_reads:[]}), '');
});

test('missing catalog evidence is separate from zero numerical results and capability rejection',()=>{
 const html=checkedDeliveryMarkup({checked_missing:[{kind:'thermal',scope:'entire_project_kind',record_id:null,checked_at:'2026-11-07'},
  {kind:'cost',scope:'requested_record_in_project',record_id:'cost_<script>',checked_at:'2026-11-07'}]});
 assert.ok(html.includes('当前记录缺失说明') && html.includes('完整项目目录中没有该类记录'));
 assert.ok(html.includes('不能据此判断其他项目') && html.includes('不代表工程计算完成'));
 assert.ok(html.includes('不自动重试写操作') && html.includes('缺失结果不记为零'));
 assert.ok(!html.includes('<script>') && !html.includes('m²·K/W') && !html.includes('已核验的材料清单结果'));
});

test('stale provenance explains observed revision without turning method scope into cause',()=>{
 const html=staleReasonMarkup({stale_details:[{code:'project_revision',subject_id:'project_<script>',expected:1,current:2},
   {code:'evidence_rejected',subject_id:'evidence_a',expected:'confirmed',current:'rejected'}]});
 assert.ok(html.includes('项目声明版本已变化：v1 → v2'));
 assert.ok(html.includes('依据已撤回') && !html.includes('<script>'));
 assert.ok(!html.includes('资源约束') && !html.includes('安全'));
});

test('checked stale limitation remains distinct from an effective numerical result',()=>{
  const html=checkedDeliveryMarkup({checked_limitations:[{record_id:'thermal_test',state:'stale',scope:'One-dimensional wall',stale_reasons:['project_revision','<script>bad</script>']}],checked_statements:[],artifacts:[]});
  assert.ok(html.includes('限制说明已核验') && html.includes('历史数值不可交付'));
  assert.ok(html.includes('不改变记录状态') && html.includes('project_revision'));
  assert.ok(!html.includes('<script>') && html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('m²·K/W'));
});

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
