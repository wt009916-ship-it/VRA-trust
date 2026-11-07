import test from 'node:test';
import assert from 'node:assert/strict';
import {outputContractMarkup,readRequestProgressMarkup} from '../src/agent-requests.js';
const plan={items:[{request_key:'wall',question_excerpt:'Explain <script>alert(1)</script>',fact_keys:['total_resistance_m2k_w'],explanation_topics:['area']}]};
test('inferred plan and source-generated explanation are distinguished and escaped',()=>{
 const html=outputContractMarkup({infer_outputs:true,answer:{output_plan:plan,output_contract_coverage:'fulfilled',
   requested_outputs:[{request_key:'wall',state:'fulfilled',missing_fact_keys:[],explanations:[{topic:'area',text:'R无需建筑面积 <img src=x>'}]}]}});
 for(const text of ['模型从原问题解析','应用依据当前核验来源生成','总热阻 R','R无需建筑面积'])assert.ok(html.includes(text));
 assert.ok(!html.includes('<script>')&&!html.includes('<img'));
});
test('missing requested metric is not presented as full output completion',()=>{
 const html=readRequestProgressMarkup({infer_outputs:true,read_request_progress:[{request_key:'wall',kind:'thermal',purpose:'results',state:'required_facts_missing'}],
   answer:{output_plan:plan,output_contract_coverage:'incomplete',requested_outputs:[{request_key:'wall',state:'incomplete',missing_fact_keys:['total_resistance_m2k_w'],explanations:[]}]}});
 assert.ok(html.includes('尚缺指标：总热阻 R')&&html.includes('尚缺所问指标'));
 assert.ok(!html.includes('计划内产物已交付'));
});
test('changed output contract hides historical explanation',()=>{
 const html=outputContractMarkup({infer_outputs:true,answer:{output_plan:plan,output_contract_coverage:'contract_changed',
   requested_outputs:[{request_key:'wall',state:'fulfilled',explanations:[{text:'STALE_NUMBER_999'}]}]}});
 assert.ok(html.includes('历史解释已撤下')&&!html.includes('STALE_NUMBER_999'));
 assert.ok(outputContractMarkup({infer_outputs:true}).includes('尚未形成'));
 assert.equal(outputContractMarkup({}), '');
});
