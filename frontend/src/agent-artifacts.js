import {escape as esc} from './api.js';
import {engineeringArtifactMarkup} from './agent-engineering.js';
import {simulationArtifactMarkup} from './agent-simulation.js';

const value=x=>esc(x??'—');
export function selectedReadProgressMarkup(task) {
  const ids=task.unresolved_selected_reads||task.answer?.unresolved_selected_reads||[];
  if(!ids.length)return '';
  return `<section aria-label="已选读取目标未交付"><h3>仍有 ${ids.length} 个读取目标未交付</h3><p>以下编号尚无正式结果或缺失说明；流程结束不代表这些目标已完成。</p><ul>${ids.map(id=>`<li class="mono">${esc(id)}</li>`).join('')}</ul><p>请逐项读取当前结果或核验编号。此清单只跟踪已选择的读取目标，不代表原问题已经完整拆解。</p></section>`;
}
export function staleReasonMarkup(record) {
  const labels={project_revision:'项目声明版本已变化',calculator_version:'计算器或来源核验版本已变化',
    evidence_revision:'依据的版本或内容摘要已变化',evidence_rejected:'依据已撤回',evidence_missing:'依据记录不可用',
    evidence_project_mismatch:'依据项目归属不一致',source_file_revision:'原件记录已变化',source_file_unavailable:'原件缺失或完整性核验失败'};
  if(record.stale_details?.length)return '<ul>'+record.stale_details.map(d=>'<li>'+esc(labels[d.code]||'来源核验未通过')+
    (d.code==='project_revision'?'：v'+value(d.expected)+' → v'+value(d.current):'')+
    ' <small class="mono">'+esc(d.subject_id)+'</small></li>').join('')+'</ul>';
  return record.stale_reasons?.length?'<p>失效依据：'+record.stale_reasons.map(esc).join('、')+'</p>':'';
}
export function costArtifactMarkup(artifact) {
  if(!artifact || artifact.kind!=='material_cost_review')return '';
  const status={calculated:'当前清单完整',incomplete:'缺参 · 合计不可用',stale:'来源或版本已变化'};
  const rows=artifact.status==='stale'?[]:artifact.rows;
  return `<section class="agent-artifact" aria-label="已核验的材料清单结果"><h3>${esc(artifact.name)}</h3><p><strong>${esc(status[artifact.status]||artifact.status)}</strong> · ${esc(artifact.scope)}</p><p>材料合计：<strong>${value(artifact.status==='stale'?null:artifact.material_total)} ${esc(artifact.currency)}</strong> · ${artifact.tax_basis==='included'?'声明含税':'声明不含税'} · 清单日期 ${esc(artifact.as_of)}</p><p>声明范围：${esc(artifact.functional_scope)}</p><p>排除项：${artifact.exclusions.map(esc).join('；')}</p>${rows.length?`<div class="table-scroll"><table><thead><tr><th>材料</th><th>净量</th><th>采购量</th><th>金额</th><th>方法与来源</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${value(r.net_quantity)} ${esc(r.unit)}</td><td>${value(r.purchase_quantity)} ${esc(r.unit)}</td><td>${value(r.amount)} ${esc(artifact.currency)}</td><td><details><summary>${esc(r.quantity_method_text)}</summary><p>损耗率：${value(r.waste_ratio)}；计价数量：${value(r.quantity_in_quote_unit)} ${esc(r.quote_unit)}；单价：${value(r.unit_price)} ${esc(artifact.currency)}/${esc(r.quote_unit)}</p><p>${esc(r.money_method)}</p><p>数量来源：${value(r.quantity_source)}；损耗依据：${value(r.waste_source)}</p><p>价格来源：${value(r.price_source)}；版本：${value(r.price_version)}；声明有效期：${value(r.price_valid_from)} 至 ${value(r.price_valid_until)}</p>${r.missing.length?`<p>缺参：${r.missing.map(esc).join('、')}</p>`:''}</details></td></tr>`).join('')}</tbody></table></div>`:''}<p>${esc(artifact.notice)}</p><small class="mono">${esc(artifact.cost_id)} · 核验时间 ${esc(artifact.checked_at)}</small><p><a href="/api/projects/${encodeURIComponent(artifact.project_id)}/material-costs/${encodeURIComponent(artifact.cost_id)}/report.html" target="_blank" rel="noopener">打开同源清单报告</a></p></section>`;
}

export function modelCommentaryMarkup(task) {
  if(task.llm_commentary_policy==='audit_only')return '<p class="subtle">工程数值、状态及方法以上方核验结果为准；模型原始文字仅保留在任务审计记录中，不作为工程说明。</p>';
  return task.llm_commentary?'<details><summary>AI 解释 · 非核验工程结论</summary><p class="model-prose">'+esc(task.llm_commentary)+'</p></details>':'';
}

// Display rounding only; the source record and monetary decimal strings remain unchanged.
const engineeringValue=x=>value(typeof x==='number'&&Number.isFinite(x)?Number(x.toPrecision(12)):x);
const stages={production:'材料生产',transport:'运输',construction:'施工',operation:'运行',end_of_life:'报废处置'};
const statusText={calculated:'当前计算完整',incomplete:'缺参 · 结果不完整',stale:'来源或版本已变化'};
function thermalMarkup(a) {
  const r=a.status==='stale'?null:a.result,b=a.input;
  if(!r)return '<p>当前核验未通过，不显示历史计算数值。请复核来源或重新计算。</p>';
  return `<p>构造传热系数 U：<strong>${engineeringValue(r.u_w_m2k)} W/(m²·K)</strong></p><p>总热阻：${engineeringValue(r.total_resistance_m2k_w)} m²·K/W；材料层合计：${engineeringValue(r.layer_resistance_m2k_w)} m²·K/W</p><p>R总 = Rsi + Σ[d/(λ×修正系数)] + Rse；U = 1/R总</p><p>表面热阻 Rsi：${engineeringValue(b.rsi_m2k_w)}；Rse：${engineeringValue(b.rse_m2k_w)} m²·K/W。依据：${esc(b.surface_basis)}</p><p>适用条件：${esc(b.application)}</p>${r.layers.map(l=>`<details><summary>${esc(l.name)} · R = ${engineeringValue(l.resistance_m2k_w)} m²·K/W</summary><p>厚度：${engineeringValue(l.thickness)} ${esc(l.thickness_unit)} → ${engineeringValue(l.thickness_m)} m</p><p>导热系数：${engineeringValue(l.conductivity)} ${esc(l.conductivity_unit)} → ${engineeringValue(l.conductivity_w_mk)} W/(m·K)</p><p>修正系数：${engineeringValue(l.correction_factor)}；修正后导热系数：${engineeringValue(l.effective_conductivity_w_mk)} W/(m·K)。修正依据：${esc(l.correction_basis)}</p><p>材料来源：${esc(l.source)}</p></details>`).join('')}<p>来源状态：${esc(a.source_status)}。${esc(a.source_notice)}</p><p>全年节能率：未评估；规范合规：未评估。</p>${r.missing.length?`<p>缺参：${r.missing.map(esc).join('、')}</p>`:''}<ul>${r.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
}
function lifecycleMarkup(a) {
  const r=a.status==='stale'?null:a.result,b=a.input;
  if(!r)return '<p>当前核验未通过，不显示历史计算数值。请复核来源或重新计算。</p>';
  const activities=new Map(b.activities.map(x=>[x.activity_id,x]));
  return `<p>声明边界合计：<strong>${engineeringValue(r.boundary_total_kgco2e)} kgCO₂e</strong></p><p>评估期单位面积量：${engineeringValue(r.kgco2e_m2_over_study_period)} kgCO₂e/m² · ${engineeringValue(b.study_years)} 年；声明面积 ${engineeringValue(b.area_m2)} m²</p><p>功能单位：${esc(b.functional_unit)}；方法：${esc(b.method)}；地区：${esc(b.region)}</p><p>五阶段均已录入且计算完整：${r.all_five_stages_entered?'是，仍不证明清单无遗漏':'否'}。碳核证：未评估；已签发信用：—。</p><ul>${Object.entries(r.stages).map(([key,s])=>`<li>${esc(stages[key]||key)}：${s.included?(s.status==='calculated'?engineeringValue(s.kgco2e)+' kgCO₂e':'资料不完整 · —'):'明确排除 · 不计为零排放'}；${esc(s.reason)}</li>`).join('')}</ul>${r.rows.map(row=>{const x=activities.get(row.activity_id),f=x.factor;return `<details><summary>${esc(x.name)} · ${engineeringValue(row.kgco2e)} kgCO₂e</summary><p>活动量：${engineeringValue(x.quantity)} ${esc(x.unit)}；${x.period==='annual'?'年量':'整个评估期量'} × ${engineeringValue(row.period_multiplier)} → 因子计量数量 ${engineeringValue(row.quantity_in_factor_unit)} ${esc(f.denominator)}</p><p>排放因子：${engineeringValue(f.value)} kgCO₂e/${esc(f.denominator)}；排放量 = 活动量×单位换算×期间倍数×因子。</p><p>活动来源：${esc(x.source)}</p><p>因子来源：${esc(f.source)}；发布者：${esc(f.publisher)}；版本：${esc(f.version)}；年份：${engineeringValue(f.year)}；地区：${esc(f.region)}；方法：${esc(f.method)}</p></details>`;}).join('')}${r.missing.length?`<p>缺参：${r.missing.map(esc).join('、')}</p>`:''}<p>来源为用户声明，填写来源或计算完整不等于因子真实性或独立核证通过。</p><ul>${r.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
}
export function professionalArtifactMarkup(a) {
  if(a&&['engineering_review','schedule_review','operation_review'].includes(a.kind))return engineeringArtifactMarkup(a);
  if(!a || !['thermal_review','lifecycle_review'].includes(a.kind))return costArtifactMarkup(a);
  const thermal=a.kind==='thermal_review',path=thermal?'thermal':'lifecycle';
  return `<section class="agent-artifact" aria-label="${thermal?'已核验的热工构造结果':'已核验的阶段碳清单结果'}"><h3>${esc(a.name)}</h3><p><strong>${esc(statusText[a.status]||a.status)}</strong> · ${esc(a.scope)}</p>${thermal?thermalMarkup(a):lifecycleMarkup(a)}<p class="subtle">数值至多显示12位有效数字，不代表输入精度；完整原始值保留在同源记录中。</p><small class="mono">${esc(a.record_id)} · 核验时间 ${esc(a.checked_at)}</small><p><a href="/api/projects/${encodeURIComponent(a.project_id)}/${path}/${encodeURIComponent(a.record_id)}/report.html" target="_blank" rel="noopener">打开同源${thermal?'热工':'碳清单'}报告</a></p></section>`;
}

export function checkedDeliveryMarkup(answer) {
  if(!answer)return '';
  const checked=answer.checked_statements||[];
  const periods={steady_state:'稳态构造',study_period:'整个评估期',quote_date:'清单声明日期',static_load_case:'声明静力工况',elapsed_days:'声明原点的连续经过日',observed_window:'CSV观测窗口 · 非年量'};
  const section=checked.length?`<section aria-label="经过核验的专业说明"><h3>模型选择 · 当前记录核验</h3><p>以下字段已与当前记录逐项核对。自由问题的完整覆盖度及模型原始文字未获核验。</p>${checked.map(s=>`<h4>${esc(s.name)}</h4><dl>${s.facts.map(f=>`<dt>${esc(f.label)}</dt><dd>${f.period==='quote_date'?value(f.value):engineeringValue(f.value===null?null:Number(f.value))} ${esc(f.unit)} · ${esc(periods[f.period]||f.period)}${f.study_years!==null?' '+value(f.study_years)+' 年':''}${f.area_m2!==null?' · 面积分母 '+value(f.area_m2)+' m²':''}<small> 来源字段 ${esc(f.source_path)}</small></dd>`).join('')}</dl><small class="mono">${esc(s.record_id)}</small>`).join('')}</section>`:'';
  const limitationStates={stale:'来源或版本已失效',incomplete:'资料不完整',outside_model_screen:'超出模型适用范围',constraints_unresolved:'资源约束未解决',incomplete_progress:'进度情景不完整',insufficient_evidence:'证据不充分',events_detected:'检出规则事件'};
  const limits=answer.checked_limitations||[];
  const limitations=limits.length?`<section aria-label="当前记录限制说明"><h3>限制说明已核验</h3><p>核验的是当前限制；不改变记录状态，不代表工程结果有效，也不会恢复历史数值。</p>${limits.map(r=>`<article><h4>${esc(limitationStates[r.state]||r.state)}</h4><p>${esc(r.scope)}</p>${r.state==='stale'?`<p>历史数值不可交付。请先复核来源变化，再另行提交计算。</p>${staleReasonMarkup(r)}`:''}<small class="mono">${esc(r.record_id)}</small></article>`).join('')}</section>`:'';
  const kinds={thermal:'热工构造',lifecycle:'阶段碳清单',cost:'材料成本',engineering:'梁分析',schedule:'施工进度',operation:'设备规则核查'};
  const missing=answer.checked_missing||[];
  const absence=missing.length?`<section aria-label="当前记录缺失说明"><h3>记录可用性已核验 · 尚无所需结果</h3><p>以下是当前项目记录范围的检查，不代表工程计算完成，也不表示应用不支持该功能。</p>${missing.map(r=>`<article><h4>${esc(kinds[r.kind]||r.kind)}</h4><p>${r.scope==='entire_project_kind'?'完整项目目录中没有该类记录。':'指定编号在当前项目中不可用；不能据此判断其他项目是否存在该记录。'}</p>${r.record_id?`<small class="mono">${esc(r.record_id)}</small>`:''}<p>核查时间：${esc(r.checked_at)}</p></article>`).join('')}<p>请核对项目与编号；需要计算时提交完整参数和本次授权。失败后不自动重试写操作，缺失结果不记为零。</p></section>`:'';
  return simulationArtifactMarkup(answer)+section+limitations+absence+(answer.artifacts||[]).map(professionalArtifactMarkup).join('');
}
