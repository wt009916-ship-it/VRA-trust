async(page)=>{
 const pid='project_6708e64d6d8741d8979473e5695c5291';
 const input=page.locator('#command'),editor=page.locator('#task-editor'),summary=page.locator('#task-editor>summary');
 if(!await editor.evaluate(el=>el.open))await summary.click();
 const endpoint='http://127.0.0.1:18774/api/projects/'+pid+'/agent-tasks';
 const before=await (await page.request.get(endpoint)).json();
 const oversized='A'.repeat(4001);await input.fill(oversized);
 const rejected=page.waitForResponse(r=>r.url().endsWith('/agent/chat')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'执行项目操作',exact:true}).click();
 const response=await rejected;if(response.status()!==422)throw Error('Expected actual input validation rejection');
 await page.waitForFunction(()=>!document.querySelector('[aria-label="执行项目操作"]').disabled);
 const after=await (await page.request.get(endpoint)).json();
 if(after.length!==before.length)throw Error('Rejected request created a task');
 if(!await editor.evaluate(el=>el.open)||await input.inputValue()!==oversized)throw Error('Rejected submission discarded draft');
 await input.fill('保留的草稿：下一步核对材料方案。');
 const sizes=[];
 for(const [width,height] of [[390,500],[768,600]]){
  await page.setViewportSize({width,height});
  await summary.focus();await page.keyboard.press('Enter');
  const box=await page.evaluate(()=>{const t=document.querySelector('.task-thread').getBoundingClientRect(),e=document.querySelector('#task-editor').getBoundingClientRect();return {width:innerWidth,height:innerHeight,documentWidth:document.documentElement.scrollWidth,readingHeight:t.height,editorHeight:e.height,overlap:t.bottom>e.top+1};});
  if(box.documentWidth>width||box.overlap||box.readingHeight<200)throw Error('Short viewport failed '+JSON.stringify(box));
  sizes.push(box);await page.keyboard.press('Enter');
 }
 return {actual_http_status:422,no_task_created:true,rejected_draft_retained:true,short_viewports:sizes,scope:'UI admission rejection; accepted failed tasks are separate and not tested here.'};
}
