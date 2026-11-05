import test from 'node:test';
import assert from 'node:assert/strict';
import {drawingResult,candidateMarkup} from '../src/drawing-ui.js';

test('OCR text and review are escaped and score never presented as correctness probability',()=>{
  const html=candidateMarkup({text:'<img src=x onerror=alert(1)>',recognition_score:.99},{decision:'corrected',effective_text:'<script>x</script>',basis:'source <b>',reviewed_at:'now'});
  assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));
  assert.ok(html.includes('不是正确概率'));assert.ok(html.includes('人工更正'));
});

test('OCR stale result suppresses old text and blank retains absence uncertainty',()=>{
  assert.ok(!drawingResult({status:'stale',result:{text:'OLD'}},'/projects/p').includes('OLD'));
  const html=drawingResult({drawing_id:'drawing_1',result:{page:{page:1,page_count:1},width:600,height:400,candidates:[],limitations:[]}},'/projects/p');
  assert.ok(html.includes('不表示原图没有文字'));assert.ok(!html.includes('drawing-review'));
});

test('OCR review defaults to unreadable, requires basis and preserves image aspect ratio',()=>{
  const html=drawingResult({drawing_id:'drawing_1',result:{page:{page:1,page_count:1},width:1200,height:900,candidates:[{candidate_id:'text_1',text:'6000',polygon_px:[[1,1],[20,1],[20,10],[1,10]]}],limitations:[]}},'/projects/p');
  assert.ok(html.includes('aspect-ratio:1200/900'));assert.ok(html.includes('viewBox="0 0 1200 900"'));
  assert.ok(html.indexOf('value="unreadable"')<html.indexOf('value="confirmed"'));assert.ok(html.includes('minlength="10"'));
});
