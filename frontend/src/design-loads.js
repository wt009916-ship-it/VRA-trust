import {escape as esc} from './api.js';

const kw = value => typeof value === 'number' && Number.isFinite(value)
  ? (value / 1000).toLocaleString('zh-CN', {minimumFractionDigits: 2, maximumFractionDigits: 3}) : '—';

export function designLoadsMarkup(loads) {
  if (!loads) return '';
  const available = loads.status === 'calculated_model_scenario' && Array.isArray(loads.rows);
  const site = loads.basis?.declared_site;
  const station = loads.weather_station;
  return `<section class="design-loads" aria-label="分区设计显热负荷"><h3>分区设计显热负荷</h3>
    <p class="subtle">输入模型的设计工况结果 · 工程适用性待复核</p>
    ${available ? `<div class="design-loads-table"><table><thead><tr><th>分区 / 工况</th><th>计算显热 kW</th><th>用户调整后 kW</th><th>峰值设计日 / 时刻</th></tr></thead><tbody>
      ${loads.rows.slice(0, 100).map(row => `<tr><td>${esc(row.zone_name)}<span>${row.load_type === 'Heating' ? '采暖' : '制冷'}</span></td>
        <td>${kw(row.calculated_sensible_load_W)}</td><td>${kw(row.user_adjusted_sensible_load_W)}</td>
        <td>${row.peak ? `${esc(row.peak.design_day)}<span>${esc(row.peak.date_time)}</span>` : '无正负荷峰值'}</td></tr>`).join('')}
      </tbody></table></div>` : '<p role="status">当前运行未取得可核验的分区设计负荷。</p>'}
    ${available && loads.rows.length > 100 ? `<p>当前展示前 100 行，共 ${esc(loads.rows.length)} 行；完整结果见 JSON 报告。</p>` : ''}
    <p>显热负荷不等于设备总容量；各分区峰值不能直接相加作为全楼同时峰值。</p>
    ${loads.site_comparison === 'declared_site_differs_from_weather' ? '<p class="design-loads-warning">IDF 声明位置与天气站坐标不同，请核对设计日来源及原生引擎采用的位置。当前数值仅代表输入模型情景。</p>' : ''}
    <details><summary>工况、倍率和来源</summary>
      <p>IDF 声明位置：${esc(site?.name || '未核验')}；EPW 站点：${esc(station?.city || '未核验')}。</p>
      <p>设计日统计来源、版本及项目适用性尚需专业复核；坐标相近不等于已验证。</p>
      <ul>${(loads.basis?.design_days || []).map(day => `<li>${esc(day.name)}：${esc(day.month)}/${esc(day.day)}，最高干球 ${esc(day.maximum_dry_bulb_C)} °C，日温差 ${esc(day.daily_dry_bulb_range_K)} K。</li>`).join('')}</ul>
      ${available ? `<ul>${loads.rows.slice(0, 100).filter(row => row.load_type === 'Heating').map(row => `<li>${esc(row.zone_name)}：分区倍率 ${esc(row.zone_multiplier)} × 分组倍率 ${esc(row.zone_list_multiplier)}，已计入原生负荷。</li>`).join('')}</ul>` : `<p>${esc(loads.reason || '缺少核验依据')}</p>`}
      ${(loads.zones_without_sizing || []).length ? `<p>以下分区没有定容结果，不能计为零：${esc(loads.zones_without_sizing.join('、'))}</p>` : ''}
      <p>原生表格交叉核对：${loads.tabular_crosscheck === 'matched_W_cells' ? 'W 单位单元格一致' : '未执行，不作为通过项'}。</p>
      <p class="mono">模型 ${esc(loads.model_sha256)}<br>SQL ${esc(loads.sql_sha256)}</p>
    </details></section>`;
}
