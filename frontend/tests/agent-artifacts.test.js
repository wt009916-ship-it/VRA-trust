import test from 'node:test';
import assert from 'node:assert/strict';
import {costArtifactMarkup,modelCommentaryMarkup} from '../src/agent-artifacts.js';

const artifact={kind:'material_cost_review',project_id:'project_a',cost_id:'cost_a',name:'Synthetic panel',status:'calculated',scope:'Declared materials only',currency:'USD',material_total:'146.02',functional_scope:'Panels',exclusions:['Tax','Transport'],as_of:'2026-11-06',tax_basis:'excluded',checked_at:'2026-11-06',notice:'Verified source fields',rows:[{name:'panel',unit:'m2',net_quantity:'19.5',purchase_quantity:'20.280',amount:'146.02',quantity_method_text:'净量×(1+损耗率)，此计量单位不向上取整',waste_ratio:'0.04',quantity_in_quote_unit:'20.280',quote_unit:'m2',unit_price:'7.2',money_method:'HALF_UP 0.01 per line',quantity_source:'Synthetic area',waste_source:'Declared allowance',price_source:'Synthetic quote',price_version:'v2',price_valid_from:'2026-01-01',price_valid_until:'2026-12-31',missing:[]}]};

test('verified quantities retain exact decimal strings and row-specific methods',()=>{
  const html=costArtifactMarkup(artifact);
  assert.ok(html.includes('20.280 m2') && html.includes('146.02 USD'));
  assert.ok(html.includes('此计量单位不向上取整'));
  assert.ok(html.includes('声明不含税') && html.includes('Tax；Transport'));
  assert.ok(html.includes('/material-costs/cost_a/report.html'));
});
test('stale artifacts do not render historical amount or rows even when supplied',()=>{
  const html=costArtifactMarkup({...artifact,status:'stale'});
  assert.ok(!html.includes('146.02') && !html.includes('20.280'));
  assert.ok(html.includes('— USD') && html.includes('来源或版本已变化'));
});
test('missing line values remain unknown and user source text is escaped',()=>{
  const html=costArtifactMarkup({...artifact,name:'<img onerror=x>',material_total:null,rows:[{...artifact.rows[0],amount:null,price_source:'<script>attack</script>',missing:['unit_price']}]});
  assert.ok(html.includes('— USD') && !html.includes('<img') && !html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;') && html.includes('unit_price'));
});
test('raw model errors remain outside the verified task result presentation',()=>{
  const task={llm_commentary_policy:'audit_only',llm_commentary:'面积向上取整为21 m2，已获安全认证'};
  const html=modelCommentaryMarkup(task);
  assert.ok(!html.includes('21 m2') && !html.includes('已获安全认证'));
  assert.ok(html.includes('仅保留在任务审计记录'));
  assert.ok(modelCommentaryMarkup({llm_commentary:'<img>'}).includes('&lt;img&gt;'));
});
