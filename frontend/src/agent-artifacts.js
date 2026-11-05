import {escape as esc} from './api.js';

const value=x=>esc(x??'—');
export function costArtifactMarkup(artifact) {
  if(!artifact || artifact.kind!=='material_cost_review')return '';
  const status={calculated:'当前清单完整',incomplete:'缺参 · 合计不可用',stale:'来源或版本已变化'};
  const rows=artifact.status==='stale'?[]:artifact.rows;
  return `<section class="agent-artifact" aria-label="已核验的材料清单结果"><h3>${esc(artifact.name)}</h3><p><strong>${esc(status[artifact.status]||artifact.status)}</strong> · ${esc(artifact.scope)}</p><p>材料合计：<strong>${value(artifact.status==='stale'?null:artifact.material_total)} ${esc(artifact.currency)}</strong> · ${artifact.tax_basis==='included'?'声明含税':'声明不含税'} · 清单日期 ${esc(artifact.as_of)}</p><p>声明范围：${esc(artifact.functional_scope)}</p><p>排除项：${artifact.exclusions.map(esc).join('；')}</p>${rows.length?`<div class="table-scroll"><table><thead><tr><th>材料</th><th>净量</th><th>采购量</th><th>金额</th><th>方法与来源</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${value(r.net_quantity)} ${esc(r.unit)}</td><td>${value(r.purchase_quantity)} ${esc(r.unit)}</td><td>${value(r.amount)} ${esc(artifact.currency)}</td><td><details><summary>${esc(r.quantity_method_text)}</summary><p>损耗率：${value(r.waste_ratio)}；计价数量：${value(r.quantity_in_quote_unit)} ${esc(r.quote_unit)}；单价：${value(r.unit_price)} ${esc(artifact.currency)}/${esc(r.quote_unit)}</p><p>${esc(r.money_method)}</p><p>数量来源：${value(r.quantity_source)}；损耗依据：${value(r.waste_source)}</p><p>价格来源：${value(r.price_source)}；版本：${value(r.price_version)}；声明有效期：${value(r.price_valid_from)} 至 ${value(r.price_valid_until)}</p>${r.missing.length?`<p>缺参：${r.missing.map(esc).join('、')}</p>`:''}</details></td></tr>`).join('')}</tbody></table></div>`:''}<p>${esc(artifact.notice)}</p><small class="mono">${esc(artifact.cost_id)} · 核验时间 ${esc(artifact.checked_at)}</small><p><a href="/api/projects/${encodeURIComponent(artifact.project_id)}/material-costs/${encodeURIComponent(artifact.cost_id)}/report.html" target="_blank" rel="noopener">打开同源清单报告</a></p></section>`;
}

export function modelCommentaryMarkup(task) {
  if(task.llm_commentary_policy==='audit_only')return '<p class="subtle">数量、金额及方法以上方核验结果为准；模型原始文字仅保留在任务审计记录中，不作为工程说明。</p>';
  return task.llm_commentary?'<details><summary>AI 解释 · 非核验工程结论</summary><p class="model-prose">'+esc(task.llm_commentary)+'</p></details>':'';
}
