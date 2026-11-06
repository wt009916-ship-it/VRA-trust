module.exports=async(page)=>{await page.reload();await page.getByRole('button',{name:'官方五区参考项目 · 非实测 示例',exact:true}).click();await page.getByText('4 类缺测或推导条件，需复核',{exact:true}).click();};
