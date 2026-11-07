async(page)=>{
 const cid='cad_970df543018e4224b1debafcb76a5415';
 const card=page.locator('[data-cad-record="'+cid+'"]');
 await card.getByRole('status').filter({hasText:'原件缺失或校验失败'}).waitFor({state:'visible',timeout:15000});
 const delayed=page.__cadDelayed;delayed.release();
 await page.waitForResponse(r=>r.url().endsWith('/cad-current-states')&&r.status()===200,{timeout:12000});
 if(await card.locator('[data-ifc-detail],table').count()||(await card.innerText()).includes('24 m³'))throw Error('Late parsed response resurrected quantity');
 await page.unroute(delayed.pattern,delayed.handler);
 return {genuine_old_response:delayed.captured,new_stale_preserved:true,released:!!delayed.released,cancelled:!!delayed.cancelled};
}
