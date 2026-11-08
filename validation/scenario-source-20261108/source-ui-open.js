async (page) => {
 await page.getByRole('button',{name:'用去重材料比较两套方案',exact:true}).click();
 await page.getByText('计量来源当前有效。每5秒复核；提交前会再次核验。',{exact:true}).waitFor();
 await page.getByRole('textbox',{name:'方案一名称',exact:true}).fill('保留我的方案草稿');
}
