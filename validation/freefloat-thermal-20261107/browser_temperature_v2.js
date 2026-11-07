async (page) => {
  const browser = await page.context().browser().browserType().launch({channel:'chrome',headless:true});
  const context = await browser.newContext({viewport:{width:1403,height:1157}});
  // Keep this isolated-test session in memory; no credential or cookie file.
  await context.addCookies(await page.context().cookies());
  const view = await context.newPage();
  const errors=[]; view.on('pageerror',e=>errors.push(String(e)));
  try {
    await view.goto('http://127.0.0.1:18774/');
    const animationFrame = await view.evaluate(() => Promise.race([new Promise(r=>requestAnimationFrame(()=>r(true))),new Promise(r=>setTimeout(()=>r(false),1000))]));
    await view.getByRole('button',{name:'官方五区参考项目 · 非实测 示例',exact:true}).focus(); await view.keyboard.press('Enter');
    await view.getByRole('button',{name:'仿真',exact:true}).focus(); await view.keyboard.press('Enter');
    await view.getByRole('button',{name:'查看依据',exact:true}).focus(); await view.keyboard.press('Enter');
    await view.getByRole('combobox',{name:'室温曲线分区',exact:true}).waitFor({timeout:10000});
    const report = await view.evaluate(async () => {
      const href=document.querySelector('.report-actions a[href$="/report.json"]').getAttribute('href');
      return await (await fetch(href)).json();
    });
    const receipt=report.run.metrics.hourly_thermal;
    if(receipt.status!=='calculated_model_scenario' || receipt.summary.hour_count!==8760 || receipt.summary.zones.length!==6) throw Error('Unexpected native coverage');
    const checks=[];
    for(let index=0;index<receipt.summary.zones.length;index++) {
      await view.getByRole('combobox',{name:'室温曲线分区',exact:true}).selectOption(String(index));
      const shown = await view.locator('[data-temperature-profiles]').evaluate(element => [...element.querySelectorAll('figure')].map(f=>({
        title:f.querySelector('figcaption').textContent, rows:[...f.querySelectorAll('tbody tr')].map(r=>r.lastElementChild.textContent),
        points:f.querySelector('polyline').getAttribute('points').trim().split(/\s+/).length})));
      const zone=receipt.summary.zones[index].zone_name;
      if(shown.length!==2) throw Error('Expected two peak-day temperature profiles');
      shown.forEach((s,i)=>{
        const expected=receipt.summary.peak_day_profiles[i].zones[zone].temperature_C.map(v=>v.toLocaleString('zh-CN',{maximumFractionDigits:2}));
        if(!s.title.includes(zone)||s.points!==24||JSON.stringify(s.rows)!==JSON.stringify(expected)) throw Error('Temperature UI/API mismatch '+zone);
      });
      checks.push({zone,profiles:2,points_each:24,all_values_match_api:true});
    }
    await view.locator('.hourly-temperature-panel').evaluate(e=>e.scrollIntoView());
    let screenshot;
    try {
      const path='C:/Users/18483/AppData/Local/Temp/vra-hourly-candidate-56c1034357dc4f9ca39ae26022963012/output/playwright/temperature-desktop.png';
      await view.locator('.hourly-temperature-panel').screenshot({path,timeout:10000}); screenshot={path,captured:true};
    } catch(e) { screenshot={captured:false,error:String(e)}; }
    await view.setViewportSize({width:390,height:844});
    const mobile=await view.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,
      chartWidths:[...document.querySelectorAll('.hourly-temperature svg')].map(e=>e.getBoundingClientRect().width)}));
    if(mobile.width>390 || mobile.chartWidths.some(w=>w<=0)) throw Error('Mobile overflow/empty temperature chart');
    const stale=await view.evaluate(async ({pid,rid})=>{
      const me=await (await fetch('/api/auth/me')).json();
      const evs=await (await fetch(`/api/projects/${pid}/evidence`)).json();
      const e=evs.find(v=>v.type==='idf'&&v.scheme_id==='baseline');
      const response=await fetch(`/api/projects/${pid}/evidence/${e.evidence_id}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token},body:JSON.stringify({expected_revision:e.revision,review_state:'pending',responsible_person:'隔离温度验收',review_note:'撤回参考模型确认，验证温度曲线清空；保留原件。'})});
      if(!response.ok) throw Error('Withdraw failed');
      const r=await (await fetch(`/api/runs/${rid}/report.json`)).json();
      if(r.run.status!=='stale'||r.run.metrics!==null) throw Error('Stale result exposed');
      return {status:r.run.status,metrics:r.run.metrics,source_hash:e.hash};
    },{pid:report.run.project_id,rid:report.run.run_id});
    await view.locator('.hourly-temperature-panel').waitFor({state:'detached',timeout:15000});
    if(errors.length) throw Error(errors.join('\n'));
    return {run_id:report.run.run_id,project_id:report.run.project_id,engine_calls:report.run.engine_calls_executed,
      sql_sha256:receipt.sql_sha256,model_sha256:receipt.model_sha256,hours:8760,headless_animation_frame:animationFrame,
      normal_clicks_passed:false,keyboard_navigation_passed:true,zones:checks,mobile,screenshot,stale,stale_curves_removed:true,page_errors:errors,credentials_saved:false};
  } finally { await browser.close(); }
}

