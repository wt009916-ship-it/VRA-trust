module.exports=async(page)=>{
 await page.getByRole('textbox',{name:'复核人',exact:true}).fill('隔离天气验收');
 await page.getByRole('combobox',{name:'处理',exact:true}).selectOption({label:'拒绝此证据版本'});
 await page.getByRole('textbox',{name:'复核依据 / 限制',exact:true}).fill('隔离验收：保留正常原件，换用有明确缺测的反例测试新准入与历史失效，不是实际工程替换。');
 await page.getByRole('button',{name:'保存复核记录',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await page.getByRole('button',{name:'导入资料',exact:true}).click();
};
