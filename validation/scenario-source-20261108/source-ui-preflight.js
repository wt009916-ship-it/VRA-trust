async (page) => {
 const region=page.getByRole('region',{name:'材料方案比较',exact:true});
 await page.getByText('计量来源当前有效。每5秒复核；提交前会再次核验。',{exact:true}).waitFor();
 while(await region.locator('details:not([open]) > summary').count())await region.locator('details:not([open]) > summary').first().click();
 for(const input of await region.locator('input').all()){
  const type=await input.getAttribute('type'),name=await input.getAttribute('name');
  if(type==='checkbox')continue;
  let value=null;
  if(type==='date')value=name.endsWith('valid_from')?'2026-01-01':name.endsWith('valid_until')?'2027-12-31':'2026-11-08';
  else if(type==='number')value=name==='study_years'?'30':name.endsWith('factor_year')?'2026':name.endsWith('solid_fraction')?'1':name.endsWith('waste_ratio')?'0':name.endsWith('density')?'1000':name.endsWith('price')?'10':name.endsWith('factor')?'2':null;
  else if(name==='baseline_name')value='保留我的方案草稿';
  else if(name==='alternative_name')value='合成对照方案';
  else if(name==='region')value='US-CO';
  else if(name==='method')value='Synthetic GWP100 v1';
  else if(name==='functional_scope')value='Synthetic slabs only; equal geometry for UI recovery acceptance';
  else if(await input.getAttribute('required')!==null||name.endsWith('density_source'))value='Synthetic test declaration v1';
  if(value!==null)await input.fill(value);
 }
 if(!await region.locator('form').evaluate(f=>f.checkValidity()))throw Error('Fixture form is not valid');
 await page.getByRole('button',{name:'重新核验来源',exact:true}).click();
 await page.getByText('计量来源当前有效。每5秒复核；提交前会再次核验。',{exact:true}).waitFor();
 let entered;const gate=new Promise(resolve=>{entered=resolve;});
 await page.route('**/ifc-material-collections/materialset_e2fefd6dc1ef450ca03ce66ad4c144aa',route=>new Promise(resolve=>{
  page.__releasePreflight=async()=>{try{await route.continue();}finally{resolve();}};entered();
 }),{times:1});
 await page.getByRole('button',{name:'核验来源并生成两方案报告',exact:true}).click();
 await gate;
 if(page.__sourcePosts.length)throw Error('POST bypassed source preflight');
}
