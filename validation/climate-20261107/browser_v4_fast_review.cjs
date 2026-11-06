module.exports=async(page)=>{
 await page.getByRole('textbox',{name:'复核人',exact:true}).fill('隔离天气验收');
 await page.getByRole('textbox',{name:'复核依据 / 限制',exact:true}).fill('重复确认仍不代表有效；同时验收保存后立即打开导入窗口的异步刷新顺序。');
 await page.getByRole('button',{name:'保存复核记录',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await page.getByRole('button',{name:'导入资料',exact:true}).click();
 await page.getByLabel('文件',{exact:true}).waitFor();
 await page.getByRole('textbox',{name:'来源定位',exact:true}).fill('刷新后窗口保持可编辑；不提交新原件');
 await page.getByRole('textbox',{name:'来源与权威性',exact:true}).fill('隔离界面顺序验收');
 if(await page.getByRole('textbox',{name:'来源定位',exact:true}).inputValue()!=='刷新后窗口保持可编辑；不提交新原件')throw Error('Intake dialog disappeared');
};
