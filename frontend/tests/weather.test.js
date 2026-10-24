import test from 'node:test';
import assert from 'node:assert/strict';
import {temperatureSegments, climateChart} from '../src/weather-ui.js';

test('weather chart breaks at absent/null months and preserves an actual zero',()=>{
  const months=[{month:1,temperature_c:0,solar_kwh_m2:0},{month:2,temperature_c:null,solar_kwh_m2:null},{month:3,temperature_c:12,solar_kwh_m2:40},{month:4,temperature_c:14,solar_kwh_m2:50},{month:6,temperature_c:20,solar_kwh_m2:70}];
  assert.deepEqual(temperatureSegments(months).map(s=>s.map(m=>m.month)),[[1],[3,4],[6]]);
  const html=climateChart(months);
  assert.equal((html.match(/<circle /g)||[]).length,4);
  assert.equal((html.match(/<rect /g)||[]).length,4);
  assert(!html.includes('NaN'));
});

test('empty climate data cannot draw an invented curve or bars',()=>{
  const html=climateChart([]);
  assert(!html.includes('<polyline'));
  assert(!html.includes('<rect '));
  assert(!html.includes('NaN'));
});
