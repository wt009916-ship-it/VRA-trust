async (page) => {
  await page.getByRole('spinbutton',{name:'参考 B 已知长度',exact:true}).fill('4');
  const pending=page.waitForResponse(r=>r.url().endsWith('/scales')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存尺度核验记录'}).click();
  const row=await (await pending).json();
  await page.getByText('参考尺寸冲突，不能换算长度',{exact:true}).waitFor();
  const disabled=await page.getByRole('button',{name:'按当前有效尺度估算长度'}).isDisabled();
  const oldLength=await page.getByText('条件长度 3 m；仅传播尺度区间：3 ～ 3 m。',{exact:true}).count();
  if(!disabled||oldLength)throw Error('conflict did not clear/disable measure');
  return {row,disabled,oldLength,snapshot:await page.locator('body').ariaSnapshot()};
}
