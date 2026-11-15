import {escape as esc} from './api.js';

const number = value => value===null || value===undefined || !Number.isFinite(Number(value)) ? '—' : esc(Number(value).toLocaleString('zh-CN',{maximumSignificantDigits:12}));
export function comparisonMarkup(answer) {
  const rows=answer?.checked_comparisons||[];
  if(!rows.length)return '';
  return `<section class="agent-artifact" aria-label="来源核验后的记录比较"><h3>记录比较</h3><p>差值为对照减基准；相对变化以基准为分母。这里比较声明指标，不判断材料等效、全年节能或工程合规。</p>${rows.map(row=>{
    const ref=row.reference, available=row.status==='verified'&&row.values;
    const source=`<details><summary>查看来源与计算口径</summary><p>基准：<span class="mono">${esc(ref.baseline_id)}</span></p><p>对照：<span class="mono">${esc(ref.candidate_id)}</span></p><p>${esc(row.notice)}</p><p>至多显示12位有效数字，不代表输入精度。完整计算值保留在任务记录中。</p></details>`;
    if(!available)return `<article><h4>${esc(row.label)}</h4><p role="status">${row.status==='stale'?'来源已变化，比较数值已撤下。':'两份记录的声明口径不一致，当前不可比较。'}</p>${source}</article>`;
    const values=row.values;
    return `<article><h4>${esc(row.label)} <small>${esc(row.unit)}</small></h4><div class="table-scroll"><table><thead><tr><th>基准</th><th>对照</th>${'difference' in values?'<th>差值（对照−基准）</th>':''}${'relative_change_percent' in values?'<th>相对变化</th>':''}</tr></thead><tbody><tr><td>${number(row.baseline)}</td><td>${number(row.candidate)}</td>${'difference' in values?`<td>${number(values.difference)}</td>`:''}${'relative_change_percent' in values?`<td>${values.relative_change_percent===null?'未定义：基准为零':number(values.relative_change_percent)+'%'}</td>`:''}</tr></tbody></table></div>${source}</article>`;
  }).join('')}</section>`;
}
