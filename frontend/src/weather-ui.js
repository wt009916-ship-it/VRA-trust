import { request, post, escape as esc, number as num } from './api.js';

const fields = {temperature_order:'最低／均温／最高温次序异常',temperature_c:'干球气温',dew_point_c:'露点气温',humidity_pct:'相对湿度',pressure_pa:'气压',infrared_wh_m2:'水平红外辐射',ghi_wh_m2:'总水平辐射',dni_wh_m2:'法向直接辐射',dhi_wh_m2:'散射辐射',wind_direction_deg:'风向',wind_m_s:'风速',solar_kwh_m2:'太阳辐射',minimum_c:'日最低温',maximum_c:'日最高温',precipitation_mm:'降水',timestamp_or_columns:'时间或列数',dew_point_above_dry_bulb:'露点高于干球温度'};
const tag = (text, type='') => `<span class="badge ${type}">${esc(text)}</span>`;
const period = d => d.kind === 'epw' ? '逐时气象年 · 原始年份见 CSV' : `${esc(d.options.start)} → ${esc(d.options.end)}`;

// Segments break at missing months. A missing value must never become a zero or an interpolated line.
export function temperatureSegments(months) {
  const result = []; let line = [];
  for (let month=1; month<=12; month++) {
    const m = months.find(x=>x.month===month);
    if (typeof m?.temperature_c === 'number' && Number.isFinite(m.temperature_c)) line.push(m);
    else if (line.length) { result.push(line); line=[]; }
  }
  if (line.length) result.push(line);
  return result;
}

export function climateChart(months) {
  const valid = months.filter(m=>Number.isFinite(m.temperature_c) && m.temperature_c !== null);
  const low = Math.floor(Math.min(0, ...valid.map(m=>m.temperature_c))/10)*10;
  const high = Math.ceil(Math.max(30, ...valid.map(m=>m.temperature_c))/10)*10;
  const solarMax = Math.max(50,...months.map(m=>m.solar_kwh_m2||0));
  const x=m=>46+(m-1)*50, y=t=>190-(t-low)/(high-low)*150;
  return `<svg class="climate-chart" viewBox="0 0 640 235" role="img" aria-label="月度有效日均温与区间月度太阳辐射，具体数据见下方表格">
    ${[0,1,2,3].map(i=>{const t=low+(high-low)*i/3;return `<line x1="40" x2="617" y1="${y(t)}" y2="${y(t)}" class="chart-grid"/><text x="32" y="${y(t)+4}" text-anchor="end">${num(t,0)}°</text>`;}).join('')}
    ${Array.from({length:12},(_,i)=>`<text x="${x(i+1)}" y="215" text-anchor="middle">${i+1}月</text>`).join('')}
    ${months.filter(m=>m.solar_kwh_m2!==null).map(m=>`<rect x="${x(m.month)-13}" y="${190-m.solar_kwh_m2/solarMax*130}" width="26" height="${m.solar_kwh_m2/solarMax*130}" rx="4" class="solar-bar"><title>${m.month}月太阳辐射 ${num(m.solar_kwh_m2)} kWh/m²</title></rect>`).join('')}
    ${temperatureSegments(months).map(seg=>`<polyline points="${seg.map(m=>`${x(m.month)},${y(m.temperature_c)}`).join(' ')}" class="temperature-line"/>`).join('')}
    ${valid.map(m=>`<circle cx="${x(m.month)}" cy="${y(m.temperature_c)}" r="4" class="temperature-dot"><title>${m.month}月有效日均温 ${num(m.temperature_c)} °C</title></circle>`).join('')}
    <text x="618" y="18" text-anchor="end">辐射柱满刻度 ${num(solarMax,0)} kWh/m²</text></svg>`;
}

function heatmap(data) {
  if (!data.heatmap.length) return '';
  return `<section class="studio-panel"><div class="panel-title"><div><span class="eyebrow">HOURLY PATTERN</span><h3>逐时温度分布</h3></div><span class="subtle">月 × 时段结束小时 · °C</span></div><div class="heatmap-scroll"><div class="weather-heatmap"><span></span>${Array.from({length:24},(_,i)=>`<span class="heat-label">${i+1}</span>`).join('')}${Array.from({length:12},(_,i)=>`<span class="heat-label">${i+1}月</span>${data.heatmap.filter(c=>c.month===i+1).map(c=>`<span class="heat-cell ${c.temperature_c===null?'heat-missing':''}" style="--heat:${c.temperature_c===null?0:Math.max(0,Math.min(220,220-(c.temperature_c+10)*5))}" title="${c.month}月 ${c.hour}时：${num(c.temperature_c)} °C；有效 ${c.valid_count} 条">${c.temperature_c===null?'—':''}</span>`).join('')}`).join('')}</div></div><p class="chart-note">蓝色较冷，橙色较暖；灰格为缺失。每格为该月同一小时的有效气温均值，悬停可查看数值和样本数。</p></section>`;
}

function analysisMarkup(d, base) {
  const q=d.quality, annual=d.annual;
  const metrics=[['全年平均气温',annual.temperature_c,'°C'],[`采暖度日 HDD${d.options.heating_base_c}`,annual.heating_degree_days,'°C·d'],[`制冷度日 CDD${d.options.cooling_base_c}`,annual.cooling_degree_days,'°C·d'],['全年水平太阳辐射',annual.solar_kwh_m2,'kWh/m²']];
  return `<div class="weather-selection"><div><span class="eyebrow">${d.kind==='epw'?'ENERGYPLUS WEATHER':'NASA POWER · DAILY'}</span><h2>${esc(d.name)}</h2><p>${period(d)} · ${num(d.location.latitude,3)}°, ${num(d.location.longitude,3)}°</p></div>${tag(d.kind==='epw'?(q.simulation_candidate?'质量检查通过 · 待项目复核':'存在质量问题'):'气候分析资料 · 非仿真 EPW',q.issues.length?'warning':'success')}</div>
  <div class="weather-metrics">${metrics.map(([name,value,unit])=>`<article class="metric-card"><span>${esc(name)}</span><strong>${num(value,1)}<small>${unit}</small></strong><p>${value===null?'全年完整资料不足，未生成此指标':'根据本次原始数据计算'}</p></article>`).join('')}</div>
  <div class="weather-analysis-grid"><section class="studio-panel"><div class="panel-title"><div><span class="eyebrow">CLIMATE PROFILE</span><h3>月度气候画像</h3></div><div class="chart-legend"><span class="legend-temp">日均气温</span><span class="legend-solar">太阳辐射</span></div></div>${climateChart(d.monthly)}<p class="chart-note">气温为有效日均值的均值；缺测不连线。辐射为所选区间内的月累计，部分年份不能与完整年直接比较。</p></section>
  <section class="studio-panel quality-panel"><div class="panel-title"><div><span class="eyebrow">DATA QUALITY</span><h3>数据质量</h3></div>${tag(q.issues.length?'需检查':'范围内通过',q.issues.length?'warning':'success')}</div><dl class="quality-stats"><div><dt>记录 / 应有</dt><dd>${num(q.records,0)} / ${num(q.expected_records,0)}</dd></div><div><dt>缺少时段</dt><dd>${num(q.missing_records,0)}</dd></div><div><dt>重复记录</dt><dd>${num(q.duplicate_records,0)}</dd></div><div><dt>完整全年时序</dt><dd>${q.full_year?'是':'否'}</dd></div></dl>${Object.entries(q.invalid_fields).length?'<ul class="quality-errors">'+Object.entries(q.invalid_fields).map(([k,n])=>`<li>${esc(fields[k]||k)}<strong>${num(n,0)} 条</strong></li>`).join('')+'</ul>':'<p class="quality-clean">已检查字段未发现缺测或越界值。</p>'}${q.issues.map(s=>`<p class="error-text">${esc(s)}</p>`).join('')}<p class="chart-note">质量检查不证明站点代表性或真实测量精度。</p></section></div>
  <section class="weather-insights"><span class="insight-symbol">↗</span><div><h3>自动分析摘要</h3><ul>${d.insights.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><p>计算规则：HDD = Σ max(0, 采暖基准 − 日均温)；CDD = Σ max(0, 日均温 − 制冷基准)。</p></div></section>
  ${heatmap(d)}<section class="studio-panel"><div class="panel-title"><div><span class="eyebrow">ORGANIZED DATA</span><h3>整理后的月度数据</h3></div><a class="button-link" href="/api${base}/${d.weather_id}/data.csv">下载${d.kind==='epw'?'逐时':'逐日'} CSV ↓</a></div><div class="table-scroll"><table><caption class="sr-only">月度气象汇总，— 表示缺失或不完整，不等于零</caption><thead><tr><th>月份</th><th>有效温度日 / 应有</th><th>均温 °C</th><th>低 / 高 °C</th><th>湿度 %</th><th>风速 m/s</th><th>辐射 kWh/m²</th><th>HDD / CDD</th></tr></thead><tbody>${d.monthly.map(m=>`<tr><td>${m.month}月</td><td>${m.valid_temperature_days} / ${m.expected_days}</td><td>${num(m.temperature_c,1)}</td><td>${num(m.minimum_c,1)} / ${num(m.maximum_c,1)}</td><td>${num(m.humidity_pct,1)}</td><td>${num(m.wind_m_s,1)}</td><td>${num(m.solar_kwh_m2,1)}</td><td>${num(m.heating_degree_days,1)} / ${num(m.cooling_degree_days,1)}</td></tr>`).join('')}</tbody></table></div><p class="chart-note">湿度、风速使用有效记录的均值；极值来自${d.kind==='epw'?'小时气温':'逐日最低／最高气温'}。缺测详见质量清单和 CSV。NASA 降水记录可在 CSV 中查看。</p></section>
  <section class="studio-panel source-panel"><div class="panel-title"><div><span class="eyebrow">SOURCE & NEXT STEP</span><h3>来源与工程使用</h3></div><div class="actions"><a class="button-link" href="/api/projects/${d.project_id}/files/${d.file_id}" target="_blank" rel="noopener">原始文件 ↗</a>${d.kind==='epw'&&q.simulation_candidate?'<button id="weather-register">登记为天气证据</button>':''}</div></div><p>${esc(d.time_basis)}</p><ul>${d.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><details><summary>来源、抓取参数与 SHA-256</summary><dl><dt>原始文件 SHA-256</dt><dd class="mono">${esc(d.source_hash)}</dd><dt>分析版本</dt><dd>${esc(d.analyzer_version)} · ${esc(d.created_at)}</dd></dl><pre>${esc(JSON.stringify(d.provenance,null,2))}</pre></details></section>`;
}

export async function weatherWorkspace(state, host, action, notice, modal, sync) {
  const pid=state.project.project_id, base='/projects/'+pid+'/weather';
  const live=()=>host.isConnected && state.project?.project_id===pid;
  let selected=null, history=[], generation=0;
  const [sources, records]=await Promise.all([request(base+'/sources'),request(base)]);
  if(!live())return;
  history=records;
  const year=new Date().getFullYear()-1;
  host.innerHTML=`<div class="view-heading"><div><span class="eyebrow">CLIMATE INTELLIGENCE</span><h1>气候与天气</h1><p>获取公开气象资料，整理数据，再为建筑仿真选择合适的天气。</p></div><span class="workspace-label"><i></i>来源可追溯</span></div><div class="weather-intake"><section class="studio-panel nasa-intake"><div class="panel-title"><div><span class="eyebrow">01 · PUBLIC DATA</span><h3>获取 NASA 历史气象</h3></div>${tag('已接入')}</div><form id="nasa-form"><div class="weather-form-grid"><label class="weather-place">地点标注<input name="label" required maxlength="120" placeholder="例如：武汉项目所在地"></label><label>纬度 °N<input name="latitude" type="number" min="-90" max="90" step="any" required placeholder="30.59"></label><label>经度 °E<input name="longitude" type="number" min="-180" max="180" step="any" required placeholder="114.30"></label><label>开始日期<input name="start" type="date" required value="${year}-01-01" min="1984-01-01"></label><label>结束日期<input name="end" type="date" required value="${year}-12-31"></label></div><details class="weather-options"><summary>度日基准与数据更新</summary><div class="form-grid"><label>采暖基准 °C<input name="heating_base_c" type="number" value="18" step="0.1" min="0" max="30" required></label><label>制冷基准 °C<input name="cooling_base_c" type="number" value="26" step="0.1" min="10" max="40" required></label></div><label class="check-option"><input type="checkbox" name="refresh">重新抓取并保存新版本（通常复用已保存数据即可）</label></details><div class="intake-footer"><span>日尺度 · 同一自然年 · 无需 API Key</span><button class="primary" type="submit">获取并分析 ↗</button></div><p id="weather-fetch-status" role="status"></p></form></section>
  <section class="studio-panel epw-intake"><div class="panel-title"><div><span class="eyebrow">02 · SIMULATION WEATHER</span><h3>检查 EnergyPlus 天气</h3></div>${tag('EPW')}</div><p>检查逐时气象年、缺测标记、异常值和时间连续性，保留原文件并生成整理表。</p><form id="epw-form"><label class="weather-upload">上传 .epw 文件<input name="file" type="file" accept=".epw" required></label><button type="submit">上传并检查 EPW</button></form><div class="existing-epw">${state.evidence.filter(e=>e.type==='epw'&&e.source_file).map(e=>`<button data-existing-epw="${e.source_file}">分析项目已有天气 · ${esc(e.name)} →</button>`).join('')}</div><p class="chart-note">日均 NASA 数据不能替代逐时 EPW。通过检查后，仍需确认项目地点和适用气象年。</p></section></div>
  <section class="weather-history"><label>已保存的分析<select id="weather-history" aria-label="选择天气分析"></select></label><span id="weather-history-note"></span></section><div id="weather-result"><div class="weather-empty"><span>◎</span><h2>让气候资料成为项目的第一层依据</h2><p>输入经纬度获取历史资料，或上传 EPW。分析结果、质量问题和原始来源将在这里展示。</p></div></div><section class="weather-catalog"><div class="section-title"><h2>公开数据与工具入口</h2><span>接口接入状态明确标注</span></div><div class="weather-source-grid">${sources.map(s=>`<a class="source-card" href="${esc(s.url)}" target="_blank" rel="noopener"><small>${esc(s.kind)}</small><h3>${esc(s.name)} ↗</h3><p>${esc(s.description)}</p></a>`).join('')}</div></section>`;
  const paintHistory=()=>{host.querySelector('#weather-history').innerHTML=history.length?history.map(d=>`<option value="${d.weather_id}" ${selected?.weather_id===d.weather_id?'selected':''}>${esc(d.name)} · ${d.invalid?'来源已失效':d.kind==='epw'?'EPW':d.options.start+' 至 '+d.options.end}</option>`).join(''):'<option value="">暂无分析记录</option>';host.querySelector('#weather-history-note').textContent=`${history.length} 份记录 · 原始数据保留在项目中`;};
  const show=async id=>{const token=++generation; const d=await request(base+'/'+id);if(!live()||token!==generation)return;selected=d;host.querySelector('#weather-result').innerHTML=analysisMarkup(d,base);paintHistory();const button=host.querySelector('#weather-register');if(button)button.onclick=()=>registerEvidence(d);};
  const saved=async d=>{if(!live())return;history=await request(base);if(!live())return;await show(d.weather_id);};
  function registerEvidence(d) {
    const existing=state.evidence.find(e=>e.type==='epw'&&e.source_file===d.file_id);
    if(existing){notice('此文件已登记为天气证据，请在「资料」中查看复核状态。');return;}
    const dialog=modal('登记天气来源',`<form id="weather-evidence"><p>登记后状态为待复核，不会自动确认，也不会覆盖其他 EPW 证据。</p><label>来源单位、版本与日期<input name="authority" required maxlength="300"></label><label>使用授权或许可依据<input name="permission" required maxlength="500"></label><label>登记人<input name="person" required value="${esc(state.user.display_name)}"></label><button type="submit" class="primary">保存为待复核证据</button></form>`);
    dialog.querySelector('form').onsubmit=e=>{e.preventDefault();const form=new FormData(e.currentTarget);action(async()=>{await post('/projects/'+pid+'/evidence',{type:'epw',name:d.name.slice(0,150)+' · EPW',source_file:d.file_id,source_locator:'原始 EPW LOCATION / DATA PERIODS 与逐时记录；天气分析 '+d.weather_id,authority:form.get('authority'),permission:form.get('permission'),responsible_person:form.get('person'),acquisition_method:'weather_workspace_upload',status:'IMPORTED',uncertainty:'自动质量检查不能代替地点与气象年适用性复核。'});if(!live())return;const evidence=await request('/projects/'+pid+'/evidence');if(!live())return;state.evidence=evidence;dialog.close();await sync(pid);notice('已登记天气证据，请前往「资料」完成人工复核。');},e.submitter);};
  }
  host.querySelector('#weather-history').onchange=e=>action(async()=>{selected=null;host.querySelector('#weather-result').innerHTML='<p class="empty">正在核对原始来源…</p>';try{await show(e.target.value);}catch(err){if(live())host.querySelector('#weather-result').innerHTML='<p class="empty error-text">'+esc(err.message)+'</p>';throw err;}});
  host.querySelector('#nasa-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget), body=Object.fromEntries(f);for(const k of ['latitude','longitude','heating_base_c','cooling_base_c'])body[k]=Number(body[k]);body.refresh=f.has('refresh');action(async()=>{const status=host.querySelector('#weather-fetch-status');status.textContent='正在请求 NASA 并校验原始数据，通常需要数秒至 45 秒…';try{await saved(await post(base+'/nasa',body));if(live())status.textContent='数据已保存，月度分析与整理表已更新。';}catch(err){if(live())status.textContent='获取失败，本次没有生成新的天气结果。';throw err;}},e.submitter);};
  host.querySelector('#epw-form').onsubmit=e=>{e.preventDefault();const file=e.currentTarget.elements.file.files[0];action(async()=>{const f=new FormData();f.append('file',file);const record=await request('/projects/'+pid+'/files',{method:'POST',body:f});await saved(await post(base+'/epw',{file_id:record.file_id}));},e.submitter);};
  host.querySelectorAll('[data-existing-epw]').forEach(b=>{b.onclick=()=>action(async()=>saved(await post(base+'/epw',{file_id:b.dataset.existingEpw})),b);});
  paintHistory();
  if(history.length){if(history[0].invalid)host.querySelector('#weather-result').innerHTML='<p class="empty error-text">最近分析的原始来源已变化，请重新导入并分析。</p>';else await show(history[0].weather_id);}
}
