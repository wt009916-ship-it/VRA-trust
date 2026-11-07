async(page)=>{
 await page.getByLabel('选择 DXF / IFC（最大10 MiB）',{exact:true}).setInputFiles('validation/cad-state-20261107/browser-original-overlap-v1.ifc');
 const parsed=page.waitForResponse(r=>r.url().endsWith('/cad-inspections')&&r.request().method()==='POST',{timeout:90000});
 await page.getByRole('button',{name:'上传并读取',exact:true}).click();
 const response=await parsed,record=await response.json();if(response.status()!==201)throw Error(JSON.stringify(record));
 await page.locator('[data-cad-record="'+record.cad_id+'"] [data-ifc-record]').waitFor({state:'visible',timeout:15000});
 return {project_id:record.project_id,cad_id:record.cad_id,file_id:record.source.file_id,source_hash:record.source.hash,hash:record.hash,
 objects:record.result.objects.map(r=>({id:r.id,type:r.type,name:r.name})),parsed:true};
}
