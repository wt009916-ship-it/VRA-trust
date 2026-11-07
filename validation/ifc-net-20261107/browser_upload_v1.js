async(page)=>{
  const rows=[];
  for(const name of ['host_fully_removed','duplicate_void_relation','single_through']){
    await page.getByLabel('选择 DXF / IFC（最大10 MiB）',{exact:true}).setInputFiles('validation/ifc-net-20261107/'+name+'.ifc');
    const pending=page.waitForResponse(r=>r.url().endsWith('/cad-inspections')&&r.request().method()==='POST',{timeout:90000});
    await page.getByRole('button',{name:'上传并读取',exact:true}).click();
    const response=await pending,record=await response.json();
    if(response.status()!==201)throw Error(JSON.stringify(record));
    const wall=record.result.ifc_geometry.objects.find(r=>r.type==='IfcWall');
    const select=page.locator('[data-ifc-record="'+record.cad_id+'"]');
    await select.waitFor({state:'attached'});await select.selectOption(String(wall.id));
    const detail=page.locator('[data-ifc-detail="'+record.cad_id+'"]');
    const text=await detail.innerText();
    if(name==='host_fully_removed'&&(!text.includes('体积保持未知')||wall.volume_m3!==null||text.includes('体积 24')))throw Error('Empty mesh not refused');
    if(name==='duplicate_void_relation'){
      await detail.getByText('洞口与宿主关系',{exact:true}).click();
      if(!(await detail.innerText()).includes('重复开洞关系')||wall.volume_m3!==null)throw Error('Ambiguous relation not refused');
    }
    if(name==='single_through'&&(!text.includes('22.000000')||wall.volume_m3!==22))throw Error('Normal opening mismatch');
    const hash=await page.evaluate(async({pid,fid})=>{
      const raw=await(await fetch('/api/projects/'+pid+'/files/'+fid)).arrayBuffer();
      return [...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join('');
    },{pid:record.project_id,fid:record.source.file_id});
    if(hash!==record.source.hash)throw Error('Original download mismatch');
    let screenshot;
    try{await detail.screenshot({path:'output/playwright/ifc-'+name+'.png',animations:'disabled',timeout:10000});screenshot='saved';}catch(e){screenshot=e.message.split('\n')[0];}
    rows.push({case:name,cad_id:record.cad_id,project_id:record.project_id,source_file:record.source.file_id,source_sha256:hash,volume:wall.volume_m3,status:wall.status,display:text,screenshot});
  }
  await page.setViewportSize({width:390,height:844});
  const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
  return {cases:rows,width,headless:true,credentials_saved:false};
}