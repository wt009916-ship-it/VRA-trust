import test from 'node:test';
import assert from 'node:assert/strict';
import {scheduleChart} from '../src/schedule-ui.js';

test('zero-duration milestones remain readable and untrusted task names are escaped',()=>{
  const html=scheduleChart({duration_days:'0',rows:[{task_id:'<script>x</script>',name:'<img src=x onerror=alert(1)>',start_day:'0',finish_day:'0',critical:true}]});
  assert.ok(!html.includes('NaN')&&!html.includes('Infinity'));
  assert.ok(!html.includes('<script>')&&!html.includes('<img'));
  assert.ok(html.includes('&lt;script&gt;')&&html.includes('关键'));
  assert.equal(scheduleChart(null),'');
});
