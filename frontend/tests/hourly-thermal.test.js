import test from 'node:test';
import assert from 'node:assert/strict';
import {hourlyThermalMarkup} from '../src/hourly-thermal.js';

test('stale and unavailable results cannot display a residual numeric summary', () => {
  assert.equal(hourlyThermalMarkup(null), '');
  const html = hourlyThermalMarkup({status: 'unavailable', reason: '<script>bad</script>', summary: {building: {heating_peak: {value_W: 123456}}}});
  assert.ok(html.includes('缺少可核验') && !html.includes('123.46') && !html.includes('<script>'));
});

test('real zero, hourly semantics, source escaping and accessible values survive rendering', () => {
  const times = Array.from({length: 24}, (_, i) => ({month: 1, day: 21, hour_ending: i + 1}));
  const html = hourlyThermalMarkup({status: 'calculated_model_scenario', model_sha256: '<img>', summary: {
    environment: {EnvironmentType: 3, EnvironmentName: '<script>'}, hour_count: 8760, zones: [],
    building: {heating_peak: {value_W: 8148.148, time: times[0]}, cooling_peak: {value_W: 0, time: times[0]}},
    peak_day_profiles: [{selected_for: 'heating_coincident_peak', times, building: {heating_W: times.map(() => 8148.148), cooling_W: times.map(() => 0)}}],
  }});
  for (const text of ['8.15', '0 <small>kW', '小时平均', '不等于设计容量', '不等于电耗', '24 小时数值', 'SQL', 'polyline']) assert.ok(html.includes(text), text);
  assert.ok(!html.includes('<script>') && !html.includes('<img>') && !html.includes('NaN'));
});

test('incomplete curves are not silently padded or drawn', () => {
  const html = hourlyThermalMarkup({status: 'calculated_model_scenario', summary: {building: {}, zones: [], peak_day_profiles: [{times: [], building: {heating_W: [null]}}]}});
  assert.ok(html.includes('曲线不可用，未补零') && !html.includes('<polyline'));
});
