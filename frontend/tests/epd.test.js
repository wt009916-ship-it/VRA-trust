import test from 'node:test';
import assert from 'node:assert/strict';
import {epdResultMarkup} from '../src/epd-ui.js';

test('EPD output keeps unknown distinct from zero and escapes source text',()=>{
  const r={dataset:{name:'<img onerror=1>',dataset_type:'average dataset',region:'DE',source_url:'https://www.oekobaudat.de/',registration:'',uuid:'uuid',version:'v1',valid_until_year:'2030'},boundary:'A1-A3',quantity:10,unit:'m2',gwp_per_unit:null,material_kgco2e:null,gaps:['<script>unknown unit'],notice:'Declaration only',source_rows:[],release:{sha256:'a'.repeat(64)}};
  const html=epdResultMarkup(r);
  assert.match(html,/平均数据/);assert.match(html,/待复核/);assert.match(html,/签发碳信用：—/);
  assert.match(html,/&lt;img/);assert.match(html,/&lt;script/);assert.ok(!html.includes('<img'));
  assert.match(html,/>— kgCO₂e</);
  const negative=epdResultMarkup({...r,gwp_per_unit:-2,material_kgco2e:-20,gaps:[]});
  assert.match(negative,/-20/);assert.match(negative,/平均数据/);
});
