import fs from 'node:fs';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const root='C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108';
const {readRequestProgressMarkup}=await import(pathToFileURL(root+'/frontend/src/agent-requests.js'));
const {checkedDeliveryMarkup}=await import(pathToFileURL(root+'/frontend/src/agent-artifacts.js'));
const data=JSON.parse(fs.readFileSync('C:/Users/18483/AppData/Local/Temp/vra-phase-candidate-20261108/4b/results.json','utf8'));
const rows=[];
for(const id of ['P01','P07','P08']){
 const t=data.cases.find(c=>c.id===id).task;
 const progress=readRequestProgressMarkup(t);const result=checkedDeliveryMarkup(t.answer);
 const partial=id!=='P01';
 assert.equal(progress.includes('整体记录仍受限'),partial);
 if(partial){
  assert.ok(!t.answer.artifacts[0].verified);
  assert.ok(result.includes('CSV观测窗口'));
  assert.ok(!progress.includes('所选结果已核验'));
  for(const row of t.answer.checked_statements)for(const fact of row.facts)assert.ok(result.includes(fact.label));
 }
 rows.push({id,partial_label:partial,actual_model_task:true,rendered_selected_fields:true});
}
const receipt={rows,browser:false,source:'Actual frozen candidate model task records rendered by current frontend functions',passed:true};
fs.writeFileSync('C:/Users/18483/AppData/Local/Temp/vra-next-intent-pair-20261108/frontend-render.json',JSON.stringify(receipt,null,2));
console.log(JSON.stringify(receipt));
