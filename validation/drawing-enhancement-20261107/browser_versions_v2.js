async (page) => {
  const links={};for(const name of ['下载原图','下载规范化原图','下载处理版本'])links[name]=await page.getByRole('link',{name,exact:true}).getAttribute('href');
  const downloads=await page.evaluate(async links=>{
    const results={};for(const [name,url] of Object.entries(links)){const r=await fetch(url);const b=await r.arrayBuffer();results[name]={status:r.status,bytes:b.byteLength,sha256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b))).map(v=>v.toString(16).padStart(2,'0')).join('')};}return results;
  },links);
  if(downloads['下载原图'].sha256!=='24b96e41329f56cb6a1de5e6d5ffbbb3cef8ea8a828fd7a379276b4b9f7508eb')throw Error('original changed');
  const form=page.getByRole('group',{name:'处理版本（原件保留）',exact:true}).nth(1);
  await form.getByRole('combobox',{name:'纠偏方式',exact:true}).selectOption('manual');
  await form.getByRole('spinbutton').fill('-2');
  await form.getByRole('checkbox').check();
  const pending=page.waitForResponse(r=>r.url().endsWith('/drawings')&&r.request().method()==='POST',{timeout:90000});
  await page.getByRole('button',{name:'从保留的原件新建处理版本',exact:true}).click();const response=await pending,record=await response.json();
  await page.getByRole('link',{name:'查看过滤差异图',exact:true}).waitFor({timeout:15000});
  const count=await page.getByRole('combobox',{name:'历史识别记录',exact:true}).getByRole('option').count();
  if(count!==2||record.source.hash!==downloads['下载原图'].sha256||record.result.processing.transform.angle_degrees_clockwise!==-2)throw Error('version preservation failed');
  return {downloads,record,historyCount:count,snapshot:await page.locator('body').ariaSnapshot()};
}

