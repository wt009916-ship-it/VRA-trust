import test from 'node:test';
import assert from 'node:assert/strict';
import {designCheckMarkup} from '../src/design-conditions-ui.js';

test('stale design checks never expose previous matching result',()=>{
  assert.ok(!designCheckMarkup({status:'stale',result:{status:'matching_declared_fields'}},'/projects/p').includes('声明字段一致'));
  assert.ok(designCheckMarkup(null,'/projects/p').includes('不可用'));
});

test('field conflicts and source locators are escaped and retain explicit uncertainty',()=>{
  const record={status:'current',designcheck_id:'designcheck_x',source_snapshot:{input:{edition:'<v1>'}},
    model_snapshot:{evidence:{revision:2}},result:{status:'differences_found',unmapped_model_days:[],
      unverified_sizing_period_types:[],site_fields:[{equal:false}],
      rows:[{model_day:'<img>',source_day:'source',status:'different_fields',model_locator:{line:12},
        source_locator:{line:5},unverified_dependencies:['DaySchedule'],fields:[
          {field:'wind_speed',unit:'m/s',model:'0',source:'3',equal:false},
          {field:'barometric_pressure',unit:'Pa',model:'',source:'101325',equal:false}]}]}};
  const html=designCheckMarkup(record,'/projects/p');
  for(const value of ['存在参数差异','不是来源权威','第 12 行','第 5 行','m/s','Pa','未填写','<td>0</td>','日程引用尚未验证','完整 JSON']) assert.ok(html.includes(value),value);
  assert.ok(!html.includes('<img>')&&!html.includes('<v1>'));
});
