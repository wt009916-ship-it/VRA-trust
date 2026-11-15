import test from 'node:test';
import assert from 'node:assert/strict';
import {idealLoadsMarkup} from '../src/ideal-loads.js';

const receipt=()=>({status:'calculated_model_scenario',limitations:['热量不是耗电'],model_sha256:'source',sql_sha256:'native',summary:{environment:{EnvironmentName:'Declared day'},hour_count:24,coverage:{ideal_system_count:1,scope:'declared_ideal_systems_only'},systems:[],aggregate:{zone_total_cooling_W:{energy_kWh:31.28,peak:{value:1303.41,time:{month:7,day:21,hour_ending:15}}},zone_latent_cooling_W:{energy_kWh:7.62},zone_sensible_cooling_W:{energy_kWh:23.66}}}});

test('source failure hides previously calculated numbers',()=>{
  assert.equal(idealLoadsMarkup(null),'');
  for(const status of ['unavailable','stale','not_applicable']){
    const r=receipt();r.status=status;r.reason='<script>bad</script>';
    const html=idealLoadsMarkup(r);assert.ok(!html.includes('31.28')&&!html.includes('<script>'));
    assert.ok(html.includes('未填零'));
  }
});

test('four boundaries and directional heat are separate from electrical consumption',()=>{
  const html=idealLoadsMarkup(receipt());
  for(const text of ['区内交付','供风处理','新风负荷','热回收','31.28','7.62','23.66','1.303','7/21 15:00','热量不等于耗电','原生倍率已包含'])assert.ok(html.includes(text),text);
  assert.ok(!html.includes('NaN')&&!html.includes('undefined'));
});

test('observed zero is displayed and absent values are not silently zero',()=>{
  const r=receipt();r.summary.aggregate.supply_total_heating_W={energy_kWh:0,peak:{value:0,time:null}};
  const html=idealLoadsMarkup(r);assert.ok(html.includes('<td>0</td>')&&html.includes('<td>—</td>'));
});

test('system names controls environment and locator payload are escaped',()=>{
  const r=receipt();r.summary.environment.EnvironmentName='<img onerror=x>';
  r.summary.systems=[{system_name:'<script>x</script>',zone_name:'<svg>',zone_multiplier:3,zone_list_multiplier:2,locators:{x:'<script>'},results:r.summary.aggregate}];
  const html=idealLoadsMarkup(r);assert.ok(!html.includes('<script>')&&!html.includes('<svg>')&&!html.includes('<img onerror'));
  assert.ok(html.includes('&lt;script&gt;')&&html.includes('不再次相乘'));
});
