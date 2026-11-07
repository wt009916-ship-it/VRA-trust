const fs=require('node:fs/promises'),path=require('node:path');
module.exports=async(page)=>{
 const region=page.getByRole('region',{name:'分区设计显热负荷',exact:true});
 await region.getByText('工况、倍率和来源',{exact:true}).click();
 const [report]=await Promise.all([page.waitForEvent('popup'),page.getByRole('link',{name:'完整 JSON ↗',exact:true}).click()]);
 await report.waitForLoadState();const data=JSON.parse(await report.locator('body').innerText());await report.close();
 const loads=data.run.metrics.zone_design_loads;
 if(data.run.status!=='succeeded'||loads.status!=='calculated_model_scenario'||loads.rows.length!==10)throw Error('Missing real sizing result');
 const rows=region.locator('tbody tr');if(await rows.count()!==10)throw Error('Wrong UI row count');
 const checks=[];
 for(let i=0;i<10;i++){
  const cells=await rows.nth(i).locator('td').allTextContents(),source=loads.rows[i];
  const calculated=Number(cells[1].replaceAll(',',''))*1000,adjusted=Number(cells[2].replaceAll(',',''))*1000;
  if(Math.abs(calculated-source.calculated_sensible_load_W)>.501||Math.abs(adjusted-source.user_adjusted_sensible_load_W)>.501)throw Error('Display units differ from report');
  if(!cells[0].includes(source.zone_name)||!cells[3].includes(source.peak.date_time))throw Error('Wrong zone/time binding');
  checks.push({zone:source.zone_name,mode:source.load_type,display_W:calculated,source_W:source.calculated_sensible_load_W});
 }
 const out='output/playwright/designload-20261107';
 await fs.writeFile(out+'/report.json',JSON.stringify(data,null,2));
 await fs.writeFile(out+'/numeric-ui-check.json',JSON.stringify(checks,null,2));
 const plan=JSON.parse(await fs.readFile('validation/designload-20261107/browser-prepared-v1.json','utf8'));
 const dir=path.join(plan.root,'downloads');await fs.mkdir(dir);const files=[];
 for(const [name,file] of [['下载 PDF ↗','report.pdf'],['原始证据 ZIP ↗','artifacts.zip']]){
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name,exact:true}).click()]);
  const target=path.join(dir,file);await download.saveAs(target);if(await download.failure())throw Error('Download failed');
  files.push({name,file:target});
 }
 await fs.writeFile(out+'/downloads.json',JSON.stringify(files,null,2));
 await page.setViewportSize({width:390,height:844});await region.scrollIntoViewIfNeeded();
 await page.screenshot({path:out+'/loads-mobile.png'});
 const dimensions=await region.evaluate(el=>({client:el.clientWidth,scroll:el.scrollWidth,page:document.documentElement.scrollWidth,viewport:innerWidth}));
 await fs.writeFile(out+'/mobile-dimensions.json',JSON.stringify(dimensions));
 await page.setViewportSize({width:1440,height:1000});
};
