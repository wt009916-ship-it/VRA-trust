async(page)=>{
  const records=await page.evaluate(async()=>{
    const projects=await(await fetch('/api/projects')).json();if(projects.length!==1)throw Error('Unexpected project count');
    return await(await fetch('/api/projects/'+projects[0].project_id+'/cad-inspections')).json();
  });
  if(records.length!==3)throw Error('Expected three existing inspections');
  const rows=[];
  for(const record of records){
    const wall=record.result.ifc_geometry.objects.find(r=>r.type==='IfcWall');
    const select=page.locator('[data-ifc-record="'+record.cad_id+'"]');await select.selectOption(String(wall.id));
    const detail=page.locator('[data-ifc-detail="'+record.cad_id+'"]'),text=await detail.innerText();
    const normal=record.source.name==='single_through.ifc';
    if(normal&&(!text.includes('体积 22 m³')||wall.volume_m3!==22))throw Error('Valid opening mismatch');
    if(!normal&&(wall.volume_m3!==null||!text.includes('体积 — m³')))throw Error('Unknown quantity exposed');
    const exported=await page.evaluate(async({pid,id,fid})=>{
      const base='/api/projects/'+pid,record=await(await fetch(base+'/cad-inspections/'+id)).json();
      const raw=await(await fetch(base+'/files/'+fid)).arrayBuffer();
      const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join('');
      return {sha,status:record.status,geometry:record.result.ifc_geometry.objects.find(r=>r.type==='IfcWall')};
    },{pid:record.project_id,id:record.cad_id,fid:record.source.file_id});
    if(exported.sha!==record.source.hash||JSON.stringify(exported.geometry)!==JSON.stringify(wall))throw Error('Export mismatch');
    rows.push({file:record.source.name,cad_id:record.cad_id,pid:record.project_id,fid:record.source.file_id,sha:exported.sha,volume:wall.volume_m3,status:wall.status,display_matches:true});
  }
  await page.setViewportSize({width:390,height:844});
  const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
  const anonymous=await page.context().browser().newContext();
  const route='/api/projects/'+rows[0].pid;
  const denied=[];for(const p of ['/cad-inspections/'+rows[0].cad_id,'/files/'+rows[0].fid])denied.push((await anonymous.request.get('http://127.0.0.1:18774'+route+p)).status());
  await anonymous.close();
  return {cases:rows,width,anonymous_statuses:denied,headless:true};
}