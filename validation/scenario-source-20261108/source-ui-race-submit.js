async (page) => {
 const fs=await import('node:fs/promises');
 const crypto=await import('node:crypto');
 const path='C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/private-1e865fea9acc4775b9832b673b08b411/api/files/file_5e4ef90274d44583a944028b2ec465bf.ifc';
 const raw=await fs.readFile(path);
 if(crypto.createHash('sha256').update(raw).digest('hex')!=='e3f3a2a285c5d668b4b438dd11a3280df06ee1f6fda35f0187b78d999253c339')throw Error('Unexpected isolated copy');
 const current='计量来源当前有效。每5秒复核；提交前会再次核验。';
 const url='**/ifc-material-collections/materialset_e2fefd6dc1ef450ca03ce66ad4c144aa';
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();await page.getByText(current,{exact:true}).waitFor();
 let injected=false;
 await page.route(url,async route=>{await fs.writeFile(path,'Damaged isolated copy during preflight');injected=true;await route.continue();},{times:1});
 try{
  await page.getByRole('button',{name:'核验来源并生成两方案报告',exact:true}).click();
  await page.getByText('本次未提交；请先解决来源核验问题。',{exact:true}).waitFor();
  await page.getByText('计量来源已失效或发生变化，不能生成方案。草稿已保留，请重新读取原文件并建立新计量。',{exact:true}).waitFor();
  if(!injected||page.__sourcePosts.length)throw Error('Preflight race not blocked');
  await page.getByRole('heading',{name:'从多构件去重材料建立两套方案',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/source-race-blocked.png'});
 }finally{await fs.writeFile(path,raw);await page.unroute(url);}
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();await page.getByText(current,{exact:true}).waitFor();
 const responsePromise=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/collection-scenarios'));
 await page.getByRole('button',{name:'核验来源并生成两方案报告',exact:true}).click();
 const response=await responsePromise,record=await response.json();
 if(response.status()!==201||record.status!=='calculated')throw Error('Recovery calculation failed: '+JSON.stringify(record));
 await page.getByRole('link',{name:'打开两方案报告',exact:true}).waitFor();
 if(page.__sourcePosts.length!==1)throw Error('Expected one calculation POST');
 await fs.writeFile('C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/browser-calculated.json',JSON.stringify(record,null,2));
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();await page.getByText(current,{exact:true}).waitFor();
 await page.getByRole('link',{name:'打开两方案报告',exact:true}).waitFor();
 await fs.writeFile('C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/browser-race-receipt.json',JSON.stringify({injected,blocked_post_count:0,recovery_post_count:page.__sourcePosts.length,response_status:response.status(),calculation_status:record.status,report_link_survived_successful_refresh:true,source_restored:Buffer.compare(raw,await fs.readFile(path))===0},null,2));
}
