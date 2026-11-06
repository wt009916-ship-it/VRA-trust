import test from 'node:test';
import assert from 'node:assert/strict';
import {engineeringArtifactMarkup} from '../src/agent-engineering.js';
import {professionalArtifactMarkup,checkedDeliveryMarkup} from '../src/agent-artifacts.js';
import {parseCalculationPlans} from '../src/agent-calculations.js';

const base={name:'<svg>Declared source',record_id:'engineering_abc',project_id:'project_a',scope:'Not certification',status:'calculated',input:{}};
test('beam outside applicability does not render engineering values',()=>{
 const html=engineeringArtifactMarkup({...base,kind:'engineering_review',status:'outside_model_screen',result:{metrics:{max_deflection_m:99},model_screening:['<script>screen'],limitations:[]}});
 assert.ok(html.includes('不在本交付中作为工程结果显示'));
 assert.ok(!html.includes('99')&&!html.includes('<script>')&&!html.includes('<svg>'));
 assert.ok(html.includes('/beam-analyses/engineering_abc/report.html'));
});
test('stale and absent engineering records retain no numerical output',()=>{
 assert.equal(engineeringArtifactMarkup(null),'');
 const html=professionalArtifactMarkup({...base,kind:'engineering_review',status:'stale',result:{metrics:{max_deflection_m:123}}});
 assert.ok(html.includes('不能复用历史数值')&&!html.includes('123'));
});
test('schedule preserves unknown forecast and unresolved constraints',()=>{
 const html=engineeringArtifactMarkup({...base,kind:'schedule_review',status:'constraints_unresolved',input:{time_origin:'<svg> day zero'},result:{planned:{duration_days:'8',critical_tasks:['A','B','D'],resources:{status:'conflict'}},forecast:{as_of_day:'3',finish_day:null,finish_variance_days:null,status:'incomplete'},limitations:[]}});
 assert.ok(html.includes('A、B、D')&&html.includes('并非唯一串行路径')&&html.includes('完工日 —')&&html.includes('资源约束未解决'));
 assert.ok(!html.includes('<svg>'));
});
test('operation window and missing evidence cannot imply health or distinct failures',()=>{
 const html=engineeringArtifactMarkup({...base,kind:'operation_review',status:'no_rule_event',input:{data_nature:'synthetic',clock_basis:'offset_aware'},result:{quality:{first_time:'start',last_time:'end',sample_count:7,cell_issue_count:1,gap_count:0},rules:[{name:'Rule <img>',event_count:0,unknown_samples:1,state:'insufficient_evidence',events_truncated:false}],limitations:[]}});
 assert.ok(html.includes('不代表健康')&&html.includes('未知样本 1')&&html.includes('不能相加当作独立故障数')&&!html.includes('<img>'));
});
test('new plan kinds preserve typed payload and explicit consent',()=>{
 for(const kind of ['engineering','schedule','operation']){
  const p=[{plan_key:'p',kind,input:{name:'explicit'}}];
  assert.deepEqual(parseCalculationPlans(JSON.stringify(p),{mode:'local_model',objective:'open_ended',allowCompute:true}),p);
  assert.throws(()=>parseCalculationPlans(JSON.stringify(p),{mode:'local_model',objective:'open_ended',allowCompute:false}));
 }
 const html=checkedDeliveryMarkup({checked_statements:[{name:'window',record_id:'operation_a',facts:[{label:'Events',value:'2',unit:'count',period:'observed_window',study_years:null,area_m2:null,source_path:'derived:sum'}]}]});
 assert.ok(html.includes('CSV观测窗口 · 非年量'));
});
