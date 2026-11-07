async (page) => {
  const img=page.getByRole('img',{name:'规范化原图；点击记录标定点，不能恢复不存在的尺寸',exact:true});
  await img.scrollIntoViewIfNeeded();
  const box=await img.boundingBox();
  await img.click({position:{x:box.width*20/1040,y:box.height*20/756}});
  const a=page.getByRole('group',{name:'参考 A：原图像素坐标',exact:true});
  const picked=[Number(await a.getByRole('spinbutton',{name:'x',exact:true}).nth(0).inputValue()),Number(await a.getByRole('spinbutton',{name:'y',exact:true}).nth(0).inputValue())];
  if(picked.some(x=>Math.abs(x-20)>1))throw Error('pixel click mismatch: '+picked);
  async function points(name,end){
    const g=page.getByRole('group',{name,exact:true});
    await g.getByRole('spinbutton',{name:'x',exact:true}).nth(0).fill('20');
    await g.getByRole('spinbutton',{name:'y',exact:true}).nth(0).fill('20');
    await g.getByRole('spinbutton',{name:'x',exact:true}).nth(1).fill(String(end));
    await g.getByRole('spinbutton',{name:'y',exact:true}).nth(1).fill('20');
  }
  await points('参考 A：原图像素坐标',120); await points('参考 B：原图像素坐标',70);
  await page.getByRole('spinbutton',{name:'参考 A 已知长度',exact:true}).fill('6000');
  await page.getByRole('spinbutton',{name:'参考 B 已知长度',exact:true}).fill('3');
  await page.getByRole('combobox',{name:'长度单位',exact:true}).nth(1).selectOption('m');
  await page.getByRole('textbox',{name:'标定依据和同页等比假设的理由'}).fill('独立合成验收：人为声明6000毫米每100像素和3米每50像素，仅验证换算，不代表真实图纸尺度。');
  await page.getByRole('checkbox',{name:'我声明本次只在同一图页等比平面假设下估算；尚未排除扫描畸变'}).check();
  const saved=page.waitForResponse(r=>r.url().endsWith('/scales')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'保存尺度核验记录'}).click();const scale=await (await saved).json();
  await points('待估算线段：原图像素坐标',70);
  const measured=page.waitForResponse(r=>r.url().endsWith('/measure')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'按当前有效尺度估算长度'}).click(); const measure=await (await measured).json();
  if(Math.abs(measure.length_m-3)>1e-12)throw Error('length mismatch');
  await page.getByRole('button',{name:'导出本次条件长度 JSON'}).waitFor();
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出本次条件长度 JSON'}).click();
  await (await download).saveAs('output/playwright/drawing-geometry-20261107/conditional-length-v1.json');
  await page.screenshot({path:'output/playwright/drawing-geometry-20261107/scale-desktop-v1.png'});
  return {picked,scale,measure,snapshot:await page.locator('body').ariaSnapshot()};
}
