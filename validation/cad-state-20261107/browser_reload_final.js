async(page)=>{
 await page.getByRole('button',{name:'官方五区参考项目 · 非实测 示例',exact:true}).click();
 await page.getByRole('button',{name:'CAD / BIM',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('#cad-results [data-ifc-record]').length===2,{},{timeout:15000});
 return {actual_records:2};
}
