async(page)=>{
 for(const id of ['text_9','text_10'])await page.locator('#norm-ocr-output input[value="'+id+'"]').check();
 await page.getByRole('button',{name:'将所选行放入待修订摘录'}).click();
 const rows=page.locator('#norm-clauses > fieldset');await rows.first().getByRole('button',{name:'移除此条'}).click();const row=rows.first();
 await row.getByLabel('条款编号',{exact:true}).fill('1.1.3');await row.getByLabel('原书印刷页码').fill('1');await row.getByLabel('检索主题').fill('建筑环境基本要求');
 await row.getByLabel('原文摘录',{exact:true}).fill('建筑环境应满足人体健康对声光热环境和空气质量的基本要求。');
 await row.getByLabel('对照原页的修订与核验依据').fill('逐字对照原PDF第5页印刷第1页1.1.3条，去除候选中的条款号与换行，水印未纳入摘录。');
 const f=page.locator('#norm-add');
 for(const [k,v]of Object.entries({standard_code:'GB55016',title:'建筑环境通用规范',source_url:'https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_762459.html',scope:'历史版本建筑环境基本要求参考，仅核对第1.1.3条，不形成工程合规结论'}))await f.locator('[name='+k+']').fill(v);
 await f.getByRole('button',{name:'登记为待复核资料'}).click();await page.locator('#norm-result').filter({hasText:'资料已登记为待复核'}).waitFor({timeout:60000});
 await page.locator('#norm-review-choice').selectOption({label:'GB55016-2021 · 建筑环境通用规范 · 待复核'});
 await page.locator('#norm-review [name=basis]').fill('对照公开PDF第5页1.1.3条、原始候选与人工摘录，历史生效日及范围已核对，仅本轮参考验收。');
 await page.getByRole('button',{name:'保存复核记录'}).click();
 await page.locator('#norm-catalog article').filter({hasText:'GB55016-2021'}).filter({hasText:'人工已复核'}).waitFor();
 await page.locator('#norm-search [name=mode]').selectOption('batch');
 const targets=page.locator('#norm-targets > fieldset');
 for(const [i,code,clause]of [[0,'GB55015','1.0.2'],[1,'GB55016','1.1.3']]){
  await targets.nth(i).locator('[name=target_code]').fill(code);await targets.nth(i).locator('[name=target_edition]').fill('2021');await targets.nth(i).locator('[name=target_clause]').fill(clause);
 }
 await page.locator('#norm-search [name=as_of]').fill('2022-04-01');
 await page.getByRole('button',{name:'检索已复核条款'}).click();
 await page.locator('#norm-result').filter({hasText:'建筑环境应满足人体健康'}).waitFor({timeout:30000});
 if(!(await page.locator('#norm-result').innerText()).includes('新建、扩建和改建建筑'))throw Error('Missing first paired clause');
 await page.locator('#norm-result').scrollIntoViewIfNeeded();
 await page.screenshot({path:'C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-20261108/ui-paired-query.png'});
}
