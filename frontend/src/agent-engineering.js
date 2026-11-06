import {escape as esc} from './api.js';
const number=x=>esc(x==null?'—':typeof x==='number'&&Number.isFinite(x)?Number(x.toPrecision(12)):x);

const kinds={engineering_review:['梁分析','beam-analyses'],schedule_review:['施工进度','schedules'],operation_review:['设备规则','operations']};
const states={calculated:'限定计算完整',outside_model_screen:'超出模型适用性筛查范围',incomplete:'缺少参数',stale:'来源或版本已失效',constraints_unresolved:'资源约束未解决',incomplete_progress:'进度情景不完整',events_detected:'检出规则事件',insufficient_evidence:'数据不充分',no_rule_event:'未检出规则事件 · 不代表健康'};

export function engineeringArtifactMarkup(a) {
  if(!a || !kinds[a.kind])return '';
  const [title,route]=kinds[a.kind],r=a.status==='stale'?null:a.result;
  let content='<p>未取得当前结果；不能复用历史数值。</p>';
  if(r&&a.kind==='engineering_review') {
    const m=r.metrics;
    content=a.status==='outside_model_screen'?'<p>数值仅供排查模型假设，不在本交付中作为工程结果显示。</p>':m?`<dl>${[
      ['最大绝对弯矩',m.max_abs_moment_nm,'N·m'],['最大绝对剪力',m.max_abs_shear_n,'N'],['最大向下挠度',m.max_deflection_m,'m'],['线弹性最大弯曲应力（非强度验算）',m.max_elastic_bending_stress_pa,'Pa']
    ].map(([label,value,unit])=>`<dt>${label}</dt><dd>${number(value)} ${unit}</dd>`).join('')}</dl>`:'<p>缺参：'+(r.missing||[]).map(esc).join('、')+'</p>';
    content+=(r.model_screening||[]).map(x=>`<p>${esc(x)}</p>`).join('');
  } else if(r&&a.kind==='schedule_review') {
    const p=r.planned,f=r.forecast;
    content=`<p>时间原点：${esc(a.input.time_origin)}；按连续经过日计算，不自动扣除休息日。</p><p>计划工期：${esc(p?.duration_days??'—')} day；关键任务集合（并非唯一串行路径）：${p? p.critical_tasks.map(esc).join('、'):'—'}</p><p>资源核查：${esc(p?.resources?.status??'未评估')}；未自动调平。</p>${f?`<p>截至第 ${esc(f.as_of_day)} 天的显式情景：完工日 ${esc(f.finish_day??'—')}；相对计划偏差 ${esc(f.finish_variance_days??'—')} day。情景状态：${esc(f.status)}</p>`:'<p>未提交进度情景，不能预测实际完工日。</p>'}`;
  } else if(r&&a.kind==='operation_review') {
    content=`<p>数据性质：${esc(a.input.data_nature)}；观测窗口 ${esc(r.quality.first_time)} 至 ${esc(r.quality.last_time)}；时钟 ${esc(a.input.clock_basis)}。</p><p>样本 ${r.quality.sample_count}；缺失或无效单元 ${r.quality.cell_issue_count}；采样缺口 ${r.quality.gap_count}。</p><ul>${r.rules.map(x=>`<li>${esc(x.name)}：规则事件 ${x.event_count}；未知样本 ${x.unknown_samples}；状态 ${esc(states[x.state]||x.state)}${x.events_truncated?'；事件详情已截断，须核对原始CSV':''}</li>`).join('')}</ul><p>不同规则可能覆盖同一段时间；不能相加当作独立故障数，不下发设备控制命令。</p>`;
  }
  return `<section class="agent-artifact" aria-label="${title}核查结果"><h3>${esc(a.name)} · ${title}</h3><p><strong>${esc(states[a.status]||a.status)}</strong>。${esc(a.scope)}</p><p>来源为用户声明，计算核对不代表来源独立核证。</p>${content}${r?`<details><summary>方法边界与解释</summary><ul>${(r.limitations||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}<small class="mono">${esc(a.record_id)}</small><p><a href="/api/projects/${encodeURIComponent(a.project_id)}/${route}/${encodeURIComponent(a.record_id)}/report.html" target="_blank" rel="noopener">打开同源${title}报告</a></p></section>`;
}
