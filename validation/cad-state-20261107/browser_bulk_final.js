async(page)=>{
 const pid='project_6ba9b6188ad24056bc4f9093695471c5',fid='file_c7c83ee99a074ba7ba43c08fa28d0716',url='http://127.0.0.1:18774/api/projects/'+pid+'/cad-inspections';
 const auth=await(await page.request.get('http://127.0.0.1:18774/api/auth/me')).json(),created=[];
 for(let i=0;i<1;i++){
  const start=Date.now();
  const response=await page.request.post(url,{data:{file_id:fid},headers:{'X-CSRF-Token':auth.csrf_token},timeout:90000}),record=await response.json();
  if(response.status()!==201||record.status!=='parsed')throw Error('Actual repeat inspection failed: '+response.status());
  created.push({cad_id:record.cad_id,hash:record.hash,duration_ms:Date.now()-start});
 }
 return {actual_native_parses:created,credentials_saved:false};
}
