async (page) => {
  await page.getByRole('combobox',{name:'历史识别记录',exact:true}).selectOption('drawing_aca07ba62d14444aad977bed7cf97f3b');
  await page.getByText('对照原图并标定尺寸',{exact:true}).click();
  await page.setViewportSize({width:390,height:844});
  const img=page.getByRole('img',{name:'规范化原图；点击记录标定点，不能恢复不存在的尺寸',exact:true});
  await img.scrollIntoViewIfNeeded();const box=await img.boundingBox();
  await img.click({position:{x:box.width*.25,y:box.height*.25}});
  const group=page.getByRole('group',{name:'参考 A：原图像素坐标',exact:true});
  const picked=[Number(await group.getByRole('spinbutton',{name:'x',exact:true}).nth(0).inputValue()),Number(await group.getByRole('spinbutton',{name:'y',exact:true}).nth(0).inputValue())];
  if(Math.abs(picked[0]-260)>2||Math.abs(picked[1]-189)>2)throw Error('mobile pixel mapping mismatch');
  const dimensions=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth,
    overflowing:Array.from(document.querySelectorAll('input,select,textarea,button,img')).filter(el=>{const r=el.getBoundingClientRect();return r.width&&r.left>=0&&r.right>innerWidth+1}).map(el=>({tag:el.tagName,name:el.getAttribute('name'),id:el.id,right:el.getBoundingClientRect().right}))}));
  return {picked,expected:[260,189],dimensions,snapshot:await page.locator('body').ariaSnapshot(),visualScreenshot:'not verified: browser capture timeouts; desktop app approval timed out'};
}
