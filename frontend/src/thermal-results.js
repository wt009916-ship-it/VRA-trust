import { escape as esc, number as num } from './api.js';

export function thermalResults(run){
  if(run.status!=='succeeded'||!run.metrics)return '';
  const m=run.metrics, scopes={ideal_thermal_loads:'理想冷热需求（不代表空调耗电）',packaged_heat_pump_electricity:'定容热泵 · 压缩机、风机及电辅热耗电',external_idf:'外部 IDF · 按原模型设备口径'};
  const uses=m.end_uses_kwh||{}, comfort=m.comfort_hours||{};
  const heating=comfort['Time Setpoint Not Met During Occupied Heating / Facility'];
  const cooling=comfort['Time Setpoint Not Met During Occupied Cooling / Facility'];
  return `<div class="thermal-result"><strong>${esc(scopes[m.hvac_scope]||'请核对原模型设备口径')}</strong><p>使用期间未满足温度：供暖 ${num(heating)} h · 制冷 ${num(cooling)} h。运行成功不等于容量与舒适性合格。</p><details><summary>原生 SQL 分项用能与警告（${num(run.warnings_count)} 条）</summary><div class="table-wrap"><table><thead><tr><th>用能分项</th><th>电 kWh</th><th>供热需求 kWh</th><th>供冷需求 kWh</th></tr></thead><tbody>${[['Heating','供暖（含电辅热）'],['Cooling','制冷'],['Fans','风机'],['Interior Lighting','室内照明'],['Interior Equipment','室内设备']].map(([key,label])=>`<tr><td>${label}</td>${['Electricity','District Heating','District Cooling'].map(carrier=>`<td>${num(uses[key]?.[carrier])}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p>缺失分项显示 —，不作为 0；全部能源、来源单元格与 ERR 见证据报告。</p></details></div>`;
}
