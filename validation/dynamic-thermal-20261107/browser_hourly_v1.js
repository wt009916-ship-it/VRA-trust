async (page) => {
  const data = await page.evaluate(async () => {
    const panel = document.querySelector('.hourly-thermal');
    if (!panel) throw new Error('Missing hourly panel');
    const href = document.querySelector('.report-actions a[href$="/report.json"]').getAttribute('href');
    const reportResponse = await fetch(href);
    const report = await reportResponse.json();
    const run = report.run;
    const response = await fetch('/api/runs/' + run.run_id);
    const current = await response.json();
    if (JSON.stringify(current.metrics) !== JSON.stringify(run.metrics)) throw new Error('Report/API mismatch');
    const receipt = run.metrics.hourly_thermal;
    if (receipt.status !== 'calculated_model_scenario' || receipt.summary.hour_count !== 8760 || receipt.summary.zones.length !== 5) throw new Error('Unexpected coverage');
    const expected = ['heating', 'cooling'].map(mode => (receipt.summary.building[mode + '_peak'].value_W / 1000).toLocaleString('zh-CN', {maximumFractionDigits: 2}));
    if (!expected.every(v => panel.textContent.includes(v))) throw new Error('Displayed peaks mismatch');
    const curves = [...panel.querySelectorAll('polyline')].map(e => e.getAttribute('points').trim().split(/\s+/).length);
    if (curves.length !== 4 || curves.some(n => n !== 24)) throw new Error('Incomplete charts');
    const pdfResponse = await fetch(href.replace('/report.json', '/report.pdf'));
    const pdf = new Uint8Array(await pdfResponse.arrayBuffer());
    if (!pdfResponse.ok || new TextDecoder().decode(pdf.slice(0, 4)) !== '%PDF') throw new Error('PDF failed');
    const htmlResponse = await fetch(href.replace('/report.json', '/report.html'));
    const html = await htmlResponse.text();
    if (!htmlResponse.ok || !html.includes(receipt.sql_sha256)) throw new Error('HTML provenance absent');
    const digest = async bytes => [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2, '0')).join('');
    return {run_id:run.run_id,project_id:run.project_id,status:run.status,actual_engine_calls:run.engine_calls_executed,
      hourly_status:receipt.status,hours:receipt.summary.hour_count,zones:receipt.summary.zones.length,
      displayed_peaks_kW:expected,building:receipt.summary.building,report_matches_api:true,
      model_sha256:receipt.model_sha256,sql_sha256:receipt.sql_sha256,curve_points:curves,
      pdf:{bytes:pdf.length,sha256:await digest(pdf)},html_provenance:true,
      desktop:{width:innerWidth,panel_width:panel.getBoundingClientRect().width,
        charts:[...panel.querySelectorAll('svg')].map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))}};
  });
  await page.setViewportSize({width:390,height:844});
  data.mobile = await page.evaluate(() => {
    const p=document.querySelector('.hourly-thermal');
    return {viewport:innerWidth,document_width:document.documentElement.scrollWidth,panel_width:p.getBoundingClientRect().width,
      profiles_columns:getComputedStyle(p.querySelector('.hourly-profiles')).gridTemplateColumns,
      charts:[...p.querySelectorAll('svg')].map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))};
  });
  if(data.mobile.document_width>390 || data.mobile.charts.some(c=>c.width<=0 || c.height<=0)) throw new Error('Mobile layout overflow/empty chart');
  await page.setViewportSize({width:1403,height:1157});
  data.visual_screenshot='pending: native screenshot timed out; DOM and keyboard checks only';
  return data;
}
