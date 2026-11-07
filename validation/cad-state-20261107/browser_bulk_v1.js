async(page)=>{
 const pid='project_d6ecd4de55c84eb98621ecb9a3c0acf4',fid='file_1556f9e32db24f229dbf85e5968849b5',url='http://127.0.0.1:18774/api/projects/'+pid+'/cad-inspections';
 const auth=await(await page.request.get('http://127.0.0.1:18774/api/auth/me')).json(),created=[];
 for(let i=0;i<5;i++){
  const start=Date.now();
  const response=await page.request.post(url,{data:{file_id:fid},headers:{'X-CSRF-Token':auth.csrf_token},timeout:90000}),record=await response.json();
  if(response.status()!==201||record.status!=='parsed')throw Error('Actual repeat inspection failed: '+response.status());
  created.push({cad_id:record.cad_id,hash:record.hash,duration_ms:Date.now()-start});
 }
 return {actual_native_parses:created,credentials_saved:false};
}
