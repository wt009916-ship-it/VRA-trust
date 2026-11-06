const fs=require('node:fs/promises'),path=require('node:path');
module.exports=async(page)=>{
 const plan=JSON.parse(await fs.readFile('validation/climate-20261107/browser-prepared-v2.json','utf8'));
 const dir=path.join(plan.root,'downloads');await fs.mkdir(dir,{recursive:true});const files=[];
 for(const [name,file] of [['下载 PDF ↗','report.pdf'],['原始证据 ZIP ↗','artifacts.zip']]){
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name,exact:true}).click()]);
  const destination=path.join(dir,file);await download.saveAs(destination);
  if(await download.failure())throw Error('Download failed');files.push({name,file:destination});
 }
 await fs.writeFile('output/playwright/weather-20261107/final-downloads.json',JSON.stringify({files},null,2));
};
