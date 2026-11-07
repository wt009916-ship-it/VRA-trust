async(page)=>{
 const records=await page.evaluate(async()=>{
  const projects=await(await fetch('/api/projects')).json();if(projects.length!==1)throw Error('Unexpected projects');
  return await(await fetch('/api/projects/'+projects[0].project_id+'/ifc-unions')).json();
 });
 if(records.length!==3)throw Error('Expected exactly three existing union records');
 const expected={'overlap.ifc':[48,36,12],'edge_touch.ifc':[null,null,null],'overlapping_aggregate.ifc':[46,24,22]};
 const rows=[];
 for(const r of records){
  const gold=expected[r.source.name];if(!gold)throw Error('Unexpected file');
  const card=page.locator('.ifc-union-record').filter({hasText:r.source.name});await card.waitFor({state:'visible'});
  const text=await card.innerText();
  for(const [i,key] of ['sum_operand_volume_m3','union_volume_m3','overlap_deduction_m3'].entries()){
   const actual=r.result[key];
   if(gold[i]===null?actual!==null:Math.abs(actual-gold[i])>1e-8)throw Error('Independent numeric mismatch');
  }
  if(gold[1]===null?!text.includes('数量 —'):!text.includes(gold[1]+' m³'))throw Error('Display mismatch');
  const url='http://127.0.0.1:18774/api/projects/'+r.project_id+'/ifc-unions/'+r.union_id;
  const report=await page.request.get(url+'/report.html');
  if(report.status()!==200||!(await report.text()).includes(r.source.hash))throw Error('Report source mismatch');
  const download=await page.evaluate(async({pid,fid})=>{
   const raw=await(await fetch('/api/projects/'+pid+'/files/'+fid)).arrayBuffer();
   return [...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join('');
  },{pid:r.project_id,fid:r.source.file_id});
  if(download!==r.source.hash)throw Error('Original hash mismatch');
  rows.push({name:r.source.name,pid:r.project_id,cad_id:r.cad_id,union_id:r.union_id,file_id:r.source.file_id,sha:download,
   selected:r.product_ids,sum:r.result.sum_operand_volume_m3,union:r.result.union_volume_m3,deduction:r.result.overlap_deduction_m3,status:r.status});
 }
 await page.setViewportSize({width:390,height:844});
 const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
 if(width.document>width.viewport)throw Error('Mobile overflow');
 await page.locator('.ifc-union-record').filter({hasText:'overlapping_aggregate.ifc'}).screenshot({path:'output/playwright/ifc-union-overlap.png'});
 const anonymous=await page.context().browser().newContext(),r=records[0];
 const response=await anonymous.request.get('http://127.0.0.1:18774/api/projects/'+r.project_id+'/ifc-unions/'+r.union_id+'/report.html');
 await anonymous.close();if(response.status()!==401)throw Error('Anonymous report leaked');
 return {cases:rows,width,anonymous_report:response.status(),reports_and_originals_verified:true};
}
