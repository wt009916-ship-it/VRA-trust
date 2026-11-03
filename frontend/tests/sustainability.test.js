import test from 'node:test';
import assert from 'node:assert/strict';
import {estimateMarkup,sourceStatsMarkup} from '../src/sustainability-ui.js';

test('source counters explicitly distinguish records, full texts and absent EPDs',()=>{
  const html=sourceStatsMarkup({metadata_records:154,distinct_title_groups:151,full_texts_archived:36,
    indexed_entries:49,product_epds_obtained:0,engineering_quotes_obtained:0});
  assert.match(html,/154 条DOI/);assert.match(html,/36 篇全文/);assert.match(html,/产品EPD 0/);
  assert.match(html,/不等于合格材料/);assert.equal(sourceStatsMarkup(null),'');
});

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
