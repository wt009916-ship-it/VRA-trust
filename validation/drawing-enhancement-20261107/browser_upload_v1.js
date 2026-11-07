async (page) => {
  await page.getByRole('button', {name:'图纸文件（PNG / JPEG / PDF，最大10 MiB）'}).setInputFiles('fixtures/drawing_geometry/turn_3_25.png');
  await page.getByRole('combobox', {name:'纠偏方式'}).selectOption('auto');
  const response = page.waitForResponse(r=>r.url().endsWith('/drawings') && r.request().method()==='POST',{timeout:60000});
  await page.getByRole('button', {name:'保留原件并生成处理与文字候选'}).click();
  const r=await response;
  await page.getByText('对照原图并标定尺寸',{exact:true}).waitFor({timeout:15000});
  return {status:r.status(),record:await r.json(),snapshot:await page.locator('body').ariaSnapshot()};
}
