async(page)=>{
 await page.getByRole('navigation',{name:'项目工作视图'}).getByRole('button',{name:'工作台',exact:true}).click();
 await page.getByRole('button',{name:'规范资料',exact:true}).click();
 await page.getByRole('combobox',{name:'查询方式',exact:true}).selectOption('batch');
 const rows=page.getByRole('group',{name:'精确查询条款',exact:true});
 const result=page.locator('#norm-result');const submit=page.getByRole('button',{name:'检索已复核条款',exact:true});
 const receipt={checks:{},layouts:[],queries:[]};
 async function fill(i,code,clause){await rows.nth(i).getByRole('textbox',{name:'规范编号',exact:true}).fill(code);await rows.nth(i).getByRole('textbox',{name:'版本年份（可选）',exact:true}).fill('2024');await rows.nth(i).getByRole('textbox',{name:'条款号',exact:true}).fill(clause);}
 async function search(){const pending=page.waitForResponse(r=>r.url().endsWith('/standard-queries')&&r.request().method()==='POST');await submit.click();const reply=await pending;const record=await reply.json();if(reply.status()!==201)throw Error('Query rejected '+reply.status());receipt.queries.push(record);await page.waitForFunction(()=>!document.querySelector('#norm-search button[type=submit]').disabled);return record;}
 await fill(0,'TEST 101','1.2.3');await fill(1,'TEST 202','1.2.3');
 const first=await search();await result.getByRole('heading',{name:'全部指定条款已找到',exact:true}).waitFor();
 if(await result.locator('blockquote').count()!==2)throw Error('Expected two distinct same-number source quotes');
 if(!first.result.citations.some(c=>c.text.startsWith('SYNTHETIC_ALPHA:'))||!first.result.citations.some(c=>c.text.startsWith('SYNTHETIC_BETA:')))throw Error('Wrong quote pairing');
 receipt.checks.same_number_distinct_sources=true;
 await page.getByRole('button',{name:'添加查询条款',exact:true}).click();await fill(2,'TEST 202','2.3.4');
 const partial=await search();await result.getByRole('heading',{name:'部分条款未找到或存在冲突',exact:true}).waitFor();
 if(partial.result.targets[2].status!=='NOT_FOUND_IN_REVIEWED_INDEX'||partial.result.citations.length!==2)throw Error('Missing exact clause substituted across standards');
 receipt.checks.missing_target_preserved=true;
 for(const width of [1440,390]){await page.setViewportSize({width,height:900});await result.scrollIntoViewIfNeeded();
  const geometry=await page.evaluate(()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth,resultWidth:document.querySelector('#norm-result').getBoundingClientRect().width}));
  receipt.layouts.push(geometry);if(geometry.documentWidth>width)throw Error('Horizontal overflow');
  await page.screenshot({path:'output/playwright/standard-batch-'+width+'.png',fullPage:true});}
 // A separate authenticated request changes the source; the visible query must withdraw on its own poll.
 const base=new URL('/api/projects/'+partial.project_id,page.url()).href;
 const auth=await (await page.request.get(new URL('/api/auth/me',page.url()).href)).json();
 const standards=await (await page.request.get(base+'/standards')).json();
 const source=standards.find(s=>s.input.standard_code==='TEST 101');
 const revoked=await page.request.post(base+'/standards/'+source.standard_id+'/review',{headers:{'X-CSRF-Token':auth.csrf_token},data:{expected_revision:source.revision,state:'rejected',basis:'Separate-client synthetic withdrawal for visible query polling.'}});
 if(revoked.status()!==200)throw Error('Withdrawal failed');
 await result.getByText('来源已变化，旧引文已撤下，请重新检索。',{exact:true}).waitFor({timeout:12000});
 if(await result.locator('blockquote').count())throw Error('Stale quote remains visible');
 const historical=await (await page.request.get(base+'/standard-queries/'+partial.normquery_id)).json();
 if(historical.status!=='stale'||historical.result!==null)throw Error('Saved result revived stale source');
 receipt.checks.external_withdrawal_and_history=true;
 await page.screenshot({path:'output/playwright/standard-batch-stale.png',fullPage:true});
 const after=await revoked.json();const restored=await page.request.post(base+'/standards/'+source.standard_id+'/review',{headers:{'X-CSRF-Token':auth.csrf_token},data:{expected_revision:after.revision,state:'confirmed',basis:'Synthetic source re-reviewed after withdrawal; new query required.'}});
 if(restored.status()!==200)throw Error('Restore failed');
 const old=await (await page.request.get(base+'/standard-queries/'+partial.normquery_id)).json();if(old.result!==null)throw Error('Re-review resurrected old snapshot');
 const fresh=await search();await result.getByRole('heading',{name:'部分条款未找到或存在冲突',exact:true}).waitFor();
 receipt.checks.new_query_required_after_rereview=fresh.normquery_id!==partial.normquery_id;
 console.log(JSON.stringify(receipt));
}
