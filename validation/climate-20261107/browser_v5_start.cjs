module.exports=async(page)=>{
 await page.reload();await page.getByRole('button',{name:'官方五区参考项目 · 非实测 示例',exact:true}).click();
 await page.getByRole('button',{name:'仿真',exact:true}).click();
 if(!await page.getByRole('button',{name:'运行仿真',exact:true}).isDisabled())throw Error('Invalid baseline enabled');
 await page.getByRole('combobox',{name:'方案',exact:true}).selectOption('R1');
 await page.getByRole('status').filter({hasText:/EPW line 9/}).waitFor();
 if(!await page.getByRole('button',{name:'运行仿真',exact:true}).isDisabled())throw Error('Invalid R1 weather enabled');
};
