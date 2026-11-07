import {escape as esc, request} from './api.js';

export const readKinds={thermal:'热工构造',lifecycle:'阶段碳清单',cost:'材料成本',engineering:'梁分析',schedule:'施工进度',operation:'设备运行',scenario:'材料两方案对照'};
const routes={thermal:'thermal',lifecycle:'lifecycle',cost:'material-costs',engineering:'beam-analyses',schedule:'schedules',operation:'operations',scenario:'material-scenarios'};
export function readRecordLabel(record,kind){
 return kind==='scenario'?(record.names||[]).join(' / ')+' · 状态将在执行时核验':record.input.name+' · '+record.status;
}
export function readRequestMarkup() {
  return `<details class="agent-read-input"><summary>明确读取范围 · 可选</summary><p>逐项选择本轮要检查的记录，模型不能换成其他编号。检查可用性仅说明记录是否存在；读取结果需指定编号，仍要核验当前来源。最多6项，其中结果读取最多3项。</p><div data-read-rows></div><button type="button" data-add-read>＋ 添加读取目标</button><p>选择AI模式与自由提问，并关闭“允许计算”。这份清单不授权计算，也不证明清单外的问题已处理。</p></details>`;
}

export function validateReadRequests(rows,{mode,allowCompute,objective,calculationPlans=[]}) {
  if(!rows.length)return [];
  if(rows.length>6||rows.filter(r=>r.purpose==='results').length>3)throw Error('最多6项读取目标，其中结果读取最多3项。');
  if(mode==='local'||allowCompute||objective!=='open_ended'||calculationPlans.length)throw Error('明确读取范围须选择AI模式、自由提问并关闭允许计算；不能同时提交计算计划。');
  const keys=new Set(),scopes=new Set();
  return rows.map(row=>{
    const r={request_key:row.request_key,kind:row.kind,purpose:row.purpose,record_id:row.record_id?.trim()||null};
    if(!/^[A-Za-z0-9_-]{1,40}$/.test(r.request_key)||!Object.hasOwn(readKinds,r.kind)||!['availability','results'].includes(r.purpose))throw Error('读取目标的编号、专业或目的无效。');
    if(r.record_id&&!new RegExp('^'+r.kind+'_[a-f0-9]{32}$').test(r.record_id))throw Error('记录编号格式或专业不匹配，请核对原编号。');
    if(r.purpose==='results'&&!r.record_id)throw Error('读取结果必须指定记录编号，不会自动替换为最新记录。');
    const scope=JSON.stringify([r.kind,r.purpose,r.record_id]);
    if(keys.has(r.request_key)||scopes.has(scope))throw Error('读取目标重复，请合并相同目的与范围。');
    keys.add(r.request_key);scopes.add(scope);return r;
  });
}

export function collectReadRequests(host) {
  return [...host.querySelectorAll('[data-read-scope]')].map(row=>({request_key:row.dataset.readScope,
    kind:row.querySelector('[data-read-kind]').value,purpose:row.querySelector('[data-read-purpose]').value,
    record_id:row.querySelector('[data-read-id]').value}));
}

export function bindReadRequests(host,pid,action) {
  let sequence=0;
  const rows=host.querySelector('[data-read-rows]'),add=host.querySelector('[data-add-read]');
  add.onclick=()=>{
    if(rows.children.length>=6)return;
    sequence++;
    rows.insertAdjacentHTML('beforeend',`<fieldset data-read-scope="read_${sequence}"><legend>读取目标 ${sequence}</legend><div class="read-scope-grid"><label>专业<select data-read-kind>${Object.entries(readKinds).map(([k,label])=>`<option value="${k}">${label}</option>`).join('')}</select></label><label>目的<select data-read-purpose><option value="availability">检查记录是否存在</option><option value="results">读取指定记录的结果</option></select></label></div><label>指定编号<input data-read-id maxlength="50" spellcheck="false" placeholder="留空表示该专业完整项目目录"></label><div class="read-scope-grid"><button type="button" data-load-records>加载已有记录</button><label>从已有记录选填<select data-existing-record><option value="">先加载记录，或手动输入编号</option></select></label></div><p data-read-note role="status">检查可用性可以留空编号；读取结果必须指定编号。</p><button type="button" data-remove-read>移除此目标</button></fieldset>`);
    const row=rows.lastElementChild,kind=row.querySelector('[data-read-kind]'),purpose=row.querySelector('[data-read-purpose]'),id=row.querySelector('[data-read-id]'),existing=row.querySelector('[data-existing-record]'),note=row.querySelector('[data-read-note]');
    let generation=0;
    kind.onchange=()=>{generation++;id.value='';existing.innerHTML='<option value="">专业已改变，请重新加载或输入编号</option>';};
    purpose.onchange=()=>{id.required=purpose.value==='results';id.placeholder=id.required?'必须指定记录编号':'留空表示该专业完整项目目录';};
    existing.onchange=()=>{if(existing.value)id.value=existing.value;};
    row.querySelector('[data-load-records]').onclick=e=>action(async()=>{
      const selected=kind.value,stamp=++generation;
      note.textContent='正在加载当前项目记录…';
      let records;
      try {records=await request('/projects/'+encodeURIComponent(pid)+'/'+routes[selected]);}
      catch(error) {
        if(row.isConnected&&generation===stamp&&kind.value===selected)note.textContent='记录加载失败，请重试或核对原编号后手动填写。';
        throw error;
      }
      if(!row.isConnected||generation!==stamp||kind.value!==selected)return;
      existing.innerHTML='<option value="">请选择；不会自动选择最新记录</option>'+records.map(r=>`<option value="${esc(r[selected+'_id'])}">${esc(readRecordLabel(r,selected))} · ${esc(r[selected+'_id'])}</option>`).join('');
      note.textContent=records.length?'选择记录只填写编号，最终仍按任务执行时的当前来源核验。':'当前列表没有记录；可以按原编号核验缺失，不会新建计算。';
    },e.currentTarget);
    row.querySelector('[data-remove-read]').onclick=()=>{generation++;row.remove();add.disabled=false;};
    add.disabled=rows.children.length>=6;kind.focus();
  };
}

export function readRequestProgressMarkup(task) {
  const rows=task.read_request_progress||task.answer?.read_request_progress||[];
  if(!rows.length)return outputContractMarkup(task);
  const states={fields_unavailable:'所问字段含不可计算项',required_facts_missing:'尚缺所问指标',output_plan_missing:'尚未形成输出计划',unfulfilled:'尚未交付',delivery_not_currently_verified:'交付目前未通过核验',availability_verified:'可用性已核验',result_verified:'所选结果已核验',limitation_verified:'当前限制已核验',record_unavailable:'指定记录不可用'};
  const available=task.answer?.checked_availability||[];
  const termination=task.termination||task.answer?.termination;
  const stopped=termination?.reason==='response_budget_exhausted'?'<p role="status">已到模型轮次上限。已提交内容仍按当前来源核验，未交付的目标继续标示；流程结束不等于全部任务完成。</p>':'';
  return outputContractMarkup(task)+`<section aria-label="声明读取目标进度"><h3>本次明确读取范围</h3>${stopped}<p>逐项检查声明范围，清单外问题的完整覆盖未获核验。记录存在不等于结果有效，缺失不记为零。</p>${rows.map(r=>`<article><h4>${esc(readKinds[r.kind]||r.kind)} · ${r.purpose==='availability'?'可用性':'指定结果'}</h4><p><strong>${esc(states[r.state]||r.state)}</strong> · ${esc(r.request_key)}</p><small class="mono">${esc(r.record_id||'该专业完整项目目录')}</small>${available.filter(a=>a.request_key===r.request_key).map(a=>`<p>${a.state==='records_present'?'声明范围内存在记录；未据此认定工程数值有效。':'声明范围内没有可用记录；不推断其他项目或计算历史。'}</p>`).join('')}</article>`).join('')}</section>`;
}

const factLabels={total_resistance_m2k_w:'总热阻 R',layer_resistance_m2k_w:'材料层热阻',u_w_m2k:'传热系数 U',
  boundary_total_kgco2e:'声明边界碳总量',kgco2e_m2_over_study_period:'评估期单位面积碳排',material_total:'材料成本合计'};
export function outputContractMarkup(task) {
  const answer=task.answer||{},plan=answer.output_plan||task.output_plan;
  if(!task.infer_outputs&&!plan)return '';
  if(!plan)return '<section aria-label="任务产物核验"><h3>任务产物</h3><p>尚未形成指标与解释计划，不能认定已完整回答问题。</p></section>';
  const states={fulfilled:'计划内产物已交付',source_limited:'已说明来源限制，数值未完成',incomplete:'仍有产物未交付'};
  const invalid=answer.output_contract_coverage==='contract_changed';
  const outputs=invalid?[]:(answer.requested_outputs||[]);
  return `<section aria-label="任务产物核验"><h3>指标与解释</h3><p>以下要求由模型从原问题解析，请核对是否准确。计划完成不等于已证明完整理解问题；解释由应用依据当前核验来源生成。</p>${invalid?'<p role="status">解释契约已变化，历史解释已撤下，请重新核验。</p>':''}${plan.items.map(item=>{
    const out=outputs.find(o=>o.request_key===item.request_key);
    return `<article><h4>${esc(item.request_key)} · ${esc(states[out?.state]||'待交付')}</h4><blockquote>${esc(item.question_excerpt)}</blockquote><p>所选指标：${esc(item.fact_keys.map(k=>factLabels[k]||k).join('、')||'记录可用性')}</p>${out?.missing_fact_keys?.length?`<p role="status">尚缺指标：${esc(out.missing_fact_keys.map(k=>factLabels[k]||k).join('、'))}</p>`:''}${(out?.explanations||[]).map(e=>`<p>${esc(e.text)}</p>`).join('')}</article>`;
  }).join('')}</section>`;
}
