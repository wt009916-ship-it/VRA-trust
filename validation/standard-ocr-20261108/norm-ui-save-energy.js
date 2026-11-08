async(page)=>{
 for(const id of ['text_7','text_8','text_9'])await page.locator('#norm-ocr-output input[value="'+id+'"]').check();
 await page.getByRole('button',{name:'将所选行放入待修订摘录'}).click();
 const rows=page.locator('#norm-clauses > fieldset');
 await rows.first().getByRole('button',{name:'移除此条'}).click();
 const row=rows.first();
 await row.getByLabel('条款编号',{exact:true}).fill('1.0.2');await row.getByLabel('原书印刷页码').fill('1');await row.getByLabel('检索主题').fill('建筑节能适用范围');
 await row.getByLabel('原文摘录',{exact:true}).fill('新建、扩建和改建建筑以及既有建筑节能改造工程的建筑节能与可再生能源建筑应用系统的设计、施工、验收及运行管理必须执行本规范。');
 await row.getByLabel('对照原页的修订与核验依据').fill('逐字对照原PDF第5页印刷第1页1.0.2条，去除候选中的条款号与换行。历史日期仅用于参考验收。');
 const f=page.locator('#norm-add');
 const values={standard_code:'GB55015',edition:'2021',title:'建筑节能与可再生能源利用通用规范',publisher:'住房和城乡建设部',source_url:'https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_762460.html',jurisdiction:'中华人民共和国',effective_from:'2022-04-01',status_checked_on:'2022-04-01',permission:'住建部公开原件仅本机参考验收，不转发原件不训练',scope:'历史版本适用范围参考，仅核对第1.0.2条，不形成工程合规结论',status_basis:'根据2021年官方公告所载2022年4月1日生效日期作历史参考，不证明2026现行性'};
 for(const [k,v]of Object.entries(values))await f.locator('[name='+k+']').fill(v);
 await f.getByRole('button',{name:'登记为待复核资料'}).click();
 await page.locator('#norm-result').filter({hasText:'资料已登记为待复核'}).waitFor({timeout:60000});
 await page.getByText('复核或撤回一份资料',{exact:true}).click();
 await page.locator('#norm-review-choice').selectOption({label:'GB55015-2021 · 建筑节能与可再生能源利用通用规范 · 待复核'});
 await page.locator('#norm-review [name=basis]').fill('对照公开PDF第5页1.0.2条、原始候选与人工摘录，历史生效日及范围已核对，仅本轮参考验收。');
 await page.getByRole('button',{name:'保存复核记录'}).click();
 await page.locator('#norm-catalog').filter({hasText:'人工已复核'}).waitFor({timeout:15000});
 await page.getByText('登记 PDF 与条款摘录',{exact:true}).click();
 await page.getByLabel('原始规范 PDF（最大20 MiB）').setInputFiles('C:/Users/18483/AppData/Local/Temp/vra-official-standards-20261108/GB55016-2021.pdf');
 await page.locator('#norm-pdf-status').filter({hasText:'43页'}).waitFor({timeout:60000});
 await page.locator('#norm-preview-page').selectOption('5');
 await page.getByRole('button',{name:'识别选定页（离线 OCR）'}).click();
 await page.getByRole('button',{name:'将所选行放入待修订摘录'}).waitFor({timeout:90000});
}

