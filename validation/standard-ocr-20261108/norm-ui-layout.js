async(page)=>{
 await page.getByRole('button',{name:'扫描规范原页复核验收 示例'}).click();await page.getByRole('button',{name:'规范资料',exact:true}).click();await page.getByText('登记 PDF 与条款摘录',{exact:true}).click();
 await page.getByLabel('原始规范 PDF（最大20 MiB）').setInputFiles('C:/Users/18483/AppData/Local/Temp/vra-official-standards-20261108/GB55016-2021.pdf');
 await page.locator('#norm-pdf-status').filter({hasText:'43页'}).waitFor({timeout:60000});await page.getByText('查看提取的文字层',{exact:true}).click();await page.locator('#norm-preview-page').selectOption('5');
 await page.getByRole('button',{name:'识别选定页（离线 OCR）'}).click();await page.getByRole('button',{name:'将所选行放入待修订摘录'}).waitFor({timeout:90000});
 const svg=page.getByRole('img',{name:'文字候选框'});let box=await svg.boundingBox();if(box.height<400)throw Error('Original page shrunk by icon style');
 await svg.scrollIntoViewIfNeeded();await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-layout-20261108/desktop.png'});
 await page.setViewportSize({width:390,height:844});box=await svg.boundingBox();if(box.height<300||box.width>390)throw Error('Mobile original page not readable');
 await svg.scrollIntoViewIfNeeded();await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-layout-20261108/mobile.png'});
 await page.locator('#norm-ocr-output input[value=text_9]').check();await page.locator('#norm-ocr-output input[value=text_10]').check();await page.getByRole('button',{name:'将所选行放入待修订摘录'}).click();
 const row=page.locator('#norm-clauses > fieldset').last();if(!(await row.getByLabel('原文摘录',{exact:true}).inputValue()).includes('基本要求'))throw Error('Selected lines missing');
 await page.locator('#norm-preview-page').selectOption('6');if(await page.locator('#norm-ocr-output').innerText())throw Error('Old page candidates remained');
}
