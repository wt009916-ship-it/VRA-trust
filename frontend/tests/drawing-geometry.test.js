import test from 'node:test';
import assert from 'node:assert/strict';
import {geometryMarkup,scaleResult,processingInput} from '../src/drawing-geometry-ui.js';

test('drawing processing preserves source comparison, incomplete auto direction and filter damage disclosure',()=>{
  const record={drawing_id:'drawing_x',status:'review_required',result:{processing:{transform:{angle_degrees_clockwise:0,source_size:[360,240]},state:'auto_not_applied',resampling:'none',auto_suggestion:{status:'ambiguous_directions',support_ratio:.6},filter_difference:{changed_pixels:81,dark_pixels_removed:81,dark_pixels_added:0}}}};
  const html=geometryMarkup(record,'/projects/project_x');
  for(const text of ['本次未自动旋转','不是正确概率','暗像素减少 81','source-preview.png','filter-difference.png','DPI 不代表工程比例尺','同页等比假设'])assert.ok(html.includes(text),text);
  assert.equal(geometryMarkup({...record,status:'stale'},'/x'),'');
});

test('conflicting or stale scale never emits a current scale number',()=>{
  const scale={status:'conflicting_references',result:{status:'conflicting_references',scale_m_per_px:null,references:[{label:'<img src=x>',distance_px:100,length_m:6,m_per_px:.06}]}};
  const html=scaleResult(scale);assert.ok(html.includes('不能换算'));assert.ok(!html.includes('条件尺度'));assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img src=x>'));
  assert.ok(!scaleResult({...scale,status:'stale'}).includes('0.06'));
});

test('nonmanual UI resets unused angle while explicit API contract remains strict',()=>{
  const form=new FormData();form.set('deskew_mode','auto');form.set('angle_degrees','7');
  assert.deepEqual(processingInput(form),{deskew_mode:'auto',angle_degrees:0,median_filter:false});
  form.set('deskew_mode','manual');form.set('median_filter','on');
  assert.deepEqual(processingInput(form),{deskew_mode:'manual',angle_degrees:7,median_filter:true});
  form.set('angle_degrees','');assert.throws(()=>processingInput(form),/旋转角度/);
});
