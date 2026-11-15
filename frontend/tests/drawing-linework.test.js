import test from 'node:test';
import assert from 'node:assert/strict';
import {lineworkMarkup} from '../src/drawing-linework-ui.js';

const record={drawing_id:'drawing_fixture',result:{width:600,height:400,linework:{
  source_size:[1200,900],lines:[{candidate_id:'line_1',points_source_px:[[10,20],[60,20]]}],
  gaps:[{candidate_id:'gap_1',points_source_px:[[60,20],[66,20]],gap_analysis_px:6}],
  limitations:['<script>untrusted text</script>'],truncated:false}},line_reviews:{}};

test('line overlay retains source frame independent of OCR preview rotation and escapes text',()=>{
  const text=lineworkMarkup(record,'/projects/p');
  assert.ok(text.includes('viewBox="0 0 1200 900"'));
  assert.ok(!text.includes('viewBox="0 0 600 400"'));
  assert.ok(text.includes('linework-preview.png')&&!text.includes('/preview.png'));
  assert.ok(text.includes('x1="60" y1="20" x2="66" y2="20"'));
  assert.ok(!text.includes('<script>')&&text.includes('&lt;script&gt;'));
  assert.ok(text.indexOf('value="keep_unknown"')<text.indexOf('value="retain_hypothesis"'));
});

test('stale drawing removes line geometry and exports; rejected gap remains reviewable but not drawn',()=>{
  assert.equal(lineworkMarkup({...record,status:'stale'},'/projects/p'),'');
  const text=lineworkMarkup({...record,line_reviews:{gap_1:{decision:'reject_hypothesis'}}},'/projects/p');
  assert.ok(!text.includes('data-gap-id="gap_1"'));
  assert.ok(text.includes('value="gap_1"'));
});

test('bounded analysis exposes incomplete coverage before opening the overlay',()=>{
  const text=lineworkMarkup({...record,result:{...record.result,linework:{...record.result.linework,truncated:true}}},'/projects/p');
  assert.ok(text.indexOf('已达到分析数量限制，结果不完整。')<text.indexOf('<details>'));
});
