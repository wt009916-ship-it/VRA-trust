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

export function temperatureProfileMarkup(profile, zoneName) {
  const values = profile.zones?.[zoneName]?.temperature_C;
  if (profile.times?.length !== 24 || !Array.isArray(values) || values.length !== 24 || !values.every(numeric)) {
    return '<p role="status">该分区温度曲线不可用，未补零或插值。</p>';
  }
  const minimum = Math.min(...values), maximum = Math.max(...values);
  // Keep a visible scale for constant/near-constant series; never imply a zero origin.
  const padding = Math.max((maximum - minimum) * .1, .5);
  const bottom = minimum - padding, top = maximum + padding;
  const points = values.map((v, i) => `${56 + i * 20},${180 - (v - bottom) / (top - bottom) * 144}`).join(' ');
  const title = profile.selected_for === 'heating_coincident_peak' ? '采暖峰值日' : '制冷峰值日';
  return `<figure class="hourly-profile hourly-temperature"><figcaption>${title} · ${esc(profile.times[0].month)}/${esc(profile.times[0].day)} · ${esc(zoneName)}</figcaption>
    <svg viewBox="0 0 560 220" role="img" aria-label="${esc(zoneName)} ${title}逐时平均室内空气温度，纵轴自动缩放，单位摄氏度">
      <path d="M56 36V180H526M56 36H526M56 108H526" fill="none" stroke="currentColor" opacity=".2"/>
      <text x="2" y="40">${format(top)}</text><text x="2" y="184">${format(bottom)}</text><text x="8" y="18">°C</text>
      <polyline class="hourly-temperature-line" points="${points}"/>
      <text x="48" y="204">01</text><text x="268" y="204">12</text><text x="508" y="204">24</text>
    </svg><p class="subtle">当日范围 ${format(minimum)} ～ ${format(maximum)} °C · 纵轴自动缩放</p>
    <details><summary>查看 24 小时温度数值</summary><div class="hourly-table"><table><thead><tr><th>小时结束</th><th>空气温度 °C</th></tr></thead><tbody>${profile.times.map((t, i) => `<tr><td>${esc(stamp(t))}</td><td>${format(values[i])}</td></tr>`).join('')}</tbody></table></div></details></figure>`;
}

function temperaturesMarkup(summary, index) {
  const zone = summary.zones[index]?.zone_name;
  if (!zone) return '<p role="status">请选择有效分区。</p>';
  const profiles = summary.peak_day_profiles || [];
  if (!profiles.length) return '<p role="status">当前运行没有峰值日温度时序。</p>';
  return profiles.map(profile => temperatureProfileMarkup(profile, zone)).join('');
}

export function bindHourlyThermal(root, receipt) {
  if (receipt?.status !== 'calculated_model_scenario') return;
  const select = root.querySelector('[data-temperature-zone]');
  const target = root.querySelector('[data-temperature-profiles]');
  if (!select || !target) return;
  select.addEventListener('change', () => {
    const index = /^\d+$/.test(select.value) ? Number(select.value) : -1;
    target.innerHTML = temperaturesMarkup(receipt.summary, index);
  });
}

export function hourlyThermalMarkup(receipt) {
  if (!receipt) return '';
  const summary = receipt.status === 'calculated_model_scenario' ? receipt.summary : null;
  const valid = summary && Array.isArray(summary.zones) && summary.building;
  const content = valid ? `<p class="subtle">${summary.environment?.EnvironmentType === 3 ? '天气运行期' : '设计日'} · ${esc(summary.environment?.EnvironmentName)} · ${esc(summary.hour_count)} 小时 · ${summary.zones.length} 个分区完整覆盖</p>
    <div class="hourly-peaks">${['heating', 'cooling'].map(mode => `<div><span>${mode === 'heating' ? '采暖' : '制冷'}同时峰值</span><strong>${format(summary.building[mode + '_peak']?.value_W, 1000)} <small>kW</small></strong><span>${esc(stamp(summary.building[mode + '_peak']?.time))} · 小时平均</span></div>`).join('')}</div>
    <div class="hourly-profiles">${(summary.peak_day_profiles || []).map(profileMarkup).join('')}</div>
    <div class="hourly-temperature-panel"><h4>分区室温变化</h4>
      <label>查看分区 <select data-temperature-zone aria-label="室温曲线分区">${summary.zones.map((z, i) => `<option value="${i}">${esc(z.zone_name)}</option>`).join('')}</select></label>
      <p>按全楼采暖与制冷峰值日展示，未必包含该分区全年温度极值。空气温度不等于操作温度；没有占用日程及评价条件时，不判定舒适性达标。</p>
      <div class="hourly-profiles" data-temperature-profiles>${temperaturesMarkup(summary, 0)}</div>
    </div>
    <details><summary>分区温度范围与各自峰值</summary><div class="hourly-table"><table><thead><tr><th>分区</th><th>温度范围 °C</th><th>采暖峰值 kW</th><th>制冷峰值 kW</th><th>倍率</th></tr></thead><tbody>${summary.zones.map(z => `<tr><td>${esc(z.zone_name)}</td><td>${format(z.temperature_min_C)} ～ ${format(z.temperature_max_C)}</td><td>${format(z.heating_peak?.value_W, 1000)}<br>${esc(stamp(z.heating_peak?.time))}</td><td>${format(z.cooling_peak?.value_W, 1000)}<br>${esc(stamp(z.cooling_peak?.time))}</td><td>${esc(z.zone_multiplier)} × ${esc(z.zone_list_multiplier)}</td></tr>`).join('')}</tbody></table></div><p>温度范围不能直接判定舒适性是否达标。各分区峰值时刻可能不同，不能相加代替全楼同时峰值。</p></details>`
    : `<p role="status">当前运行缺少可核验的逐时热工结果。</p><p>${esc(receipt.reason || '请检查原模型是否请求逐时温度及采暖、制冷显热交付率。')}</p>`;
  return `<section class="hourly-thermal" aria-label="逐时热工分析"><h3>逐时热工分析</h3>${content}
    <p class="hourly-boundary">小时平均负荷不等于设计容量；显热交付量不等于电耗或含潜热的总冷热量。</p>
    <details><summary>核验范围与数据来源</summary><ul>${(receipt.limitations || []).map(v => `<li>${esc(v)}</li>`).join('')}</ul><p>曲线展示两个峰值日；完整原生时序保留在证据 ZIP 的 SQL 文件中。模型原件未自动追加输出请求。</p><p class="mono">模型 ${esc(receipt.model_sha256)}<br>SQL ${esc(receipt.sql_sha256)}</p></details></section>`;
}
