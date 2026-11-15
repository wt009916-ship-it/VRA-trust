import test from 'node:test';
import assert from 'node:assert/strict';
import {comparisonMarkup} from '../src/agent-comparisons.js';
const row={status:'verified',reference:{baseline_id:'thermal_a',candidate_id:'thermal_b'},label:'U',unit:'W/(m2 K)',baseline:'0.625',candidate:'0.45454545454545453',values:{difference:'-0.17045454545454547',relative_change_percent:'-27.2727272727272752'},notice:'同一稳态指标，非全年节能'};
test('comparison labels direction and formats source arithmetic',()=>{
 const html=comparisonMarkup({checked_comparisons:[row]});
 assert.match(html,/差值（对照−基准）/);assert.match(html,/-27.2727272727%/);assert.match(html,/thermal_a/);assert.match(html,/非全年节能/);
});
test('stale or incompatible source hides all historical comparison numbers',()=>{
 for(const status of ['stale','unavailable']){
  const html=comparisonMarkup({checked_comparisons:[{...row,status}]});
  assert.doesNotMatch(html,/0\.625|0\.4545|27\.272/);assert.match(html,status==='stale'?/已撤下/:/不可比较/);
 }
});
test('zero baseline is undefined, difference-only omits percentage column',()=>{
 assert.match(comparisonMarkup({checked_comparisons:[{...row,values:{difference:'7.5',relative_change_percent:null}}]}),/未定义：基准为零/);
 const html=comparisonMarkup({checked_comparisons:[{...row,values:{difference:'7.5'}}]});
 assert.doesNotMatch(html,/<th>相对变化<\/th>|27\.272/);
});
test('source text is escaped and empty tasks add no card',()=>{
 assert.equal(comparisonMarkup({}),'');
 const html=comparisonMarkup({checked_comparisons:[{...row,label:'<script>attack</script>',notice:'<img src=x onerror=attack>'}]});
 assert.doesNotMatch(html,/<script>|<img /);assert.match(html,/&lt;script&gt;/);
});
