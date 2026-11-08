async(page)=>{
 await page.locator('#norm-result').filter({hasText:'已撤下'}).waitFor({timeout:15000});
 const text=await page.locator('#norm-result').innerText();if(text.includes('建筑环境应满足人体健康')||text.includes('新建、扩建和改建建筑'))throw Error('Stale citations remained visible');
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-20261108/ui-stale.png'});
}

