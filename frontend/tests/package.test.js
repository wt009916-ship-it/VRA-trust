import test from 'node:test';
import assert from 'node:assert/strict';
import {packageMarkup,packageDocument} from '../src/package-ui.js';

test('package report exposes omitted costs and escapes user and evidence text',()=>{
  const html=packageMarkup({name:'<img onerror=1>',comparison_basis:'Shared scope',horizon_years:20,carbon_boundary:'A1-A3',limitations:['<script>'],rows:[{
    name:'<b>Unknown package</b>',state:'NEEDS_EVIDENCE',initial_cost_cny:null,within_budget:null,
    discounted_declared_outlay_cny:null,initial_material_kgco2e:null,items:[],cashflows:[],
    engineering_gaps:['<img>'],cost_gaps:['拆除缺含税总额'],cashflow_gaps:[],carbon_gaps:[]}]});
  assert.match(html,/拆除缺含税总额/);assert.match(html,/待补证/);assert.match(html,/&lt;img/);
  assert.ok(!html.includes('<img'));assert.ok(!html.includes('<script>'));assert.match(html,/>—</);
  const doc=packageDocument({name:'Test',comparison_basis:'Test',horizon_years:1,carbon_boundary:'A1-A3',rows:[],limitations:[]},
    {locator:'</pre><script>alert(1)</script>',record_id:'sustainability_test'});
  assert.match(doc,/sustainability_test/);assert.ok(!doc.includes('<script>'));assert.match(doc,/未签章/);
});
