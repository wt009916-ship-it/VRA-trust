async (page)=>{
 await page.getByRole('button',{name:'规范资料',exact:true}).click();
 await page.getByText('登记 PDF 与条款摘录',{exact:true}).click();
 await page.getByLabel('原始规范 PDF（最大20 MiB）').setInputFiles('C:/Users/18483/AppData/Local/Temp/vra-official-standards-20261108/GB55015-2021.pdf');
 await page.locator('#norm-pdf-status').filter({hasText:'82页'}).waitFor({timeout:60000});
 await page.getByText('查看提取的文字层',{exact:true}).click();
 await page.getByLabel('PDF页码',{exact:true}).selectOption('5');
 await page.getByRole('button',{name:'识别选定页（离线 OCR）'}).click();
 await page.getByRole('button',{name:'将所选行放入待修订摘录'}).waitFor({timeout:90000});
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-20261108/ui-first-ocr.png',fullPage:true});
}
