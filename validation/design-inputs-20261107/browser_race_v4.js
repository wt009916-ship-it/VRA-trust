async(page)=>{
  await page.reload({waitUntil:'domcontentloaded'});
  await page.locator('button.sidebar-project[data-project="project_5b7f6c44f86d4be8a8a8f78dcb2355bf"]').focus();await page.keyboard.press('Enter');
  await page.getByRole('button',{name:'仿真',exact:true}).waitFor({state:'attached',timeout:15000});
  await page.getByRole('button',{name:'仿真',exact:true}).focus();await page.keyboard.press('Enter');
  await page.getByText('设计气象来源核对',{exact:true}).focus();await page.keyboard.press('Enter');
  await page.getByRole('combobox',{name:'设计气象来源',exact:true}).waitFor({state:'attached'});
  await page.waitForFunction(()=>document.querySelector('[data-source-choice]')?.options.length===2);
  const source='designsource_7f6a8b3cfaa94b938d831b843ac86529',model='evidence_fcfcd4bb21e34af6b4c66103d57bee01';
  let release,seen;const ready=new Promise(r=>seen=r),gate=new Promise(r=>release=r);
  await page.route('**/design-sources',async route=>{
    if(route.request().method()!=='GET')return route.continue();
    const response=await route.fetch();seen();await gate;await route.fulfill({response});
  });
  await page.getByRole('button',{name:'刷新当前版本',exact:true}).focus();await page.keyboard.press('Enter');await ready;
  await page.getByRole('combobox',{name:'设计气象来源',exact:true}).selectOption(source);
  await page.getByRole('combobox',{name:'已确认模型',exact:true}).selectOption(model);
  await page.getByRole('button',{name:'选择设计日对应关系',exact:true}).focus();await page.keyboard.press('Enter');
  await page.locator('[data-map]').first().waitFor({state:'attached'});
  release();await page.waitForFunction(()=>!document.querySelector('[data-refresh]').disabled);
  await page.unroute('**/design-sources');
  const preserved=await page.locator('[data-source-choice]').inputValue()===source&&await page.locator('[data-model-choice]').inputValue()===model;
  if(!preserved)throw Error('Late refresh replaced selection');
  await page.locator('[data-map="0"]').selectOption('0');await page.locator('[data-map="1"]').selectOption('6');
  const posted=page.waitForResponse(r=>r.url().endsWith('/design-checks')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'核对并保存记录',exact:true}).focus();await page.keyboard.press('Enter');
  const response=await posted,record=await response.json();if(response.status()!==201)throw Error(JSON.stringify(record));
  await page.getByRole('heading',{name:'声明字段一致',exact:true}).waitFor({state:'attached'});
  await page.setViewportSize({width:390,height:844});
  const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
  const paths=await page.evaluate(()=>[...document.scripts].map(s=>s.src).filter(Boolean));
  return {late_refresh_preserves_selection:preserved,check_id:record.designcheck_id,status:record.result.status,width,assets:paths};
}