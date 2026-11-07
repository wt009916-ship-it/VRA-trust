async(page)=>{
  const pid='project_5b7f6c44f86d4be8a8a8f78dcb2355bf',sid='designsource_7f6a8b3cfaa94b938d831b843ac86529',cid='designcheck_dd146af44c1f41e083ad737426a7e113';
  let mouse,screenshot;
  try{await page.locator('[data-result] details summary').first().click({timeout:3500});mouse='passed';}catch(e){mouse=e.message.split('\n')[0];}
  try{await page.screenshot({path:'output/playwright/design-source-390-v2.png',animations:'disabled',timeout:5000});screenshot='saved';}catch(e){screenshot=e.message.split('\n')[0];}
  const record=await page.evaluate(async({pid,sid,cid})=>{
    const base='/api/projects/'+pid,source=await(await fetch(base+'/design-sources/'+sid)).json();
    const me=await(await fetch('/api/auth/me')).json(),file=base+'/files/'+source.input.file_id;
    async function sha(){const raw=await(await fetch(file)).arrayBuffer();return [...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join('');}
    const before=await sha();
    const rejected=await fetch(base+'/design-sources/'+sid+'/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:source.revision,state:'pending',basis:'Missing CSRF negative local test'})});
    const response=await fetch(base+'/design-sources/'+sid+'/review',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token},body:JSON.stringify({expected_revision:source.revision,state:'pending',basis:'撤回本次隔离测试来源确认，用于验证正在打开的报告自动失效。'})});
    if(!response.ok)throw Error('withdraw '+response.status);
    const current=await(await fetch(base+'/design-checks/'+cid)).json(),html=await(await fetch(base+'/design-checks/'+cid+'/report.html')).text();
    return {missing_csrf_status:rejected.status,withdraw_status:response.status,current_status:current.status,result_is_null:current.result===null,
      stale_reasons:current.stale_reasons,report_withdrawn:html.includes('当前核对结果不可用'),original_sha_before:before,original_sha_after:await sha(),file_path:file};
  },{pid,sid,cid});
  await page.getByText('当前核对结果不可用，请重新检查来源和模型版本。',{exact:true}).waitFor({state:'attached',timeout:20000});
  const paths=['/api/projects/'+pid+'/design-sources/'+sid,'/api/projects/'+pid+'/design-checks/'+cid,'/api/projects/'+pid+'/design-checks/'+cid+'/report.html',record.file_path];
  const other=await page.context().browser().newContext();
  const anonymous=[];for(const path of paths)anonymous.push((await other.request.get('http://127.0.0.1:18774'+path)).status());
  const password=await page.evaluate(()=>crypto.randomUUID()+crypto.randomUUID());
  const registration=await other.request.post('http://127.0.0.1:18774/api/auth/register',{data:{username:'design_other_ui',display_name:'隔离跨账号验收',password}});
  if(registration.status()!==200)throw Error('Other test registration failed');
  const cross_owner=[];for(const path of paths)cross_owner.push((await other.request.get('http://127.0.0.1:18774'+path)).status());
  await other.close();
  return {...record,auto_poll_removed_result:true,mouse,screenshot,anonymous,cross_owner,credentials_saved:false};
}