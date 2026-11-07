async (page) => {
  await page.getByRole('textbox',{name:'怎么称呼你',exact:true}).fill('图纸几何隔离验收');
  await page.getByRole('textbox',{name:'用户名',exact:true}).fill('drawing_geometry_ui');
  let password=await page.evaluate(()=>Array.from(crypto.getRandomValues(new Uint8Array(24)),x=>x.toString(16).padStart(2,'0')).join(''));
  await page.getByRole('textbox',{name:'密码 显示密码',exact:true}).fill(password);
  await page.getByRole('button',{name:'创建工作区',exact:true}).click();password=null;
  await page.getByRole('button',{name:'创建工作区',exact:true}).waitFor({state:'hidden'});
  console.log(await page.locator('body').ariaSnapshot());
}
