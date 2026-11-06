module.exports=async(page)=>{
 await page.getByRole('textbox',{name:'复核人',exact:true}).fill('隔离天气验收');
 await page.getByRole('textbox',{name:'复核依据 / 限制',exact:true}).fill('故意确认含第9行干球缺测的合成天气，测试人工确认不能绕过输入校验；并非工程认可。');
 await page.getByRole('button',{name:'保存复核记录',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await page.getByRole('navigation',{name:'项目工作视图',exact:true}).getByRole('button',{name:'工作台',exact:true}).click();
 await page.getByText(/EPW line 9.*dry_bulb/).waitFor();
};
