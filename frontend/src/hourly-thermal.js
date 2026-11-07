import {escape as esc} from './api.js';

const numeric = value => typeof value === 'number' && Number.isFinite(value);
const format = (value, scale = 1) => numeric(value)
  ? (value / scale).toLocaleString('zh-CN', {maximumFractionDigits: 2}) : '—';
const stamp = time => time ? `${time.month}/${time.day} ${String(time.hour_ending).padStart(2, '0')}:00` : '—';

function profileMarkup(profile) {
  const heating = profile.building?.heating_W;
  const cooling = profile.building?.cooling_W;
  if (profile.times?.length !== 24 || ![heating, cooling].every(v => Array.isArray(v) && v.length === 24 && v.every(numeric))) {
    return '<p>峰值日曲线不可用，未补零。</p>';
  }
  const maximum = Math.max(...heating, ...cooling, 1);
  const points = values => values.map((v, i) => `${56 + i * 20},${180 - v / maximum * 144}`).join(' ');
  const title = profile.selected_for === 'heating_coincident_peak' ? '采暖峰值日' : '制冷峰值日';
  return `<figure class="hourly-profile"><figcaption>${title} · ${esc(profile.times[0].month)}/${esc(profile.times[0].day)}</figcaption>
    <svg viewBox="0 0 560 220" role="img" aria-label="${title}全楼逐时平均显热负荷，横轴为小时结束时刻，纵轴为千瓦">
      <path d="M56 30V180H526" fill="none" stroke="currentColor" opacity=".4"/>
      <path d="M56 108H526M56 36H526" fill="none" stroke="currentColor" opacity=".12"/>
      <text x="8" y="40">${format(maximum, 1000)}</text><text x="20" y="184">0</text><text x="8" y="18">kW</text>
      <polyline class="hourly-heating" points="${points(heating)}"/><polyline class="hourly-cooling" points="${points(cooling)}"/>
      <text x="48" y="204">01</text><text x="268" y="204">12</text><text x="508" y="204">24</text>
    </svg><p class="hourly-legend"><span>实线：采暖</span><span>虚线：制冷</span></p>
    <details><summary>查看 24 小时数值</summary><div class="hourly-table"><table><thead><tr><th>小时结束</th><th>采暖 kW</th><th>制冷 kW</th></tr></thead><tbody>${profile.times.map((t, i) => `<tr><td>${esc(stamp(t))}</td><td>${format(heating[i], 1000)}</td><td>${format(cooling[i], 1000)}</td></tr>`).join('')}</tbody></table></div></details></figure>`;
}

export function hourlyThermalMarkup(receipt) {
  if (!receipt) return '';
  const summary = receipt.status === 'calculated_model_scenario' ? receipt.summary : null;
  const valid = summary && Array.isArray(summary.zones) && summary.building;
  const content = valid ? `<p class="subtle">${summary.environment?.EnvironmentType === 3 ? '天气运行期' : '设计日'} · ${esc(summary.environment?.EnvironmentName)} · ${esc(summary.hour_count)} 小时 · ${summary.zones.length} 个分区完整覆盖</p>
    <div class="hourly-peaks">${['heating', 'cooling'].map(mode => `<div><span>${mode === 'heating' ? '采暖' : '制冷'}同时峰值</span><strong>${format(summary.building[mode + '_peak']?.value_W, 1000)} <small>kW</small></strong><span>${esc(stamp(summary.building[mode + '_peak']?.time))} · 小时平均</span></div>`).join('')}</div>
    <div class="hourly-profiles">${(summary.peak_day_profiles || []).map(profileMarkup).join('')}</div>
    <details><summary>分区温度范围与各自峰值</summary><div class="hourly-table"><table><thead><tr><th>分区</th><th>温度范围 °C</th><th>采暖峰值 kW</th><th>制冷峰值 kW</th><th>倍率</th></tr></thead><tbody>${summary.zones.map(z => `<tr><td>${esc(z.zone_name)}</td><td>${format(z.temperature_min_C)} ～ ${format(z.temperature_max_C)}</td><td>${format(z.heating_peak?.value_W, 1000)}<br>${esc(stamp(z.heating_peak?.time))}</td><td>${format(z.cooling_peak?.value_W, 1000)}<br>${esc(stamp(z.cooling_peak?.time))}</td><td>${esc(z.zone_multiplier)} × ${esc(z.zone_list_multiplier)}</td></tr>`).join('')}</tbody></table></div><p>温度范围不能直接判定舒适性是否达标。各分区峰值时刻可能不同，不能相加代替全楼同时峰值。</p></details>`
    : `<p role="status">当前运行缺少可核验的逐时热工结果。</p><p>${esc(receipt.reason || '请检查原模型是否请求逐时温度及采暖、制冷显热交付率。')}</p>`;
  return `<section class="hourly-thermal" aria-label="逐时热工分析"><h3>逐时热工分析</h3>${content}
    <p class="hourly-boundary">小时平均负荷不等于设计容量；显热交付量不等于电耗或含潜热的总冷热量。</p>
    <details><summary>核验范围与数据来源</summary><ul>${(receipt.limitations || []).map(v => `<li>${esc(v)}</li>`).join('')}</ul><p>曲线展示两个峰值日；完整原生时序保留在证据 ZIP 的 SQL 文件中。模型原件未自动追加输出请求。</p><p class="mono">模型 ${esc(receipt.model_sha256)}<br>SQL ${esc(receipt.sql_sha256)}</p></details></section>`;
}
