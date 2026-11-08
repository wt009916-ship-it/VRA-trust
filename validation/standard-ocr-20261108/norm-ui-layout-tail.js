async(page)=>{
 const row=page.locator('#norm-clauses > fieldset').last();const text=await row.getByLabel('原文摘录',{exact:true}).inputValue();
 if(text!=='1.1.3 建筑环境应满足人体健康对声光热环境和空气质量的基\n本要求。')throw Error('Candidate line boundaries changed');
 await page.locator('#norm-preview-page').selectOption('6');if(await page.locator('#norm-ocr-output').innerText())throw Error('Old page candidates remained');
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-layout-20261108/page-changed.png'});
 return {selected_lines_preserved:true,page_change_cleared_candidates:true};
}
