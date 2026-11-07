async(page)=>{
 const pid='project_81405c50ca824dc791416c30acc007de',cid='cad_d376dd0bcb0f4a49898be376c989347d';
 const card=page.locator('.ifc-union-record').filter({hasText:'overlap.ifc'});
 await card.getByText('来源或计算版本已变化，旧数量已撤下；数量 —。',{exact:true}).waitFor({state:'visible',timeout:15000});
 const legacy=page.locator('[data-ifc-detail="'+cid+'"]'),text=await legacy.innerText();
 const response=await page.request.get('http://127.0.0.1:18774/api/projects/'+pid+'/cad-inspections/'+cid),current=await response.json();
 if(current.status!=='stale'||current.result!==null)throw Error('Stale prerequisite missing');
 if(!text.includes('体积 24'))throw Error('Expected old CAD snapshot not observed');
 await legacy.screenshot({path:'output/playwright/ifc-cad-stale-baseline.png'});
 return {defect:'IFCU-06',cad_api_status:current.status,cad_api_result:current.result,legacy_cad_still_shows_24:true,
   new_union_quantities_removed:true,scope:'Isolated synthetic source only'};
}