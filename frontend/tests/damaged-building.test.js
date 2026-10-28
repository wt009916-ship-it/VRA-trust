import test from 'node:test';
import assert from 'node:assert/strict';
import {damageMarkup,damageOverlay} from '../src/drawing-damage.js';
import {componentSummary} from '../src/component-ui.js';
import {thermalResults} from '../src/thermal-results.js';
import {readRoute} from '../src/workspace-ui.js';
import {centralDesignDays} from '../src/central-system.js';

test('editing central sizing retains every supplied design day rather than discarding extra conditions',()=>{
  const days=[{kind:'winter',month:1,day:21},{kind:'summer',month:7,day:21},{kind:'summer',month:8,day:15}];
  const rows=centralDesignDays({design_days:days});
  assert.deepEqual(rows,days);rows[2].day=16;assert.equal(days[2].day,15);
  assert.deepEqual(centralDesignDays(null),[{kind:'winter'},{kind:'summer'}]);
});

test('scan repair overlay retains original pixels and visible uncertainty',()=>{
  const analysis={deskew:{applied_degrees:5,supporting_lines:10},repairs:[{id:'<unsafe>',polygon_px:[[1,2],[3,2],[3,4]],added_pixel_count:12,maximum_requested_gap_m:.2}]};
  const html=damageMarkup(analysis);assert.ok(html.includes('非')||html.includes('待复核'));
  assert.ok(html.includes('&lt;unsafe&gt;'));assert.ok(!html.includes('<unsafe>'));
  assert.ok(damageOverlay(analysis).includes('1,2 3,2 3,4'));
});
test('component view retains missing items and real furniture availability',()=>{
  const html=componentSummary({category_counts:{furniture:253},in_scope_count:988,status_counts:{SOURCE_MESH:987,NO_REPRESENTATION:1},triangles:42});
  assert.ok(html.includes('253'));assert.ok(html.includes('缺表示 1'));assert.ok(html.includes('不会自动添加'));
  assert.equal(readRoute('#project/project_'+'a'.repeat(32)+'/components').view,'components');
});
test('central heating shows native gas and pumps, with unknown values distinct',()=>{
  const html=thermalResults({status:'succeeded',warnings_count:0,metrics:{hvac_scope:'central_chiller_boiler_energy',end_uses_kwh:{Heating:{'Natural Gas':123},Pumps:{Electricity:4}},comfort_hours:{}}});
  assert.ok(html.includes('天然气'));assert.ok(html.includes('123'));assert.ok(html.includes('水泵'));
  assert.ok(html.includes('不代表')||html.includes('不等于'));assert.ok(html.includes('—'));
});
