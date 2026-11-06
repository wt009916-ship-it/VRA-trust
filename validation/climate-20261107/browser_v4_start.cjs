module.exports=async(page)=>{
 await page.reload();await page.getByRole('button',{name:'官方五区参考项目 · 非实测 示例',exact:true}).click();
 await page.getByRole('button',{name:'资料 5',exact:true}).click();
 await page.getByRole('button',{name:'dry_bulb_missing.epw',exact:true}).click();
 await page.getByRole('button',{name:'更改复核状态',exact:true}).click();
};
