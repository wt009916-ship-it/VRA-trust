async (page) => {
  const dir = 'C:/Users/18483/AppData/Local/Temp/vra-slab-layers-20261108/browser/';
  await page.getByRole('heading', {name:'材料包络去重结果', exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:dir+'measured.png'});
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('link', {name:'材料计量与来源报告', exact:true}).click();
  const report = await popupPromise;
  await report.waitForLoadState('domcontentloaded');
  await report.screenshot({path:dir+'report.png'});
  await report.close();
  await page.getByRole('button', {name:'用去重材料比较两套方案', exact:true}).click();
  await page.getByRole('heading', {name:'从多构件去重材料建立两套方案', exact:true}).waitFor();
  await page.getByRole('heading', {name:'从多构件去重材料建立两套方案', exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:dir+'scenario-entry.png'});
}
