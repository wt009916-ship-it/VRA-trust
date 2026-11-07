async(page)=>{
 const checks={},observations=[];
 const input=page.getByRole('textbox',{name:'项目操作',exact:true});
 const target=page.getByRole('region',{name:'本次任务结果',exact:true});
 const objective=page.getByRole('combobox',{name:'验收目标',exact:true});
 const editor=page.locator('#task-editor'),summary=page.locator('#task-editor>summary');
 const submit=page.getByRole('button',{name:'执行项目操作',exact:true});
 await page.setViewportSize({width:390,height:900});
 await objective.selectOption('inspect_material_scenarios');
 const question='核验公开墙的两套材料方案，查看当前成本与阶段碳量。';await input.fill(question);
 await page.screenshot({path:'output/playwright/task-input-mobile.png',fullPage:true});
 await submit.click();
 await page.getByText('材料采购金额 26.82 USD；声明边界碳总量 1697.60608048 kgCO₂e（整个评估期）。',{exact:true}).waitFor();
 if(await editor.evaluate(el=>el.open))throw Error('Accepted draft still consumes result space');
 if(await input.inputValue()!==question)throw Error('Submitted draft erased');
 checks.real_local_task_and_amount=true;checks.accepted_editor_collapsed=true;checks.draft_retained=true;
 checks.result_keyboard_focus=await target.evaluate(el=>el===document.activeElement);
 if(!checks.result_keyboard_focus)throw Error('Focus did not move to accessible results');
 for(const width of [390,1440]){
  await page.setViewportSize({width,height:900});
  const geometry=await page.evaluate(()=>{const t=document.querySelector('.task-thread').getBoundingClientRect(),e=document.querySelector('#task-editor').getBoundingClientRect();return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,threadHeight:t.height,threadBottom:t.bottom,editorTop:e.top,editorHeight:e.height};});
  if(geometry.documentWidth>width||geometry.editorHeight>90||geometry.threadBottom>geometry.editorTop+1||geometry.threadHeight<400)throw Error('Reading region obscured '+JSON.stringify(geometry));
  observations.push(geometry);
  await target.scrollIntoViewIfNeeded();
  await page.screenshot({path:`output/playwright/task-result-${width}.png`,fullPage:true});
 }
 await summary.focus();await page.keyboard.press('Enter');
 if(!await editor.evaluate(el=>el.open)||await input.inputValue()!==question)throw Error('Keyboard reopen lost draft');
 checks.keyboard_reopen_preserves_draft=true;
 // Delay delivery of the actual server response, never fabricate an API result.
 let release,seen;const held=new Promise(r=>release=r),arrived=new Promise(r=>seen=r);
 const route='**/api/projects/*/agent/chat';
 await page.route(route,async routed=>{const response=await routed.fetch();seen();await held;await routed.fulfill({response});},{times:1});
 await input.fill('读取同一材料方案，检查等待期间的编辑。');await submit.click();await arrived;
 const newDraft='下一条草稿：只核对运输阶段，并暂不提交。';await input.fill(newDraft);release();
 await page.waitForFunction(()=>!document.querySelector('[aria-label="执行项目操作"]').disabled);
 if(!await editor.evaluate(el=>el.open)||await input.inputValue()!==newDraft)throw Error('Late acceptance hid or erased newer draft');
 if(!await input.evaluate(el=>document.activeElement===el))throw Error('Late response stole draft focus');
 checks.real_response_delayed_new_draft_preserved=true;checks.no_focus_theft=true;
 await summary.focus();await page.keyboard.press('Space');
 if(await editor.evaluate(el=>el.open))throw Error('Keyboard collapse failed');
 await page.keyboard.press('Space');
 if(!await editor.evaluate(el=>el.open))throw Error('Keyboard expand failed');
 checks.keyboard_space_toggle=true;
 return {checks,observations,network_note:'One actual POST response delayed without changing status/body; all normal results from isolated server.',model_used:false,prototype_18772_touched:false};
}
