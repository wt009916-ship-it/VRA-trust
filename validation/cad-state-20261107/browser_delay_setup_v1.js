async(page)=>{
 const cid='cad_970df543018e4224b1debafcb76a5415';
 const pattern='**/cad-inspections/'+cid;
 let release,captured,first=true;
 const gate=new Promise(r=>release=r),ready=new Promise(r=>captured=r);
 const handler=async route=>{
  if(!first){await route.continue();return;}first=false;
  const response=await route.fetch(),body=await response.body(),record=JSON.parse(body.toString());
  page.__cadDelayed.captured={status:response.status(),record_status:record.status,hash:record.hash,quantity:record.result?.ifc_geometry?.objects?.[0]?.volume_m3};
  captured();await gate;
  try{await route.fulfill({response,body});page.__cadDelayed.released=true;}catch{page.__cadDelayed.cancelled=true;}
 };
 page.__cadDelayed={release,pattern,handler};
 await page.route(pattern,handler);
 await page.getByRole('button',{name:'立即核验状态',exact:true}).click();
 await ready;
 if(page.__cadDelayed.captured.record_status!=='parsed')throw Error('Delayed response was not genuine parsed record');
 return {holding_genuine_response:true,...page.__cadDelayed.captured};
}
