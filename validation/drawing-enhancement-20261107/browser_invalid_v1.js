async (page) => {
  await page.getByRole('combobox',{name:'已保存尺度记录',exact:true}).selectOption('scale_df50d0e2e4fe425ebbfd8381208f4da7');
  const pending=page.waitForResponse(r=>r.url().endsWith('/measure')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'按当前有效尺度估算长度'}).click();const valid=await (await pending).json();
  await page.getByRole('button',{name:'导出本次条件长度 JSON'}).waitFor();
  const group=page.getByRole('group',{name:'待估算线段：原图像素坐标',exact:true});
  await group.getByRole('spinbutton',{name:'x',exact:true}).nth(1).fill('6000');
  const invalid=page.waitForResponse(r=>r.url().endsWith('/measure')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'按当前有效尺度估算长度'}).click();const r=await invalid;
  return {valid,status:r.status(),error:await r.json(),oldLengthStillVisible:await page.getByText('条件长度 3 m；仅传播尺度区间：3 ～ 3 m。',{exact:true}).count(),snapshot:await page.locator('body').ariaSnapshot()};
}
