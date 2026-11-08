async (page) => {
 const pid='project_7774569f51234722868dc5b5cd2e2d03',rid='scenario_dfdce0627a2740a2888e285b7103ace7';
 const base='http://127.0.0.1:18774/api/projects/'+pid;
 const original=await page.getByRole('region',{name:'材料两方案核验',exact:true}).innerText();
 for(const expected of ['26.82 USD','21.44 USD','-5.38 USD','1697.60608048','1322.43669243','30 年'])
  if(!original.includes(expected))throw Error('Missing displayed source value '+expected);
 await page.getByRole('combobox',{name:'从已有记录选填'}).selectOption(rid);
 if(await page.getByRole('textbox',{name:'指定编号',exact:true}).inputValue()!==rid)throw Error('Wrong selected ID');
 const popupPromise=page.waitForEvent('popup');
 await page.getByRole('link',{name:'打开同源两方案报告'}).click();
 const popup=await popupPromise;await popup.waitForLoadState();
 const report=await popup.locator('body').innerText();
 for(const expected of ['26.82','21.44','-5.38','运输','运行'])if(!report.includes(expected))throw Error('Report missing '+expected);
 await popup.close();
 await page.getByRole('button',{name:'移除此目标'}).click();
 const widths=[];
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:900});
  widths.push(await page.evaluate(()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth})));
 }
 await page.screenshot({path:'output/playwright/scenario-mobile.png',fullPage:true});
 await page.setViewportSize({width:1440,height:1000});
 await page.screenshot({path:'output/playwright/scenario-desktop.png',fullPage:true});
 const auth=await (await page.request.get('http://127.0.0.1:18774/api/auth/me')).json();
 const project=await (await page.request.get(base)).json();
 const update=await page.request.put(base+'/building',{headers:{'X-CSRF-Token':auth.csrf_token},data:{expected_revision:project.revision,building:{...project.building,area_m2:928}}});
 if(update.status()!==200)throw Error('Revision mutation failed '+update.status());
 const current=await (await page.request.get(base+'/material-scenarios/'+rid)).json();
 if(current.status!=='stale'||current.result!==null)throw Error('Source withdrawal failed');
 const oldCardStillPresent=(await page.getByRole('region',{name:'材料两方案核验',exact:true}).innerText()).includes('26.82 USD');
 await page.getByRole('button',{name:'执行项目操作',exact:true}).click();
 await page.getByText('来源已变化，旧比较数值已撤下。',{exact:true}).waitFor({timeout:30000});
 const withdrawn=await page.getByRole('region',{name:'材料两方案核验',exact:true}).innerText();
 if(withdrawn.includes('26.82')||withdrawn.includes('1697.606'))throw Error('Stale card still shows values');
 await page.screenshot({path:'output/playwright/scenario-stale.png',fullPage:true});
 console.log(JSON.stringify({source_values_checked:true,real_selector_checked:true,same_source_report_checked:true,widths,
  backend_source_withdrawal:true,stale_values_withdrawn_after_explicit_recheck:true,old_card_present_until_recheck:oldCardStillPresent,
  automatic_live_withdrawal_tested:false,model_used_in_browser:false,prototype_18772_touched:false}));
}
