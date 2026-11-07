async(page)=>{
 const cases=[
  {file:'validation/ifc-union-20261107/overlap.ifc',name:'overlap.ifc',expected:36,sum:48,deduction:12},
  {file:'validation/ifc-union-20261107/edge_touch.ifc',name:'edge_touch.ifc',expected:null},
  {file:'validation/ifc-net-20261107/overlapping_aggregate.ifc',name:'overlapping_aggregate.ifc',expected:24,sum:46,deduction:22}
 ],results=[];
 for(const item of cases){
  await page.getByLabel('选择 DXF / IFC（最大10 MiB）',{exact:true}).setInputFiles(item.file);
  const parsed=page.waitForResponse(r=>r.url().endsWith('/cad-inspections')&&r.request().method()==='POST',{timeout:90000});
  await page.getByRole('button',{name:'上传并读取',exact:true}).click();
  const response=await parsed,inspection=await response.json();if(response.status()!==201)throw Error(JSON.stringify(inspection));
  await page.getByLabel('来源 IFC 读取记录',{exact:true}).selectOption(inspection.cad_id);
  const ids=inspection.result.objects.filter(p=>p.type==='IfcWall').map(p=>String(p.id));
  if(ids.length!==2)throw Error('Expected two physical operands');
  await page.getByLabel('参与并集的构件（可多选）',{exact:true}).selectOption(ids);
  const saved=page.waitForResponse(r=>r.url().endsWith('/ifc-unions')&&r.request().method()==='POST',{timeout:90000});
  await page.getByRole('button',{name:'核算几何并集',exact:true}).click();
  const reply=await saved,record=await reply.json();if(reply.status()!==201)throw Error(JSON.stringify(record));
  const actual=record.result;
  if(item.expected===null){
   if(actual.union_volume_m3!==null||actual.reason!=='union_topology_unverified')throw Error('Unverified topology delivered');
  }else if(Math.abs(actual.union_volume_m3-item.expected)>1e-8||Math.abs(actual.sum_operand_volume_m3-item.sum)>1e-8||Math.abs(actual.overlap_deduction_m3-item.deduction)>1e-8)throw Error('Independent gold mismatch');
  const card=page.locator('.ifc-union-record').filter({hasText:item.name});
  await card.waitFor({state:'visible'});
  const text=await card.innerText();
  if(item.expected===null?!text.includes('数量 —'):!text.includes(item.expected+' m³'))throw Error('Rendered result mismatch');
  const original=await page.evaluate(async({pid,fid})=>{
   const r=await fetch('/api/projects/'+pid+'/files/'+fid);const raw=await r.arrayBuffer();
   return {status:r.status,sha:[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join('')};
  },{pid:record.project_id,fid:record.source.file_id});
  if(original.sha!==record.source.hash)throw Error('Original changed');
  results.push({file:item.name,pid:record.project_id,cad_id:record.cad_id,union_id:record.union_id,file_id:record.source.file_id,
   sha:original.sha,selected:record.product_ids,status:record.status,union:actual.union_volume_m3,sum:actual.sum_operand_volume_m3,deduction:actual.overlap_deduction_m3});
 }
 const last=results[2];
 const report=await page.request.get('/api/projects/'+last.pid+'/ifc-unions/'+last.union_id+'/report.html');
 if(report.status()!==200||!(await report.text()).includes('24.0'))throw Error('Report not matching native record');
 await page.setViewportSize({width:390,height:844});
 const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
 if(width.document>width.viewport)throw Error('Mobile overflow');
 await page.locator('.ifc-union-record').filter({hasText:'overlapping_aggregate.ifc'}).screenshot({path:'output/playwright/ifc-union-overlap.png'});
 const anonymous=await page.context().browser().newContext();
 const denial=await anonymous.request.get('http://127.0.0.1:18774/api/projects/'+last.pid+'/ifc-unions/'+last.union_id);
 await anonymous.close();if(denial.status()!==401)throw Error('Anonymous union leaked');
 return {cases:results,width,anonymous_status:denial.status(),report:true,headless:true};
}
