async (page) => {
 const current='计量来源当前有效。每5秒复核；提交前会再次核验。';
 const url='**/ifc-material-collections/materialset_e2fefd6dc1ef450ca03ce66ad4c144aa';
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();await page.getByText(current,{exact:true}).waitFor();
 let injected=false;
 await page.route(url,async route=>{const r=await page.request.post('http://127.0.0.1:18780/invalidate');if(!r.ok())throw Error('fault control failed');injected=true;await route.continue();},{times:1});
 try{
  await page.getByRole('button',{name:'核验来源并生成两方案报告',exact:true}).click();
  await page.getByText('本次未提交；请先解决来源核验问题。',{exact:true}).waitFor();
  await page.getByText('计量来源已失效或发生变化，不能生成方案。草稿已保留，请重新读取原文件并建立新计量。',{exact:true}).waitFor();
  if(!injected||page.__sourcePosts.length)throw Error('Preflight race not blocked');
  await page.getByRole('heading',{name:'从多构件去重材料建立两套方案',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/source-race-blocked.png'});
 }finally{await page.request.post('http://127.0.0.1:18780/restore');await page.unroute(url);}
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();await page.getByText(current,{exact:true}).waitFor();
 const responsePromise=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/collection-scenarios'));
 await page.getByRole('button',{name:'核验来源并生成两方案报告',exact:true}).click();
 const response=await responsePromise,record=await response.json();
 if(response.status()!==201||record.status!=='calculated')throw Error('Recovery calculation failed: '+JSON.stringify(record));
 await page.getByRole('link',{name:'打开两方案报告',exact:true}).waitFor();
 if(page.__sourcePosts.length!==1)throw Error('Expected one calculation POST');
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();await page.getByText(current,{exact:true}).waitFor();
 await page.getByRole('link',{name:'打开两方案报告',exact:true}).waitFor();
 const receipt=await page.request.post('http://127.0.0.1:18780/record',{data:{injected,blocked_post_count:0,recovery_post_count:page.__sourcePosts.length,response_status:response.status(),report_link_survived_successful_refresh:true,calculation:record}});
 if(!receipt.ok())throw Error('Receipt write failed');
}
