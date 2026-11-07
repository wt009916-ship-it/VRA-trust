async(page)=>{
  const ev=await page.evaluate(async()=>{
    const p=await (await fetch('/api/projects')).json();
    if(p.length!==1)throw Error('Unexpected isolated project count');
    const pid=p[0].project_id,me=await (await fetch('/api/auth/me')).json();
    const rows=await (await fetch('/api/projects/'+pid+'/evidence')).json();
    const model=rows.find(r=>r.type==='idf'&&r.scheme_id==='baseline');
    const response=await fetch('/api/projects/'+pid+'/evidence/'+model.evidence_id,{method:'PATCH',
      headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token},
      body:JSON.stringify({expected_revision:model.revision,review_state:'confirmed',responsible_person:'隔离参考测试',
        review_note:'核对公开参考文件，仅用于来源一致性测试，不是实楼适用性确认。'})});
    if(!response.ok)throw Error('Reference review failed');
    return {pid,model_evidence_id:model.evidence_id};
  });
  await page.getByText('设计气象来源核对',{exact:true}).focus();await page.keyboard.press('Enter');
  await page.getByText('登记设计气象来源',{exact:true}).waitFor({state:'attached',timeout:10000});
  await page.getByText('登记设计气象来源',{exact:true}).focus();await page.keyboard.press('Enter');
  return ev;
}