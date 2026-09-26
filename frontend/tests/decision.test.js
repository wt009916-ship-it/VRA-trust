import test from 'node:test';
import assert from 'node:assert/strict';
import {optionalNumber, paretoPlot, assessmentMarkup} from '../src/decision-ui.js';

test('blank cost stays unknown while explicit zero is retained',()=>{
  assert.equal(optionalNumber(''),null);assert.equal(optionalNumber('  '),null);
  assert.equal(optionalNumber('0'),0);assert.equal(optionalNumber('.08'),.08);
  assert.throws(()=>optionalNumber('Infinity'));assert.throws(()=>optionalNumber('not a number'));
});
test('stale study does not render historical candidate figures',()=>{
  const markup=assessmentMarkup({status:'stale',assessment:null,stale_reasons:['来源已撤回'],points:[{metrics:{annual_energy_kwh:1234567}}]});
  assert.match(markup,/来源已撤回/);assert.doesNotMatch(markup,/1234567|pareto-plot/);
});
test('scatter plot does not plot missing costs or execute material names',()=>{
  const row={option_id:'C01',name:'<script>alert(1)</script>',status:'FEASIBLE',values:{energy_kwh:100,cost_cny:20}};
  const markup=paretoPlot({rows:[row,{...row,option_id:'UNKNOWN',values:{energy_kwh:50,cost_cny:null}}],pareto_option_ids:['C01']});
  assert.match(markup,/&lt;script&gt;/);assert.doesNotMatch(markup,/<script>|UNKNOWN|NaN|Infinity/);
});
test('factor-only staleness offers reevaluation without asserting current winners',()=>{
  const markup=assessmentMarkup({study_id:'study_test',status:'succeeded',assessment:null,assessment_stale:true});
  assert.match(markup,/无需重新仿真/);assert.doesNotMatch(markup,/待复核非支配候选/);
});
