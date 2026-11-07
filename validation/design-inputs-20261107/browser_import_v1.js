async(page)=>{
  await page.getByLabel('DDY 原件',{exact:true}).setInputFiles('F:/EnergyPlusV9-0-1/WeatherData/USA_CO_Golden-NREL.724666_TMY3.ddy');
  await page.getByRole('combobox',{name:'原件编码',exact:true}).selectOption('cp1252');
  for(const [name,value] of [['资料名称','Golden公开设计条件'],['声明发布方','文件注释声明 ASHRAE，随 EnergyPlus 分发，未独立认证'],
      ['资料版本 / 年代','DDY注释2009 / EnergyPlus9.0.1包'],['来源网址','https://github.com/NatLabRockies/EnergyPlus/releases/tag/v9.0.1'],
      ['取得日期','2026-11-07'],['授权使用说明','本机已安装公开参考资料，仅用于来源一致性验收'],
      ['适用范围与限制','仅核对公开参考模型声明参数，不能用于当前规范合规或实楼设计认证']]) {
    await page.getByLabel(name,{exact:true}).fill(value);
  }
  let response=page.waitForResponse(r=>r.url().endsWith('/design-sources')&&r.request().method()==='POST',{timeout:20000});
  await page.getByRole('button',{name:'保留原件并登记',exact:true}).focus();await page.keyboard.press('Enter');
  const createdResponse=await response,created=await createdResponse.json();
  if(createdResponse.status()!==201)throw Error(JSON.stringify(created));
  await page.getByRole('combobox',{name:'设计气象来源',exact:true}).selectOption(created.designsource_id);
  await page.getByText('人工复核 / 撤回来源',{exact:true}).focus();await page.keyboard.press('Enter');
  await page.getByLabel('复核依据',{exact:true}).fill('核对原件、注释版本及18个设计日；仅作为公开参考参数一致性测试，不认定来源权威或项目适用性。');
  response=page.waitForResponse(r=>r.url().endsWith('/review')&&r.request().method()==='POST',{timeout:10000});
  await page.getByRole('button',{name:'确认已检查原件及声明',exact:true}).focus();await page.keyboard.press('Enter');
  const reviewedResponse=await response,reviewed=await reviewedResponse.json();
  if(reviewedResponse.status()!==200)throw Error(JSON.stringify(reviewed));
  await page.getByRole('combobox',{name:'设计气象来源',exact:true}).selectOption(created.designsource_id);
  await page.getByRole('combobox',{name:'已确认模型',exact:true}).selectOption('evidence_fcfcd4bb21e34af6b4c66103d57bee01');
  await page.getByRole('button',{name:'选择设计日对应关系',exact:true}).focus();await page.keyboard.press('Enter');
  await page.locator('[data-map]').first().waitFor({state:'attached',timeout:10000});
  return {source_id:created.designsource_id,source_file_sha256:created.file_snapshot.hash,source_days:created.catalog.days.length,
    review_state:reviewed.review.state,review_revision:reviewed.revision,
    mappings:await page.locator('[data-map]').count(),credentials_saved:false};
}