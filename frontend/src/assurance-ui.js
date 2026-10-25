import { escape as esc, number as num } from './api.js';

export function importDiagnostics(t, base) {
  const d = t.diagnostics || t.candidate?.diagnostics;
  if (!d) return '';
  const blocked = (d.spaces || []).filter(s => s.status === 'blocked');
  return `<section class="import-diagnostics">${d.scope==='selected_storeys'?`<p>显式楼层范围：本次 ${d.total} / 源文件 ${d.source_total} 个空间；${d.excluded_by_scope} 个范围外空间未尝试。</p>`:''}<div class="assurance-counts"><span>源空间 <b>${num(d.total,0)}</b></span><span>已解析 <b>${num(d.extracted,0)}</b></span><span>待补全 <b>${num(d.blocked,0)}</b></span></div>
    <ul>${(d.actions||[]).map(a=>`<li>${esc(a)}</li>`).join('')}</ul>
    ${blocked.length?`<details open><summary>逐空间补证清单 · ${blocked.length} 项</summary><div class="diagnostic-scroll"><table><thead><tr><th>空间 / GlobalId</th><th>现有表示</th><th>修复动作</th></tr></thead><tbody>${blocked.map(s=>`<tr><td>${esc(s.name)} ${esc(s.long_name)}<code>${esc(s.global_id)}</code></td><td>${(s.representations||[]).map(r=>esc(r.identifier)+' / '+esc(r.type)).join('<br>')||'无'}<small>${esc(s.code)}</small></td><td>${esc(s.action)}<details><summary>解析详情</summary><p>${esc(s.error)}</p></details></td></tr>`).join('')}</tbody></table></div></details>`:''}
    <a href="/api${esc(base)}/imports/${esc(t.import_id)}/report.json" download>下载完整诊断与来源记录 JSON</a><p class="source-fingerprint">源文件 SHA256 <code>${esc(t.source?.hash||t.candidate?.source?.hash||'—')}</code></p></section>`;
}

export function weatherFacts(records) {
  if (!records) return '';
  return `<section class="agent-weather"><h3>天气核验结果</h3>${records.length ? records.map(w => {
    if (w.invalid) return `<article class="weather-fact-card"><strong>${esc(w.name)}</strong><p class="error-text">来源失效 · ${esc(w.error)}</p></article>`;
    const a=w.annual||{}, q=w.quality||{}, o=w.options||{};
    const metrics=[['记录数',q.records,w.kind==='epw'?'小时':'天'],['年均温',a.temperature_c,'°C'],[`HDD${o.heating_base_c??'—'}`,a.heating_degree_days,'°C·d'],[`CDD${o.cooling_base_c??'—'}`,a.cooling_degree_days,'°C·d'],['年太阳辐射',a.solar_kwh_m2,'kWh/m²']];
    return `<article class="weather-fact-card"><header><div><strong>${esc(w.name)}</strong><p>站点 ${esc(w.location?.station||'—')} · ${w.kind==='epw'?'EPW 逐时资料':'NASA 日尺度资料 · 非 EPW'}</p></div><span class="badge">${q.full_year?'完整年度':'年度不完整'}</span></header><div class="weather-fact-grid">${metrics.map(([label,value,unit])=>`<div><small>${esc(label)}</small><b>${num(value,3)}</b><span>${unit}</span></div>`).join('')}</div><p>缺记录 ${num(q.missing_records,0)} · 重复 ${num(q.duplicate_records,0)}。度日按日均温计算；这些数值不是建筑能耗。</p>${q.issues?.length?'<ul class="error-text">'+q.issues.map(i=>'<li>'+esc(i)+'</li>').join('')+'</ul>':''}<p class="source-fingerprint">源文件 SHA256 <code>${esc(w.source_hash||'—')}</code></p></article>`;
  }).join('') : '<p>尚无已保存的天气分析，请进入「气候与天气」导入 EPW 或获取日尺度资料。</p>'}</section>`;
}

export function agentAssurance(t) {
  const explanation={pending:'AI 说明生成中',available:'AI 说明可读 · 未核验',invalid:'AI 说明无效',unavailable:'AI 说明不可用',not_requested:'未请求 AI 说明'};
  return `<div class="assurance-counts" role="status"><span>工程工具 <b>${({running:'执行中',succeeded:'已完成',partial:'部分完成',failed:'失败'})[t.tool_status]||'—'}</b></span><span>${esc(explanation[t.explanation_status]||'—')}</span></div>${t.explanation_error?`<p class="error-text">${esc(t.explanation_error)} 已完成的工具结果保留如下。</p>`:''}${t.answer?.as_of?`<small>核验时间 ${esc(t.answer.as_of)} · 本次快照，资料修改后请重新核验。</small>`:''}${weatherFacts(t.answer?.weather)}`;
}
