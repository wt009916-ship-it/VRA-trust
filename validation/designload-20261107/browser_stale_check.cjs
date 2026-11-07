const fs=require('node:fs/promises'),crypto=require('node:crypto');
module.exports=async(page)=>{
 await page.getByRole('heading',{name:'报告与依据',exact:true}).waitFor();
 const prior=JSON.parse(await fs.readFile('output/playwright/designload-20261107/report.json','utf8'));
 const rid=prior.run.run_id,pid=prior.project.project_id;
 const run=await (await page.request.get('http://127.0.0.1:18774/api/runs/'+rid)).json();
 if(run.status!=='stale'||run.metrics!==null)throw Error('Stale design loads leaked');
 if(await page.getByRole('region',{name:'分区设计显热负荷',exact:true}).count())throw Error('Stale sizing table visible');
 const evidence=await (await page.request.get('http://127.0.0.1:18774/api/projects/'+pid+'/evidence')).json();
 const originals=[];
 for(const item of evidence){
  const response=await page.request.get('http://127.0.0.1:18774/api/projects/'+pid+'/files/'+item.source_file);
  if(!response.ok())throw Error('Original missing');
  const hash=crypto.createHash('sha256').update(await response.body()).digest('hex');
  if(hash!==item.hash)throw Error('Original was altered');
  originals.push({name:item.name,hash,revision:item.revision,review:item.review_state});
 }
 const report=await (await page.request.get('http://127.0.0.1:18774/api/runs/'+rid+'/report.json')).json();
 if(report.run.metrics!==null)throw Error('Stale report contains load metrics');
 await fs.writeFile('output/playwright/designload-20261107/stale-verified.json',JSON.stringify({run,originals,report_metrics:report.run.metrics},null,2));
 await page.screenshot({path:'output/playwright/designload-20261107/stale.png'});
};
