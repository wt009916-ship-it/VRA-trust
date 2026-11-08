async(page)=>{
 await page.reload();await page.getByRole('button',{name:'扫描规范原页复核验收 示例'}).click();await page.getByRole('button',{name:'规范资料',exact:true}).click();
 await page.locator('#norm-search [name=mode]').selectOption('batch');const targets=page.locator('#norm-targets > fieldset');
 for(const [i,code,clause]of [[0,'GB55015','1.0.2'],[1,'GB55016','1.1.3']]){
  await targets.nth(i).locator('[name=target_code]').fill(code);await targets.nth(i).locator('[name=target_edition]').fill('2021');await targets.nth(i).locator('[name=target_clause]').fill(clause);
 }
 await page.locator('#norm-search [name=as_of]').fill('2022-04-01');await page.getByRole('button',{name:'检索已复核条款'}).click();
 await page.locator('#norm-result').filter({hasText:'OCR辅助摘录 · 人工修订复核'}).waitFor({timeout:15000});
 const result=await page.locator('#norm-result').innerText();if(result.includes('文字层位置已核对'))throw Error('Misleading OCR provenance');
 await page.locator('#norm-result').scrollIntoViewIfNeeded();await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-20261108/ui-final-query.png'});
 await page.getByText('登记 PDF 与条款摘录',{exact:true}).click();
 await page.getByLabel('原始规范 PDF（最大20 MiB）').setInputFiles('C:/Users/18483/AppData/Local/Temp/vra-official-standards-20261108/GB55016-2021.pdf');
 await page.locator('#norm-pdf-status').filter({hasText:'43页'}).waitFor({timeout:60000});await page.getByText('查看提取的文字层',{exact:true}).click();
 await page.locator('#norm-preview-page').selectOption('5');await page.getByRole('button',{name:'识别选定页（离线 OCR）'}).click();
 await page.getByRole('button',{name:'将所选行放入待修订摘录'}).waitFor({timeout:90000});
 await page.locator('.norm-ocr-grid').scrollIntoViewIfNeeded();await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-20261108/ui-final-comparison.png'});
 await page.setViewportSize({width:390,height:844});await page.locator('.norm-ocr-lines').scrollIntoViewIfNeeded();
 const box=await page.locator('.norm-ocr-grid').boundingBox();if(box.width>390)throw Error('OCR comparison overflow');
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-20261108/ui-final-mobile.png'});
 await page.locator('#norm-preview-page').selectOption('6');if(await page.locator('#norm-ocr-output').innerText())throw Error('Previous page candidates retained');
 await page.setViewportSize({width:1440,height:1000});
}
