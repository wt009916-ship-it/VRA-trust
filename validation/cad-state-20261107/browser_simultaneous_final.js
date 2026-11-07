async(page)=>{
 await page.waitForFunction(()=>[...document.querySelectorAll('#cad-results [role="status"]')].filter(e=>e.textContent.includes('原件缺失或校验失败')).length===2,{},{timeout:15000});
 await page.locator('.ifc-union-record').getByRole('status').filter({hasText:'旧数量已撤下'}).waitFor({state:'visible',timeout:15000});
 if(await page.locator('#cad-results [data-ifc-detail],#cad-results table').count())throw Error('Stale details persisted');
 if(await page.getByRole('button',{name:'核算几何并集',exact:true}).isEnabled())throw Error('Stale source calculation enabled');
 await page.locator('#cad-results').screenshot({path:'output/playwright/cad-current-stale-final.png'});
 return {stale_records:2,details_removed:true,union_stale:true,union_disabled:true};
}
