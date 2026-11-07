const fs=require('node:fs/promises');
module.exports=async(page)=>{
 const out='output/playwright/designload-agent-20261107';
 const region=page.getByRole('region',{name:'当前原生运行结果',exact:true});
 await region.waitFor();
 const href=await region.getByRole('link',{name:'打开当前同源报告',exact:true}).getAttribute('href');
 if(!/^\/api\/runs\/run_[a-f0-9]{32}\/report\.html$/.test(href))throw Error('Unexpected report binding');
 const response=await page.request.get('http://127.0.0.1:18774'+href.replace('.html','.json'));
 if(!response.ok())throw Error('Current report read failed');
 const report=await response.json(),rows=region.locator('tbody tr'),source=report.run.metrics.zone_design_loads.rows;
 if(source.length!==10||await rows.count()!==10)throw Error('Wrong current load coverage');
 const checks=[];
 for(let i=0;i<10;i++){
  const cells=await rows.nth(i).locator('td').allTextContents();
  for(const [index,key] of [[1,'calculated_sensible_load_W'],[2,'user_adjusted_sensible_load_W']]){
   if(Math.abs(Number(cells[index].replaceAll(',',''))*1000-source[i][key])>.501)throw Error('Native/card numeric mismatch');
  }
  if(!cells[0].includes(source[i].zone_name)||!cells[3].includes(source[i].peak.date_time))throw Error('Wrong zone/peak');
  checks.push({row:i+1,zone:source[i].zone_name,mode:source[i].load_type,display:cells,source:source[i]});
 }
 const aid=(await page.locator('.agent-reply > small.mono').innerText()).trim();
 const task=await(await page.request.get(`http://127.0.0.1:18774/api/projects/${report.project.project_id}/agent/${aid}`)).json();
 if(task.answer.simulation_artifact.metrics.zone_design_loads.rows.length!==10||task.mode!=='local'||task.answer.sizing_read_progress.state!=='not_requested')throw Error('Controller read mislabeled as model read');
 if(task.llm_commentary_policy!=='audit_only')throw Error('Unverified prose policy missing');
 await fs.writeFile(out+'/agent-native-verified.json',JSON.stringify({report,task,checks},null,2));
 await region.scrollIntoViewIfNeeded();await page.screenshot({path:out+'/agent-native-desktop.png'});
 await page.setViewportSize({width:390,height:844});await region.scrollIntoViewIfNeeded();await page.screenshot({path:out+'/agent-native-mobile.png'});
 const dimensions=await region.evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth,page:document.documentElement.scrollWidth,viewport:innerWidth}));
 if(dimensions.page>390)throw Error('Page horizontal overflow');
 await fs.writeFile(out+'/agent-mobile-dimensions.json',JSON.stringify(dimensions));
 await page.setViewportSize({width:1440,height:1000});
};
