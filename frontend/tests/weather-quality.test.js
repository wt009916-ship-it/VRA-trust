import test from 'node:test';
import assert from 'node:assert/strict';
import {weatherQualityMarkup} from '../src/weather-quality.js';

test('weather conditions are visible, source-bound and safely escaped', () => {
  const html = weatherQualityMarkup({station:{city:'<img src=x>'},hours:8760,scope:'年度筛查',source_sha256:'abc',policy_version:'v1',
    conditions:[{field:'rain',count:2,first_line:9,last_line:30,message:'缺测<script>'}],limitations:['非实测认证']});
  for (const value of ['存在缺测或推导条件','1 类缺测或推导条件','不等于零','abc','非实测认证','并非每行均缺测']) assert.ok(html.includes(value));
  assert.ok(!html.includes('<img') && !html.includes('<script>'));
});

test('absent or stale receipt is never shown as a weather pass', () => {
  assert.equal(weatherQualityMarkup(null),'');
  assert.equal(weatherQualityMarkup(undefined),'');
});

test('weather notices use readable field names without claiming project readiness', () => {
  const html=weatherQualityMarkup({station:{city:'Golden'},hours:8760,conditions:[
    {field:'liquid_precipitation_depth',count:2,first_line:9,last_line:10,message:'缺测'}]});
  assert.ok(html.includes('液态降水量') && !html.includes('liquid_precipitation_depth'));
  assert.ok(!html.includes('可运行'));
});
