async(page)=>{
 await page.locator('#norm-preview-page').selectOption('5');
 await page.getByRole('button',{name:'识别选定页（离线 OCR）'}).click();
 await page.getByRole('button',{name:'将所选行放入待修订摘录'}).waitFor({timeout:90000});
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-20261108/ui-first-ocr.png',fullPage:true});
}
