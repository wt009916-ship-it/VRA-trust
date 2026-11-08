async (page) => {
 const submit=page.getByRole('button',{name:'核验来源并生成两方案报告',exact:true,includeHidden:true});
 if(!await submit.isDisabled())throw Error('Hidden form is enabled');
 await page.getByRole('button',{name:'CAD / BIM',exact:true}).click();
 await page.getByText('计量来源当前有效。每5秒复核；提交前会再次核验。',{exact:true}).waitFor();
 if(await page.getByRole('textbox',{name:'方案一名称',exact:true}).inputValue()!=='保留我的方案草稿'||page.__sourcePosts.length)throw Error('draft lost or unexpected POST');
 await page.getByRole('heading',{name:'从多构件去重材料建立两套方案',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108/recovered.png'});
}
