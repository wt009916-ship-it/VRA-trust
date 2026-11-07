async (page) => {
  await page.getByRole('combobox',{name:'已保存尺度记录',exact:true}).selectOption('scale_df50d0e2e4fe425ebbfd8381208f4da7');
  const group=page.getByRole('group',{name:'待估算线段：原图像素坐标',exact:true});
  const end=group.getByRole('spinbutton',{name:'x',exact:true}).nth(1);
  await group.getByRole('spinbutton',{name:'x',exact:true}).nth(0).fill('20');
  await group.getByRole('spinbutton',{name:'y',exact:true}).nth(0).fill('20');
  await end.fill('70');await group.getByRole('spinbutton',{name:'y',exact:true}).nth(1).fill('20');
  const button=page.getByRole('button',{name:'按当前有效尺度估算长度',exact:true});
  const wait=()=>page.waitForResponse(r=>r.url().endsWith('/measure')&&r.request().method()==='POST');
  const good=wait();await button.click();const valid=await (await good).json();
  await page.getByRole('button',{name:'导出本次条件长度 JSON'}).waitFor();
  await end.fill('6000');
  const old=()=>page.getByText('条件长度 3 m；仅传播尺度区间：3 ～ 3 m。',{exact:true}).count();
  const afterEdit=await old();const bad=wait();await button.click();const invalid=await bad;
  const afterFailure=await old();
  if(afterEdit||afterFailure||valid.length_m!==3||invalid.status()!==409)throw Error('invalid result guard failed');
  await end.fill('70');
  let release,ready,finished;
  const gate=new Promise(r=>release=r),received=new Promise(r=>ready=r),done=new Promise(r=>finished=r);
  const routeHandler=async route=>{const actual=await route.fetch();ready();await gate;await route.fulfill({response:actual});finished();};
  await page.route('**/scales/*/measure',routeHandler);
  const delayed=wait();await button.click();await received;
  await end.fill('90');release();await done;const delayedBody=await (await delayed).json();
  await page.unroute('**/scales/*/measure',routeHandler);
  await page.waitForFunction(()=>!document.querySelector('#drawing-length-form button').disabled);
  const afterLateResponse=await old();if(afterLateResponse||delayedBody.length_m!==3)throw Error('late response guard failed');
  return {valid,invalidStatus:invalid.status(),afterEdit,afterFailure,afterLateResponse,delayedBody,
          testNote:'Actual local API response delayed in browser transport; no fabricated API or calculation response.',snapshot:await page.locator('body').ariaSnapshot()};
}
