async(page)=>{
 const cid='cad_970df543018e4224b1debafcb76a5415';
 const fresh=page.waitForResponse(r=>r.url().endsWith('/cad-inspections/'+cid)&&r.status()===200,{timeout:15000});
 await page.getByRole('button',{name:'立即核验状态',exact:true}).click();
 const body=await(await fresh).json();if(body.status!=='parsed')throw Error('No current detail');
 const card=page.locator('[data-cad-record="'+cid+'"]');
 await card.getByRole('combobox',{name:'查看构件来源、数量与属性',exact:true}).waitFor({state:'visible',timeout:10000});
 if(!(await card.innerText()).includes('体积 24 m³'))throw Error('Fresh detail not rendered');
 return {fresh_get:true,status:body.status,hash:body.hash,recovered_volume:24};
}
