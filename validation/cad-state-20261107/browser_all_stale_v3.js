async(page)=>{
 const cid='cad_970df543018e4224b1debafcb76a5415';
 await page.locator('[data-cad-record="'+cid+'"]').getByRole('status').filter({hasText:'原件缺失或校验失败'}).waitFor({state:'visible',timeout:15000});
 await page.locator('.ifc-union-record').getByRole('status').filter({hasText:'旧数量已撤下'}).waitFor({state:'visible',timeout:15000});
 if(await page.getByRole('button',{name:'核算几何并集',exact:true}).isEnabled())throw Error('Stale union enabled');
 await page.getByRole('button',{name:'上一页',exact:true}).click();
 await page.waitForFunction(()=>[...document.querySelectorAll('#cad-results [role="status"]')].filter(e=>e.textContent.includes('原件缺失或校验失败')).length===20,{},{timeout:15000});
 if(await page.locator('#cad-results [data-ifc-detail],#cad-results table').count())throw Error('Stale page retained measurements');
 await page.locator('#cad-results [data-cad-record]').first().screenshot({path:'output/playwright/cad-current-stale-final.png'});
 return {second_page_stale:true,first_page_stale_records:20,union_stale:true,union_disabled:true,all_visible_details_removed:true};
}
