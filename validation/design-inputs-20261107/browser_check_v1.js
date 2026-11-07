async(page)=>{
  const project='project_5b7f6c44f86d4be8a8a8f78dcb2355bf',source='designsource_7f6a8b3cfaa94b938d831b843ac86529',model='evidence_fcfcd4bb21e34af6b4c66103d57bee01';
  const before=await page.locator('[data-source-choice]').inputValue();
  await page.getByRole('combobox',{name:'设计气象来源',exact:true}).selectOption(source);
  await page.getByRole('combobox',{name:'已确认模型',exact:true}).selectOption(model);
  await page.getByRole('button',{name:'选择设计日对应关系',exact:true}).focus();await page.keyboard.press('Enter');
  await page.locator('[data-map]').first().waitFor({state:'attached'});
  await page.locator('[data-map="0"]').selectOption('0');await page.locator('[data-map="1"]').selectOption('6');
  const promise=page.waitForResponse(r=>r.url().endsWith('/design-checks')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'核对并保存记录',exact:true}).focus();await page.keyboard.press('Enter');
  const response=await promise, record=await response.json();
  if(response.status()!==201)throw Error(JSON.stringify(record));
  await page.getByRole('heading',{name:'声明字段一致',exact:true}).waitFor({state:'attached'});
  const exported=await page.evaluate(async({project,id})=>{
    const base='/api/projects/'+project+'/design-checks/'+id;
    const json=await (await fetch(base)).json(),report=await (await fetch(base+'/report.html')).text();
    return {status:json.status,result:json.result,report_has_status:report.includes('matching_declared_fields'),report_has_hash:report.includes(json.source_snapshot.file_snapshot.hash)};
  },{project,id:record.designcheck_id});
  await page.locator('[data-result] details').first().locator('summary').focus();await page.keyboard.press('Enter');
  const tableRows=await page.locator('[data-result] tbody tr').count();
  await page.locator('[data-map="1"]').selectOption('7');
  const cleared=await page.locator('[data-result]').innerText();
  return {before_selected_source:before,check_id:record.designcheck_id,post_status:response.status(),table_rows:tableRows,mapping_change_cleared:cleared==='',...exported};
}