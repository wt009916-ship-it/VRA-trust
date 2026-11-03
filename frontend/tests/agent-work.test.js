import test from 'node:test';
import assert from 'node:assert/strict';
import {agentWorkMarkup,modelMarkup} from '../src/agent-work-ui.js';

test('agent work UI shows executable provenance, draft status and a continuation form',()=>{
  const html=agentWorkMarkup({mode:'provider',status:'partial',model_tool_calls:2,events:[],llm_commentary:'<img onerror=x>',
    work_plans:[{goal:'<unsafe>',steps:[{purpose:'读取原件',tool:'ifc_source_inventory',depends_on:[],status:'failed',error:'missing'}]}],
    input_questions:[{question:'请补充窗面积',why_needed:'用于同范围比选'}],work_products:[]});
  assert.match(html,/模型自主工程调用 2/);assert.match(html,/执行失败/);assert.match(html,/根据补充继续任务/);
  assert.match(html,/&lt;img/);assert.ok(!html.includes('<img'));assert.match(html,/AI工程分析/);
});

test('model tables and headings render without executing HTML or invented links',()=>{
  const html=modelMarkup('## 来源\n|材料|取舍|\n|---|---|\n|**LaB6**|<img src=x onerror=1>|\n- `source_id`\n[假链接](javascript:alert(1))');
  assert.match(html,/<table>/);assert.match(html,/<strong>LaB6<\/strong>/);assert.match(html,/&lt;img/);
  assert.ok(!html.includes('<img'));assert.ok(!html.includes('<a '));assert.match(html,/<h4>来源/);
});
