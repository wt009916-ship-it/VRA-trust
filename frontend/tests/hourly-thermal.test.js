import test from 'node:test';
import assert from 'node:assert/strict';
import {hourlyThermalMarkup, temperatureProfileMarkup, bindHourlyThermal} from '../src/hourly-thermal.js';

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

const temperatureTimes = Array.from({length: 24}, (_, i) => ({month: 2, day: 21, hour_ending: i + 1}));
const temperatureProfile = (values, name = 'ROOM') => ({selected_for: 'heating_coincident_peak', times: temperatureTimes, zones: {[name]: {temperature_C: values}}});

test('temperature display preserves negative and zero values, constant series and escaped names', () => {
  for (const value of [-10, 0, 20]) {
    const html = temperatureProfileMarkup(temperatureProfile(Array(24).fill(value), '<img>'), '<img>');
    assert.ok(html.includes('<polyline') && html.includes('°C') && html.includes('纵轴自动缩放'));
    assert.equal((html.match(/<tr><td>/g) || []).length, 24);
    assert.ok(!html.includes('<img>') && !html.includes('NaN') && !html.includes('Infinity'));
    assert.ok(html.includes(`<td>${value}</td>`));
  }
});

test('missing, null and nonfinite temperatures never become a curve or zero', () => {
  for (const values of [null, [], Array(23).fill(20), [...Array(23).fill(20), null], Array(24).fill(NaN), Array(24).fill(Infinity)]) {
    const html = temperatureProfileMarkup(temperatureProfile(values), 'ROOM');
    assert.ok(html.includes('不可用') && !html.includes('<polyline'));
  }
});

test('zone selection replaces the full temperature panel and invalid selection removes prior values', () => {
  const receipt = {status: 'calculated_model_scenario', summary: {zones: [{zone_name: 'ROOM'}, {zone_name: 'OTHER'}],
    peak_day_profiles: [{...temperatureProfile(Array(24).fill(13)), zones: {ROOM: {temperature_C: Array(24).fill(13)}, OTHER: {temperature_C: Array(24).fill(27)}}}]}};
  let onChange;
  const select = {value: '0', addEventListener(type, callback) {assert.equal(type, 'change'); onChange = callback;}};
  const target = {innerHTML: ''};
  const root = {querySelector(selector) {return selector === '[data-temperature-zone]' ? select : target;}};
  bindHourlyThermal(root, receipt);
  onChange(); assert.ok(target.innerHTML.includes('<td>13</td>'));
  select.value = '1'; onChange(); assert.ok(target.innerHTML.includes('<td>27</td>') && !target.innerHTML.includes('<td>13</td>'));
  select.value = 'unknown'; onChange(); assert.ok(!target.innerHTML.includes('<polyline') && target.innerHTML.includes('有效分区'));
  bindHourlyThermal({querySelector() {throw Error('stale must not bind');}}, {...receipt, status: 'stale'});
});
