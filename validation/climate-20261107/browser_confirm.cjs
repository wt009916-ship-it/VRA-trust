module.exports=async(page)=>{
 await page.getByRole('textbox',{name:'复核人',exact:true}).fill('隔离天气验收');
 await page.getByRole('textbox',{name:'复核依据 / 限制',exact:true}).fill('核对公开五区模型和Golden参考天气哈希，仅用于回归验证。雨况及降水缺测仍存在，不作为实测建筑或降雨工程依据。');
 await page.getByRole('button',{name:'保存复核记录',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await page.getByRole('button',{name:'仿真',exact:true}).click();
};
