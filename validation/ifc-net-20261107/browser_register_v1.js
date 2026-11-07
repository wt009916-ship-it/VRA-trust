async(page)=>{
  await page.getByRole('textbox',{name:'怎么称呼你',exact:true}).fill('IFC开洞隔离验收');
  await page.getByRole('textbox',{name:'用户名',exact:true}).fill('ifc_opening_ui');
  const password=await page.evaluate(()=>crypto.randomUUID()+crypto.randomUUID());
  await page.getByRole('textbox',{name:'密码 显示密码',exact:true}).fill(password);
  await page.getByRole('button',{name:'创建工作区',exact:true}).click();
  await page.getByRole('button',{name:'探索参考项目',exact:true}).waitFor({state:'visible'});
  await page.getByRole('button',{name:'探索参考项目',exact:true}).click();
  return {isolated_account_created:true,reference_project_created:true,credentials_saved:false};
}