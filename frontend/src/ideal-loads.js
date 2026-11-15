import {escape as esc} from './api.js';

const number=(v,scale=1)=>typeof v==='number'&&Number.isFinite(v)?(v/scale).toLocaleString('zh-CN',{maximumFractionDigits:3}):'—';
const groups=[['zone','区内交付'],['supply','供风处理'],['outdoor','新风负荷'],['recovery','热回收']];
const stamp=t=>t?`${t.month}/${t.day} ${String(t.hour_ending).padStart(2,'0')}:00`:'—';

export function idealLoadsMarkup(receipt){
  if(!receipt)return '';
  const summary=receipt.status==='calculated_model_scenario'?receipt.summary:null;
  const limits=`<ul>${(receipt.limitations||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
  if(!summary)return `<section class="hourly-thermal"><h3>理想空调显热、潜热与新风</h3><p role="status">${receipt.status==='not_applicable'?'该模型未声明理想空调系统':'该运行缺少可核验的显潜热输出'}：${esc(receipt.reason||'来源尚未核验')}。结果未填零。</p>${limits}</section>`;
  const rows=(values)=>groups.flatMap(([g,label])=>[['heating','加热'],['cooling','冷却']].map(([mode,direction])=>{
    const s=values?.[`${g}_sensible_${mode}_W`],l=values?.[`${g}_latent_${mode}_W`],t=values?.[`${g}_total_${mode}_W`];
    return `<tr><th>${label} · ${direction}</th><td>${number(s?.energy_kWh)}</td><td>${number(l?.energy_kWh)}</td><td>${number(t?.energy_kWh)}</td><td>${number(t?.peak?.value,1000)}</td><td>${esc(stamp(t?.peak?.time))}</td></tr>`;
  })).join('');
  const table=values=>`<div class="hourly-table"><table><thead><tr><th>边界与方向</th><th>显热 kWh</th><th>潜热 kWh</th><th>合计 kWh</th><th>合计小时峰值 kW</th><th>峰值时刻</th></tr></thead><tbody>${rows(values)}</tbody></table></div>`;
  return `<section class="hourly-thermal"><h3>理想空调显热、潜热与新风</h3><p>${esc(summary.environment?.EnvironmentName||'原生环境')} · ${esc(summary.hour_count)}小时 · ${esc(summary.coverage?.ideal_system_count)}套理想系统</p><p>以下仅汇总已覆盖系统。四个边界分别阅读，不能再相加；热量不等于耗电或设备选型容量。原生倍率已包含。</p>${table(summary.aggregate)}<details><summary>设备、分区及SQL来源</summary>${(summary.systems||[]).map(s=>`<h4>${esc(s.system_name)} · ${esc(s.zone_name)}</h4><p>分区/分组倍率 ${esc(s.zone_multiplier)} / ${esc(s.zone_list_multiplier)}，不再次相乘；除湿 ${esc(s.dehumidification_control)}，加湿 ${esc(s.humidification_control)}，热回收 ${esc(s.heat_recovery_type)}。</p>${table(s.results)}<p>新风最大流量 ${number(s.results?.outdoor_mass_kg_s?.peak?.value)} kg/s；供风最大流量 ${number(s.results?.supply_mass_kg_s?.peak?.value)} kg/s。</p><details><summary>字典行及模型绑定</summary><pre>${esc(JSON.stringify({model:receipt.model_sha256,sql:receipt.sql_sha256,locators:s.locators},null,2))}</pre></details>`).join('')}<pre>${esc(JSON.stringify(summary.coverage,null,2))}</pre></details>${limits}</section>`;
}
