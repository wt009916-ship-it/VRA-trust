async (page) => {
 await page.getByText('计量来源已失效或发生变化，不能生成方案。草稿已保留，请重新读取原文件并建立新计量。',{exact:true}).waitFor({timeout:12000});
 if(!await page.getByRole('button',{name:'核验来源并生成两方案报告',exact:true}).isDisabled())throw Error('stale form enabled');
 if(await page.getByRole('textbox',{name:'方案一名称',exact:true}).inputValue()!=='保留我的方案草稿'||page.__sourcePosts.length)throw Error('draft lost or stale POST');
 await page.getByRole('heading',{name:'从多构件去重材料建立两套方案',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/stale.png'});
}
