async(page)=>{
 const root='http://127.0.0.1:18774',pid='project_d6ecd4de55c84eb98621ecb9a3c0acf4';
 const auth=await(await page.request.get(root+'/api/auth/me')).json();
 const historyResponse=await page.request.get(root+'/api/projects/'+pid+'/cad-inspections'),raw=await historyResponse.body(),records=JSON.parse(raw.toString());
 if(records.length!==21)throw Error('Expected 21 genuine records');
 const measurements=[];
 for(let i=0;i<10;i++){
  const start=Date.now(),response=await page.request.post(root+'/api/projects/'+pid+'/cad-current-states',{data:{cad_ids:records.slice(0,20).map(r=>r.cad_id)},headers:{'X-CSRF-Token':auth.csrf_token}});
  const bytes=await response.body(),body=JSON.parse(bytes.toString());
  if(response.status()!==200||body.states.length!==20||body.states.some(s=>s.status!=='parsed'||s.result))throw Error('Invalid state benchmark response');
  measurements.push({elapsed_ms:Date.now()-start,bytes:bytes.length});
  await page.waitForTimeout(200);
 }
 const values=measurements.map(r=>r.elapsed_ms).sort((a,b)=>a-b);
 return {scope:'10 sequential loopback authenticated samples, 20 records bound to one small synthetic original, not production load test',
 initial_full_history_bytes:raw.length,samples:measurements,median_ms:(values[4]+values[5])/2,max_ms:values.at(-1)};
}
