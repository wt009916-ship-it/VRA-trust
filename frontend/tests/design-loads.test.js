import test from 'node:test';
import assert from 'node:assert/strict';
import {designLoadsMarkup} from '../src/design-loads.js';

test('design loads distinguish units, native multipliers, scenario and source mismatch', () => {
  const html = designLoadsMarkup({status:'calculated_model_scenario',site_comparison:'declared_site_differs_from_weather',
    basis:{declared_site:{name:'Golden'},design_days:[]},weather_station:{city:'Other'}, rows:[
      {zone_name:'<script>x</script>',load_type:'Heating',calculated_sensible_load_W:1542.056,
        user_adjusted_sensible_load_W:1927.57,zone_multiplier:3,zone_list_multiplier:1,
        peak:{design_day:'Original day',date_time:'1/21 24:00:00'}}]});
  for (const text of ['1.542','1.928','原生负荷','原生引擎采用的位置','坐标相近不等于已验证','设备总容量','Golden','Other']) {
    assert.ok(html.includes(text),text);
  }
  assert.ok(!html.includes('<script>'));
});

test('unavailable loads never render numeric rows even if an inconsistent payload contains them', () => {
  const html = designLoadsMarkup({status:'unavailable',reason:'missing<script>',rows:[{calculated_sensible_load_W:999999}]});
  assert.ok(html.includes('未取得可核验') && !html.includes('999.999') && !html.includes('<script>'));
});

test('null/stale metrics do not show design load results', () => {
  assert.equal(designLoadsMarkup(null),'');
  assert.equal(designLoadsMarkup(undefined),'');
});
