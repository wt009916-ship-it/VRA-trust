async (page) => {
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('textbox',{name:'项目名称',exact:true}).fill('图纸几何公开与合成验收');
  await dialog.getByRole('textbox',{name:'建筑用途',exact:true}).fill('公开与合成参考，非真实建筑');
  await dialog.getByRole('textbox',{name:'地点',exact:true}).fill('无现场项目');
  await dialog.getByRole('textbox',{name:'地区代码（如 CN-JX / US-CO）',exact:true}).fill('reference');
  await dialog.getByRole('spinbutton',{name:'总建筑面积 m²',exact:true}).fill('1');
  const [response]=await Promise.all([page.waitForResponse(r=>r.url().endsWith('/api/projects')&&r.request().method()==='POST'),dialog.getByRole('button',{name:'保存项目声明',exact:true}).click()]);
  await dialog.waitFor({state:'hidden'});
  return {project:await response.json(),snapshot:await page.locator('body').ariaSnapshot()};
}
