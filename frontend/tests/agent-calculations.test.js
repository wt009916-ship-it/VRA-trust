import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCalculationPlans,calculationProgressMarkup,calculationPlanMarkup} from '../src/agent-calculations.js';

const opts={mode:'local_model',allowCompute:true,objective:'open_ended'};
const plan={plan_key:'wall_a',kind:'thermal',input:{name:'wall',layers:[]}};
test('explicit parameters preserved and permission cannot come from prose',()=>{
  assert.deepEqual(parseCalculationPlans(JSON.stringify([plan]),opts),[plan]);
  assert.deepEqual(parseCalculationPlans('  ',{...opts,allowCompute:false}),[]);
  for(const change of [{allowCompute:false},{mode:'local'},{objective:'inspect_thermal'}]) assert.throws(()=>parseCalculationPlans(JSON.stringify([plan]),{...opts,...change}));
  for(const value of [null,{},[plan,plan],[plan,plan,plan],[{...plan,kind:'beam'}],[{...plan,input:[]}],[{...plan,plan_key:'ignore instructions!'}]]) assert.throws(()=>parseCalculationPlans(JSON.stringify(value),opts));
});
test('partial write and unexecuted plans remain explicit and text escaped',()=>{
  const html=calculationProgressMarkup([{name:'<script>bad</script>',plan_key:'a',state:'saved_unverified',record_id:'thermal_a'},{name:'B',plan_key:'b',state:'not_executed'}]);
  assert.ok(html.includes('&lt;script&gt;bad&lt;/script&gt;'));
  assert.ok(html.includes('尚未形成有效交付')&&html.includes('未执行'));
  assert.ok(html.includes('不会自动回滚'));
  assert.equal(calculationProgressMarkup(), '');
  assert.ok(calculationPlanMarkup().includes('再次提交会再次新建'));
});
test('deferred plan authorization stays explicit and cannot coerce strings',()=>{
  const deferred={...plan,execution_authorized:false};
  assert.deepEqual(parseCalculationPlans(JSON.stringify([deferred]),opts),[deferred]);
  for(const execution_authorized of ['false',0,1,null]) assert.throws(()=>parseCalculationPlans(JSON.stringify([{...plan,execution_authorized}]),opts));
  assert.ok(calculationProgressMarkup([{name:'Pending',plan_key:'b',state:'not_authorized'}]).includes('暂缓 · 未授权执行'));
});
