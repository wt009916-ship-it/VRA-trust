import test from 'node:test';
import assert from 'node:assert/strict';
import {estimateMarkup} from '../src/sustainability-ui.js';

test('unknown quotations render as missing rather than zero',()=>{
  assert.match(estimateMarkup([]),/尚无已提交报价/);
  const html=estimateMarkup([{name:'<img src=x onerror=alert(1)>',quantity:1,unit:'m2',gwp_boundary:null,
    initial_cost_cny:null,within_budget:null,initial_embodied_kgco2e:null,horizon_material_kgco2e:null,
    annual_operating_saving_kgco2:null,partial_horizon_net_reduction_kg:null}]);
  assert.match(html,/缺报价/); assert.match(html,/&lt;img/); assert.ok(!html.includes('<img'));
});

test('explicit zero cost is distinct from missing, and negative net reduction survives',()=>{
  const html=estimateMarkup([{name:'Test',quantity:1,unit:'kg',gwp_boundary:'A1-A3',initial_cost_cny:0,
    within_budget:true,initial_embodied_kgco2e:10,horizon_material_kgco2e:20,
    annual_operating_saving_kgco2:0,partial_horizon_net_reduction_kg:-20}]);
  assert.match(html,/预算内/); assert.match(html,/>-20</); assert.match(html,/>0</);
});
