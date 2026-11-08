async (page) => {
  const panel=page.getByRole('region',{name:'多构件材料包络计量',exact:true});
  await panel.getByRole('heading',{name:'材料包络量未知',exact:true}).waitFor();
  if (await panel.getByRole('table').count()) throw Error('Stale material table remains');
  if (await panel.getByRole('button',{name:'用去重材料比较两套方案',exact:true}).count()) throw Error('Stale action remains');
  await panel.getByRole('heading',{name:'材料包络量未知',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-slab-layers-20261108/browser/withdrawn.png'});
}
