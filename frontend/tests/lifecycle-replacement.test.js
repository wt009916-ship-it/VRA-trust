import test from 'node:test';
import assert from 'node:assert/strict';
import {readReplacementFields,replacementResultMarkup} from '../src/lifecycle-replacement-ui.js';

test('missing lifetime stays null and source identity survives draft reading',()=>{
  const values={component_id:'pump-1',component_name:'Test pump',condition:'existing',service_life_years:'12',remaining_life_years:'',life_source:'Declared test scenario',life_evidence_id:'evidence_test',overlap_review:'Reviewed base activities exclude replacements'};
  const processes=[{process:'removal',included:false,reason:'Explicit test exclusion',activity:null}];
  const r=readReplacementFields(n=>values[n],()=>processes);
  assert.equal(r.service_life_years,12);assert.equal(r.remaining_life_years,null);
  assert.equal(r.life_evidence_id,'evidence_test');assert.deepEqual(r.processes,processes);
  assert.equal(r.endpoint,'strictly_before_horizon');assert.equal(r.scope,'same_function_replacements_only');
  values.remaining_life_years='0';assert.equal(readReplacementFields(n=>values[n],()=>[]).remaining_life_years,0);
});

test('ledger shows missing as unknown, exclusions and escaped names',()=>{
  const html=replacementResultMarkup({replacement:{components:[{name:'<script>bad</script>',years:null,count:null,kgco2e:null,all_four_processes_included:false}]}});
  assert(!html.includes('<script>'));assert(html.includes('&lt;script&gt;'));assert(html.includes('寿命缺失'));assert(html.includes('有明确排除过程'));assert(html.includes('—'));
});

test('zero replacements is distinct from missing and unassessed',()=>{
  const html=replacementResultMarkup({replacement:{components:[{name:'long life',years:[],count:0,kgco2e:0,all_four_processes_included:true}]}});
  assert(html.includes('评估期内无替换'));assert(html.includes('<td>0</td>'));
  assert(replacementResultMarkup({}).includes('未单独核算'));
  assert(replacementResultMarkup(null).includes('未单独核算'));
});
