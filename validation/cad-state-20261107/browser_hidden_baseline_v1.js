async(page)=>{
 let requests=0;
 const listener=r=>{if(r.url().endsWith('/cad-current-states'))requests++;};
 await page.getByRole('button',{name:'热工计算',exact:true}).click();
 page.on('request',listener);
 try{
 await page.waitForResponse(r=>r.url().endsWith('/cad-current-states'),{timeout:12000});
 const hidden=await page.locator('#cad').evaluate(el=>el.hidden);
 if(!hidden||requests<1)throw Error('Baseline not reproduced');
 return {defect:'CADS-02',panel_hidden:hidden,background_state_requests:requests};
 }finally{page.off('request',listener);await page.getByRole('button',{name:'CAD / BIM',exact:true}).click();}
}
