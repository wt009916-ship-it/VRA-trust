const fs=require('node:fs/promises'),crypto=require('node:crypto');
module.exports=async(page)=>{
 const out='output/playwright/designload-agent-20261107';
 const before=JSON.parse(await fs.readFile(out+'/agent-native-verified.json','utf8'));
 await page.getByText('核验本次真实运行，显示当前原生分区设计负荷及适用范围。 · succeeded',{exact:true}).click();
 const dialog=page.getByRole('dialog');
 const history=JSON.parse(await dialog.locator('pre').innerText());
 if(history.answer.task_completion!=='incomplete'||history.answer.simulation_artifact.metrics!==null)throw Error('History exposes stale numeric result');
 const task=await(await page.request.get(`http://127.0.0.1:18774/api/projects/${before.report.project.project_id}/agent/${before.task.agent_id}`)).json();
 if(task.answer.simulation_artifact.status!=='stale'||task.answer.simulation_artifact.metrics!==null)throw Error('Current task read not stale');
 if(JSON.stringify(task.events)!==JSON.stringify(before.task.events))throw Error('Historical audit overwritten');
 const originals=[];
 for(const e of before.report.evidence){
  const response=await page.request.get(`http://127.0.0.1:18774/api/projects/${before.report.project.project_id}/files/${e.source_file}`);
  if(!response.ok())throw Error('Original missing');
  const sha=crypto.createHash('sha256').update(await response.body()).digest('hex');
  if(sha!==e.hash)throw Error('Original altered');originals.push({name:e.name,sha256:sha});
 }
 await fs.writeFile(out+'/agent-history-stale-verified.json',JSON.stringify({history,task,originals,audit_events_unchanged:true},null,2));
 await dialog.getByRole('button',{name:'关闭',exact:true}).click();
 await page.getByRole('combobox',{name:'验收目标',exact:true}).selectOption({label:'核验最近一次仿真结果'});
 await page.getByRole('textbox',{name:'项目操作',exact:true}).fill('检查撤回复核后的当前运行，不得显示旧数值。');
 await page.getByRole('button',{name:'执行项目操作',exact:true}).click();
 const region=page.getByRole('region',{name:'当前原生运行结果',exact:true});await region.waitFor();
 await region.getByText('当前状态：stale。未显示历史数值；请复核来源和运行状态。',{exact:true}).waitFor();
 if(await region.locator('tbody tr').count())throw Error('Stale result card still has numeric rows');
 await region.scrollIntoViewIfNeeded();await page.screenshot({path:out+'/agent-stale.png'});
};
