import fs from 'node:fs';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const root='C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108';
const out='C:/Users/18483/AppData/Local/Temp/vra-nonnumeric-20261108';
const {readRequestProgressMarkup}=await import(pathToFileURL(root+'/frontend/src/agent-requests.js'));
const {checkedDeliveryMarkup}=await import(pathToFileURL(root+'/frontend/src/agent-artifacts.js'));
const raw=JSON.parse(fs.readFileSync(out+'/http-flow.json','utf8'));
const results={};
for(const [key,t] of Object.entries(raw.cases)){
 const progress=readRequestProgressMarkup(t),values=checkedDeliveryMarkup(t.answer);
 if(key==='review'){
  assert.ok(progress.includes('当前记录状态：已计算'));
  assert.ok(progress.includes('状态与口径已复核 · 未交付数值'));
  assert.ok(!values.includes('<dd>'));
 }
 if(key==='ask'){
  assert.ok(progress.includes('等待澄清 · 任务未完成'));
  assert.ok(progress.includes('请确认是否只需要传热系数U？'));
  assert.ok(!values.includes('<dd>'));
 }
 if(key==='reply'){
  assert.ok(!progress.includes('请补充确认'));
  assert.ok(values.includes('0.735294117647'));
 }
 if(key==='withdrawn'){
  assert.ok(progress.includes('旧说明已撤下'));
  assert.ok(!progress.includes('当前记录状态：已计算'));
 }
 fs.writeFileSync(out+'/render-'+key+'.html','<!doctype html><meta charset="utf-8">'+progress+values);
 results[key]=true;
}
const hostile=structuredClone(raw.cases.ask);
hostile.answer.clarification_requests[0].question='<script>steal()</script>';
assert.ok(!readRequestProgressMarkup(hostile).includes('<script>'));
fs.writeFileSync(out+'/render-receipt.json',JSON.stringify({results,escaped_clarification:true,browser:false,source:'Current renderer using actual HTTP flow responses; scripted planner, not a model pass.'},null,2));
console.log(JSON.stringify({results,escaped_clarification:true,browser:false}));
