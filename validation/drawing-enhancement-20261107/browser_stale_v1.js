async (page) => {
  const select=page.getByRole('combobox',{name:'已保存尺度记录',exact:true});
  await select.selectOption('scale_321c1b46ef1b43e3aa6bd22ee373c9c6');
  await page.getByText('图页或算法依据已变化，旧尺度失效，不能继续估算。',{exact:true}).waitFor();
  await select.selectOption('scale_df50d0e2e4fe425ebbfd8381208f4da7');
  await page.getByText('图页或算法依据已变化，旧尺度失效，不能继续估算。',{exact:true}).waitFor();
  const disabled=await page.getByRole('button',{name:'按当前有效尺度估算长度',exact:true}).isDisabled();
  const scaleNumber=await page.getByText('条件尺度 0.06 m/px；声明区间 0.06 ～ 0.06 m/px。',{exact:true}).count();
  if(!disabled||scaleNumber)throw Error('stale scale visible');
  const exportUrl=await page.getByRole('link',{name:'导出当前尺度核验 JSON',exact:true}).getAttribute('href');
  const scale=await (await page.request.get(exportUrl)).json();if(scale.status!=='stale'||scale.result!==null)throw Error('stale API not null');
  const history=page.getByRole('combobox',{name:'历史识别记录',exact:true});
  await history.selectOption('drawing_aca07ba62d14444aad977bed7cf97f3b');
  await page.getByRole('link',{name:'查看过滤差异图',exact:true}).waitFor();
  await history.selectOption('drawing_e02566dfce64450eb0c4f41eb0186f08');
  await page.getByText('原件、预览或解析器已变化；旧识别和复核结果已失效，请新建记录。',{exact:true}).waitFor();
  const geometry=await page.getByText('对照原图并标定尺寸',{exact:true}).count();
  if(geometry)throw Error('stale drawing geometry rendered');
  return {disabled,scaleNumber,scale,geometry,snapshot:await page.locator('body').ariaSnapshot()};
}
