import test from 'node:test';
import assert from 'node:assert/strict';
import {professionalArtifactMarkup} from '../src/agent-artifacts.js';

const base={record_id:'thermal_test',project_id:'project_test',name:'Independent assembly',status:'calculated',checked_at:'2026-11-06',scope:'Declared calculation only',source_status:'USER_DECLARED',source_notice:'Not a certificate'};
const thermal={...base,kind:'thermal_review',input:{rsi_m2k_w:.12,rse_m2k_w:.05,surface_basis:'Declared test films',application:'Opaque uniform wall'},result:{u_w_m2k:100/197,total_resistance_m2k_w:1.97,layer_resistance_m2k_w:1.8,missing:[],limitations:['No annual savings'],layers:[{name:'Layer B',thickness:6,thickness_unit:'cm',thickness_m:.06,conductivity:30,conductivity_unit:'mW/(m K)',conductivity_w_mk:.03,correction_factor:1.25,effective_conductivity_w_mk:.0375,resistance_m2k_w:1.6,correction_basis:'Declared correction',source:'Synthetic test source'}]}};
const carbon={...base,kind:'lifecycle_review',record_id:'lifecycle_test',input:{study_years:12,area_m2:927.2,functional_unit:'Office over twelve years',method:'Synthetic GWP',region:'US-CO',activities:[{activity_id:'operation',name:'Operation',quantity:240,unit:'kWh',period:'annual',source:'Synthetic activity',factor:{value:.37,denominator:'kWh',source:'Synthetic factor',publisher:'Audit',version:'new-2',year:2026,region:'*',method:'Synthetic GWP'}}]},result:{boundary_total_kgco2e:1065.6,kgco2e_m2_over_study_period:1065.6/927.2,all_five_stages_entered:false,stages:{operation:{included:true,status:'calculated',kgco2e:1065.6,reason:'Included declared operation'},construction:{included:false,status:'excluded',kgco2e:null,reason:'Explicit exclusion'}},rows:[{activity_id:'operation',kgco2e:1065.6,period_multiplier:12,quantity_in_factor_unit:2880}],missing:[],limitations:['No credits issued']}};

test('thermal receipt exposes original and normalized units and denies annual savings claim',()=>{
  const html=professionalArtifactMarkup(thermal);
  for(const text of ['6 cm → 0.06 m','30 mW/(m K) → 0.03 W/(m·K)','0.0375 W/(m·K)','1.97 m²·K/W','全年节能率：未评估','规范合规：未评估','/thermal/thermal_test/report.html'])assert.ok(html.includes(text),text);
});
test('lifecycle receipt separates excluded stage, annual multiplier, factor version and credits',()=>{
  const html=professionalArtifactMarkup(carbon);
  for(const text of ['1065.6 kgCO₂e','年量 × 12','2880 kWh','版本：new-2','明确排除 · 不计为零排放','已签发信用：—','/lifecycle/lifecycle_test/report.html'])assert.ok(html.includes(text),text);
});
test('stale professional result never renders historical values or inputs as current results',()=>{
  for(const a of [thermal,carbon]){
    const html=professionalArtifactMarkup({...a,status:'stale'});
    assert.ok(html.includes('不显示历史计算数值'));
    assert.ok(!html.includes('1065.6')&&!html.includes('1.97')&&!html.includes('6 cm'));
  }
});
test('unknowns stay unknown and source fields cannot inject HTML',()=>{
  const a=structuredClone(thermal);a.result.u_w_m2k=null;a.result.missing=['rsi'];a.result.layers[0].source='<img onerror=attack>';a.name='<script>attack</script>';
  const html=professionalArtifactMarkup(a);
  assert.ok(html.includes('— W/(m²·K)')&&html.includes('缺参：rsi'));
  assert.ok(!html.includes('<img')&&!html.includes('<script>'));
  const c=structuredClone(carbon);c.input.activities[0].factor.version='<svg onload=attack>';
  assert.ok(!professionalArtifactMarkup(c).includes('<svg'));
});
test('engineering display removes binary tails, retains small nonzero values and leaves inputs intact',()=>{
  const a=structuredClone(carbon);a.result.kgco2e_m2_over_study_period=17.661749999999998;a.result.stages.operation.kgco2e=7.800000000000001;
  const before=JSON.stringify(a),html=professionalArtifactMarkup(a);
  assert.ok(html.includes('17.66175 kgCO₂e/m²')&&html.includes('7.8 kgCO₂e'));
  assert.ok(!html.includes('17.661749999999998')&&!html.includes('7.800000000000001'));
  assert.ok(html.includes('不代表输入精度'));
  assert.equal(JSON.stringify(a),before);
  const t=structuredClone(thermal);t.result.u_w_m2k=1.23456789012345e-10;
  assert.ok(professionalArtifactMarkup(t).includes('1.23456789012e-10 W/(m²·K)'));
});
