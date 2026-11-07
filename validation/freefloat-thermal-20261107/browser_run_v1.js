async (page) => {
  return await page.evaluate(async () => {
    const projects = await (await fetch('/api/projects')).json();
    if (projects.length !== 1) throw Error('Expected one isolated reference');
    const pid = projects[0].project_id;
    const me = await (await fetch('/api/auth/me')).json();
    const headers = {'Content-Type':'application/json','X-CSRF-Token':me.csrf_token};
    const evidence = await (await fetch(`/api/projects/${pid}/evidence`)).json();
    for (const e of evidence) {
      const response = await fetch(`/api/projects/${pid}/evidence/${e.evidence_id}`,{method:'PATCH',headers,
        body:JSON.stringify({expected_revision:e.revision,review_state:'confirmed',responsible_person:'隔离参考验收',review_note:'公开参考模型与天气用于界面验收，不是实楼数据或工程适用性确认。'})});
      if (!response.ok) throw Error('Reference confirmation failed: '+response.status);
    }
    const response = await fetch('/api/runs',{method:'POST',headers,body:JSON.stringify({project_id:pid,scheme_id:'baseline'})});
    if (!response.ok) throw Error('Native run enqueue failed: '+response.status);
    const run = await response.json();
    return {project_id:pid,run_id:run.run_id,status:run.status,source:'Public reference; new native run; isolated database'};
  });
}
