async (page) => {
  const evidence = await page.evaluate(async () => {
    const href=document.querySelector('.report-actions a[href$="/report.json"]').getAttribute('href');
    const report=await (await fetch(href)).json();
    return {rid:report.run.run_id,pid:report.run.project_id};
  });
  const other=await page.context().browser().newContext();
  let isolation;
  try {
    const base=new URL(page.url()).origin;
    const anonymous=await other.request.get(`${base}/api/runs/${evidence.rid}/report.json`);
    if(anonymous.status()!==401) throw new Error('Anonymous report access not blocked');
    const password=await page.evaluate(()=>crypto.randomUUID()+crypto.randomUUID());
    const account=await other.request.post(`${base}/api/auth/register`,{data:{username:'hourly_other_owner',display_name:'隔离权限验收',password}});
    if(account.status()!==200) throw new Error('Other test owner creation failed');
    const statuses=[];
    for(const suffix of ['result','report.json','report.html','report.pdf','artifacts']){
      const response=await other.request.get(`${base}/api/runs/${evidence.rid}/${suffix}`);
      statuses.push({suffix,status:response.status()});
      if(response.status()!==404) throw new Error('Cross-owner data exposed: '+suffix);
    }
    isolation={anonymous_status:anonymous.status(),other_owner:statuses};
  } finally { await other.close(); }
  const stale=await page.evaluate(async ({rid,pid})=>{
    const me=await (await fetch('/api/auth/me')).json();
    const rows=await (await fetch(`/api/projects/${pid}/evidence`)).json();
    const source=rows.find(e=>e.type==='idf' && e.scheme_id==='baseline');
    const response=await fetch(`/api/projects/${pid}/evidence/${source.evidence_id}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token},body:JSON.stringify({expected_revision:source.revision,review_state:'pending',responsible_person:'自动失效测试',review_note:'隔离验收撤回确认，保留原输入与原运行，验证逐时结果撤下。'})});
    if(!response.ok) throw new Error('Evidence revision failed: '+response.status);
    const r=await (await fetch(`/api/runs/${rid}/report.json`)).json();
    if(r.run.status!=='stale' || r.run.metrics!==null) throw new Error('Stale result not suppressed');
    return {status:r.run.status,metrics:r.run.metrics,source_hash:source.hash,source_evidence:source.evidence_id};
  },evidence);
  await page.locator('.hourly-thermal').waitFor({state:'detached',timeout:15000});
  return {...evidence,isolation,stale,old_curves_removed:true,credentials_saved:false};
}
