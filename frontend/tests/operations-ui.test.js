import test from 'node:test';
import assert from 'node:assert/strict';
import {operationsResult} from '../src/operations-ui.js';

test('operational result preserves missing data, adverse quality and unconfirmed diagnosis',()=>{
  const html=operationsResult({input:{name:'<script>attack</script>'},status:'events_detected',result:{data_nature:'simulation',equipment:'Test',quality:{sample_count:2,cell_issue_count:1,gap_count:1,irregular_intervals:1,first_time:'2026-01-01',last_time:'2026-01-02'},channels:[{name:'T',channel_id:'t',unit:'degC',input_unit:'degF',valid_samples:0,missing_or_invalid:2,minimum:null,maximum:null,sample_mean:null}],rules:[],series_preview:[{line:2,timestamp:'2026-01-01',values:{t:null}}],limitations:[]}});
  assert.ok(!html.includes('<script>'));assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(html.includes('数据不完整'));assert.ok(html.includes('故障根因未确认'));
  assert.ok(html.includes('<td>— / —</td>'));assert.ok(html.includes('degC（输入 degF）'));
});

test('stale operational output never displays old numerical conclusions',()=>{
  const html=operationsResult({input:{name:'Previous analysis'},status:'stale',result:null});
  assert.ok(html.includes('需重新分析'));assert.ok(!html.includes('样本均值'));
});
