async (page) => {
 const popup=page.waitForEvent('popup');await page.getByRole('link',{name:'打开两方案报告',exact:true}).click();const report=await popup;await report.waitForLoadState('domcontentloaded');
 await report.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/report.png'});await report.close();
 const url='**/ifc-material-collections/materialset_e2fefd6dc1ef450ca03ce66ad4c144aa';
 let entered;const gate=new Promise(resolve=>{entered=resolve;});
 await page.route(url,async route=>{
  const response=await route.fetch();
  await new Promise(resolve=>{page.__releaseOldForm=async()=>{try{await route.fulfill({response});}catch{}resolve();};entered();});
 },{times:1});
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();await gate;
 await page.getByRole('button',{name:'收起方案表单',exact:true}).click();
 await page.getByRole('combobox',{name:'查看构件来源、数量与属性',exact:true}).selectOption('21');
 await page.getByRole('button',{name:'计算材料层包络',exact:true}).click();
 await page.getByRole('button',{name:'用此计量比较两套材料方案',exact:true}).waitFor({timeout:60000});
 await page.getByRole('button',{name:'用此计量比较两套材料方案',exact:true}).click();
 await page.getByRole('heading',{name:'从本构件建立两套材料方案',exact:true}).waitFor();
 await page.getByText('计量来源当前有效。每5秒复核；提交前会再次核验。',{exact:true}).waitFor();
 await page.getByRole('textbox',{name:'方案一名称',exact:true}).fill('单构件独立草稿');
 const result=await page.request.post('http://127.0.0.1:18780/invalidate');if(!result.ok())throw Error('fault failed');
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();
 await page.getByText('计量来源已失效或发生变化，不能生成方案。草稿已保留，请重新读取原文件并建立新计量。',{exact:true}).waitFor();
 await page.__releaseOldForm();await page.unroute(url);
 if(!await page.getByRole('button',{name:'核验来源并生成两方案报告',exact:true}).isDisabled())throw Error('Old response reopened new stale form');
 if(await page.getByRole('textbox',{name:'方案一名称',exact:true}).inputValue()!=='单构件独立草稿')throw Error('New form draft lost');
 await page.getByRole('heading',{name:'从本构件建立两套材料方案',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/single-stale-old-response.png'});
 await page.request.post('http://127.0.0.1:18780/restore');
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();
 await page.getByText('计量来源当前有效。每5秒复核；提交前会再次核验。',{exact:true}).waitFor();
 if(await page.getByRole('textbox',{name:'方案一名称',exact:true}).inputValue()!=='单构件独立草稿')throw Error('Single draft lost on recovery');
 await page.getByRole('button',{name:'收起方案表单',exact:true}).click();
}
