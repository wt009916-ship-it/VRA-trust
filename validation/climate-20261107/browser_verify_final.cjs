const fs=require('node:fs/promises'),crypto=require('node:crypto');
module.exports=async(page)=>{
 await page.getByRole('button',{name:'关闭',exact:true}).click();
 await page.getByRole('button',{name:'仿真',exact:true}).click();
 if(!await page.getByRole('button',{name:'运行仿真',exact:true}).isDisabled())throw Error('Invalid weather is runnable');
 await page.getByText('已失效 · 需复核',{exact:true}).waitFor();
 const before=JSON.parse(await fs.readFile('output/playwright/weather-20261107/report.json','utf8'));
 const pid=before.project.project_id,rid=before.run.run_id,base='http://127.0.0.1:18774/api/projects/'+pid;
 const gate=await (await page.request.get(base+'/gate')).json();
 const run=await (await page.request.get('http://127.0.0.1:18774/api/runs/'+rid)).json();
 const jobs=await (await page.request.get(base+'/runs')).json();
 if(gate.can_simulate||gate.weather_quality!==null||run.status!=='stale'||run.metrics!==null||run.weather_quality!==null||jobs.length!==1)throw Error('Weather invalidation failed');
 const evidence=await (await page.request.get(base+'/evidence')).json();const originals=[];
 for(const item of evidence.filter(e=>e.type==='epw')){
   const response=await page.request.get(base+'/files/'+item.source_file);if(!response.ok())throw Error('Original unavailable');
   const digest=crypto.createHash('sha256').update(await response.body()).digest('hex');if(digest!==item.hash)throw Error('Original changed');
   originals.push({name:item.name,hash:digest,review_state:item.review_state});
 }
 await fs.writeFile('output/playwright/weather-20261107/final-api.json',JSON.stringify({gate,run,originals,job_count:jobs.length},null,2));
 await page.screenshot({path:'output/playwright/weather-20261107/stale-final-v4.png'});
};
