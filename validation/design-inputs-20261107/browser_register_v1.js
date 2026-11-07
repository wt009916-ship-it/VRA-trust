async (page) => {
  await page.getByRole('textbox',{name:'怎么称呼你',exact:true}).fill('设计气象隔离验收');
  await page.getByRole('textbox',{name:'用户名',exact:true}).fill('design_source_ui');
  const password=await page.evaluate(()=>crypto.randomUUID()+crypto.randomUUID());
  await page.getByRole('textbox',{name:'密码 显示密码',exact:true}).fill(password);
  await page.getByRole('button',{name:'创建工作区',exact:true}).focus(); await page.keyboard.press('Enter');
  await page.getByRole('button',{name:'探索参考项目',exact:true}).waitFor({state:'attached',timeout:15000});
  await page.getByRole('button',{name:'探索参考项目',exact:true}).focus(); await page.keyboard.press('Enter');
  await page.getByRole('button',{name:'仿真',exact:true}).waitFor({state:'attached',timeout:15000});
  await page.getByRole('button',{name:'仿真',exact:true}).focus(); await page.keyboard.press('Enter');
  return {isolated_account_registered:true,reference_project_created:true,credentials_saved:false};
}