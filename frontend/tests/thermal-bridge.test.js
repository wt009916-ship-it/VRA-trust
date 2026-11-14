import test from 'node:test';
import assert from 'node:assert/strict';
import {nullableNumber,geometryMarkup,resultMarkup,drawTemperature,heatColor,fieldBounds} from '../src/thermal-bridge-view.js';

const field={status:'needs_refinement',temperature_c:[[0,10],[20,30]],x_edges_m:[0,1,3],y_edges_m:[0,2,4],
  boundary_heat_into_domain_w_per_m:{left:20,right:-20,bottom:0,top:0},energy_balance_w_per_m:0,
  mesh_check:{coarse_cells:1,fine_cells:4,max_temperature_difference_k:.25,max_edge_heat_difference_relative:.02,fixed_temperature_corner_discontinuities:[]},
  probes:[{name:'<script>alert(1)</script>',x:1,y:2,temperature_c:15}],limitations:['Synthetic reference only']};
const record={thermalbridge_id:'thermalbridge_test',status:'needs_refinement',input:{name:'<img src=x onerror=bad()>'},result:field,source_notice:'Declared reference'};

test('unknown stays null, zero stays zero, nonfinite and boolean values rejected',()=>{
  assert.equal(nullableNumber(''),null);assert.equal(nullableNumber('  '),null);assert.equal(nullableNumber(null),null);
  assert.equal(nullableNumber('0'),0);assert.equal(nullableNumber('-7.5'),-7.5);
  for(const value of [true,false,'Infinity','NaN'])assert.throws(()=>nullableNumber(value));
});
test('geometry preserves physical aspect and y-up coordinates; names are escaped',()=>{
  const html=geometryMarkup({width:2,height:1,length_unit:'m',regions:[{name:'<script>',x0:0,x1:1,y0:0,y1:.5,conductivity:null}]});
  assert.match(html,/viewBox="0 0 720 360"/);assert.match(html,/y="180"/);assert.match(html,/height="180"/);
  assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);
  assert.match(geometryMarkup({width:null,height:1}),/填写截面尺寸/);
});
test('diagnostic and missing/stale results cannot be presented as engineering approval',()=>{
  const html=resultMarkup(record,'/projects/test/thermal-bridges');
  assert.match(html,/需要细化网格/);assert.match(html,/仅用于检查模型/);assert.match(html,/W\/m 延伸长度/);
  assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img src=x'));
  const stale=resultMarkup({...record,status:'stale'},'/projects/test/thermal-bridges');
  assert.ok(!stale.includes('<canvas'));assert.ok(!stale.includes('temperatures.csv'));assert.match(stale,/当前结果不可用/);
  const missing=resultMarkup({...record,status:'incomplete',result:{status:'incomplete',missing:['regions[0].conductivity']}},'/projects/test/thermal-bridges');
  assert.match(missing,/未计算温度或热流/);assert.ok(!missing.includes('<canvas'));
});
test('heat map uses true nonuniform cell geometry with bottom row at bottom',()=>{
  const rects=[],colors=[],canvas={getContext:()=>({set fillStyle(v){colors.push(v);},fillRect:(...args)=>rects.push(args)})};
  drawTemperature(canvas,field);
  assert.equal(canvas.width,300);assert.equal(canvas.height,400);
  assert.deepEqual(rects[0],[0,200,100.2,200.2]);assert.deepEqual(rects[1],[100,200,200.2,200.2]);
  assert.deepEqual(rects[2],[0,0,100.2,200.2]);assert.equal(colors[0],heatColor(0,0,30));assert.equal(colors[3],heatColor(30,0,30));
  assert.deepEqual(fieldBounds(field),{low:0,high:30});assert.equal(fieldBounds(null),null);
  assert.equal(heatColor(18,18,18),'hsl(120 65% 46%)');
});
