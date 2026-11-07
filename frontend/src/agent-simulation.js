import {escape as esc, number as num} from './api.js';
import {designLoadsMarkup} from './design-loads.js';

export function simulationArtifactMarkup(answer) {
  const artifact = answer?.simulation_artifact;
  if (!artifact) return '';
  const current = artifact.verified && artifact.status === 'succeeded' && artifact.metrics;
  const progress = answer.sizing_read_progress;
  const coverage = progress?.total_rows != null
    ? `<p>模型实际读取负荷行：${esc(progress.read_rows)} / ${esc(progress.total_rows)}。${progress.state === 'partial' ? '仍有未读行，不能判为全部覆盖。' : progress.state === 'not_requested' ? '本次未由模型分页读取。' : '这些行已由模型工具读取，不等于解释或自由问题全部核验。'}</p>` : '';
  return `<section class="agent-artifact" aria-label="当前原生运行结果"><h3>当前原生运行结果</h3>
    <p>以下数值由服务端重新核验原生运行；模型读取覆盖单列，模型文字不替代原生结果。</p>${coverage}
    ${current ? `<p>全年场地能耗：${num(artifact.metrics.annual_energy_kwh)} kWh；EUI：${num(artifact.metrics.eui_kwh_m2a)} kWh/(m²·a)；面积：${num(artifact.metrics.area_m2)} m²。</p>${designLoadsMarkup(artifact.metrics.zone_design_loads)}`
      : `<p>当前状态：${esc(artifact.status || '不可用')}。未显示历史数值；请复核来源和运行状态。</p><p>${esc(artifact.error || '')}</p>`}
    <small class="mono">${esc(artifact.run_id || '')}</small>
    ${artifact.run_id ? `<p><a href="/api/runs/${encodeURIComponent(artifact.run_id)}/report.html" target="_blank" rel="noopener">打开当前同源报告</a></p>` : ''}
    </section>`;
}
