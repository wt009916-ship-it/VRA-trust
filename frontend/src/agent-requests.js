import {escape as esc, request} from './api.js';

export const readKinds={thermal:'热工构造',lifecycle:'阶段碳清单',cost:'材料成本',engineering:'梁分析',schedule:'施工进度',operation:'设备运行',scenario:'材料两方案对照',enduse:'设备用途能耗账',utility:'账单模拟比较'};
const routes={thermal:'thermal',lifecycle:'lifecycle',cost:'material-costs',engineering:'beam-analyses',schedule:'schedules',operation:'operations',scenario:'material-scenarios',enduse:'end-use-ledgers',utility:'utility-comparisons'};
export function readRecordLabel(record,kind){
 if(['enduse','utility'].includes(kind))return record.name+' · 选中后核验，目录不认证数值';
 return kind==='scenario'?(record.names||[]).join(' / ')+' · 状态将在执行时核验':record.input.name+' · '+record.status;
}
export function readRecordPage(value,kind){
 if(['enduse','utility'].includes(kind)){if(!Array.isArray(value?.records)||!(value.next_before===null||Number.isSafeInteger(value.next_before)&&value.next_before>0))throw Error('记录目录响应无效');return {records:value.records,next:value.next_before};}
 if(!Array.isArray(value))throw Error('记录目录响应无效');return {records:value,next:null};
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
    if(row.output_contract){
      const c=row.output_contract;
      if(!Array.isArray(c.fact_keys)||!Array.isArray(c.explanation_topics)||c.fact_keys.length>12||c.explanation_topics.length>6||!c.fact_keys.length&&!c.explanation_topics.length||new Set(c.fact_keys).size!==c.fact_keys.length||new Set(c.explanation_topics).size!==c.explanation_topics.length)throw Error('请至少选择一项指标或解释，指标最多12项且不能重复。');
      if(r.purpose==='availability'&&(c.fact_keys.length||c.explanation_topics.some(t=>!['history','status'].includes(t))))throw Error('可用性检查不能要求数值。');
      r.output_contract={fact_keys:[...c.fact_keys],explanation_topics:[...c.explanation_topics]};
    }
    keys.add(r.request_key);scopes.add(scope);return r;
  });
}

const topicLabels={meaning:'指标含义',area:'面积分母',period:'期间与年份',scope:'适用范围',status:'来源状态',history:'记录历史边界'};
export function explicitOutputMarkup(entry,purpose) {
 const topics=purpose==='availability'?['history','status']:entry.topics;
 return `<p>只锁定勾选的指标与解释主题；自由问题中的其他要求仍需核对。最多12项指标。</p>${purpose==='results'?`<label>数值指标<select data-output-facts multiple size="6">${entry.facts.map(f=>`<option value="${esc(f.key)}">${esc(f.label)}</option>`).join('')}</select></label>`:''}<fieldset><legend>解释主题</legend>${topics.map(t=>`<label><input type="checkbox" data-output-topic value="${esc(t)}">${esc(topicLabels[t]||t)}</label>`).join('')}</fieldset>`;
}

export function collectReadRequests(host) {
  return [...host.querySelectorAll('[data-read-scope]')].map(row=>({request_key:row.dataset.readScope,
    kind:row.querySelector('[data-read-kind]').value,purpose:row.querySelector('[data-read-purpose]').value,
    record_id:row.querySelector('[data-read-id]').value,
    ...(row.querySelector('[data-explicit-output]')?.checked?{output_contract:{
      fact_keys:[...(row.querySelector('[data-output-facts]')?.selectedOptions||[])].map(o=>o.value),
      explanation_topics:[...row.querySelectorAll('[data-output-topic]:checked')].map(o=>o.value)}}:{})}));
}

export function bindReadRequests(host,pid,action) {
  let sequence=0,catalogPromise=null;
  const rows=host.querySelector('[data-read-rows]'),add=host.querySelector('[data-add-read]');
  add.onclick=()=>{
    if(rows.children.length>=6)return;
    sequence++;
    rows.insertAdjacentHTML('beforeend',`<fieldset data-read-scope="read_${sequence}"><legend>读取目标 ${sequence}</legend><div class="read-scope-grid"><label>专业<select data-read-kind>${Object.entries(readKinds).map(([k,label])=>`<option value="${k}">${label}</option>`).join('')}</select></label><label>目的<select data-read-purpose><option value="availability">检查记录是否存在</option><option value="results">读取指定记录的结果</option></select></label></div><label>指定编号<input data-read-id maxlength="50" spellcheck="false" placeholder="留空表示该专业完整项目目录"></label><div class="read-scope-grid"><button type="button" data-load-records>加载已有记录</button><label>从已有记录选填<select data-existing-record><option value="">先加载记录，或手动输入编号</option></select></label></div><button type="button" data-read-more hidden>更早记录</button><p data-read-note role="status">检查可用性可以留空编号；读取结果必须指定编号。</p><label><input type="checkbox" data-explicit-output>锁定本项指标与解释</label><div data-output-controls hidden></div><button type="button" data-remove-read>移除此目标</button></fieldset>`);
    const row=rows.lastElementChild,kind=row.querySelector('[data-read-kind]'),purpose=row.querySelector('[data-read-purpose]'),id=row.querySelector('[data-read-id]'),existing=row.querySelector('[data-existing-record]'),note=row.querySelector('[data-read-note]');
    const explicit=row.querySelector('[data-explicit-output]'),controls=row.querySelector('[data-output-controls]');
    let outputGeneration=0;
    const resetOutput=()=>{outputGeneration++;explicit.checked=false;controls.hidden=true;controls.innerHTML='';};
    explicit.onchange=e=>{
      const stamp=++outputGeneration,selected=kind.value,selectedPurpose=purpose.value;
      controls.innerHTML='';controls.hidden=!explicit.checked;
      if(!explicit.checked)return;
      controls.textContent='正在加载可选指标…';
      action(async()=>{
        catalogPromise ||= request('/agent/status').then(r=>r.output_catalog).catch(error=>{catalogPromise=null;throw error;});
        let catalog;
        try{catalog=await catalogPromise;}
        catch(error){if(row.isConnected&&stamp===outputGeneration){explicit.checked=false;controls.textContent='指标目录加载失败，未启用锁定；请重新勾选。';}throw error;}
        if(!row.isConnected||stamp!==outputGeneration||!explicit.checked)return;
        controls.innerHTML=explicitOutputMarkup(catalog[selected],selectedPurpose);
      },e.currentTarget);
    };
    let generation=0,cursor=null;const more=row.querySelector('[data-read-more]');
    kind.onchange=()=>{resetOutput();generation++;cursor=null;more.hidden=true;id.value='';existing.innerHTML='<option value="">专业已改变，请重新加载或输入编号</option>';};
    purpose.onchange=()=>{resetOutput();id.required=purpose.value==='results';id.placeholder=id.required?'必须指定记录编号':'留空表示该专业完整项目目录';};
    existing.onchange=()=>{if(existing.value)id.value=existing.value;};
    const loadPage=(before,e)=>action(async()=>{
      const selected=kind.value,stamp=++generation;
      note.textContent='正在加载当前项目记录…';
      let records;
      try {records=await request('/projects/'+encodeURIComponent(pid)+'/'+routes[selected]+(before===null?'':'?before='+before));}
      catch(error) {
        if(row.isConnected&&generation===stamp&&kind.value===selected)note.textContent='记录加载失败，请重试或核对原编号后手动填写。';
        throw error;
      }
      if(!row.isConnected||generation!==stamp||kind.value!==selected)return;
      const page=readRecordPage(records,selected);records=page.records;cursor=page.next;more.hidden=cursor===null;
      existing.innerHTML='<option value="">请选择；不会自动选择最新记录</option>'+records.map(r=>`<option value="${esc(r[selected+'_id'])}">${esc(readRecordLabel(r,selected))} · ${esc(r[selected+'_id'])}</option>`).join('');
      note.textContent=records.length?'仅本页名称，选择只填写编号，执行时核验来源；可翻到更早记录。':'本页没有记录，不能推断整个项目从未计算；可手动核对原编号。';
    },e.currentTarget);
    row.querySelector('[data-load-records]').onclick=e=>loadPage(null,e);more.onclick=e=>{if(cursor!==null)loadPage(cursor,e);};
    row.querySelector('[data-remove-read]').onclick=()=>{outputGeneration++;generation++;row.remove();add.disabled=false;};
    add.disabled=rows.children.length>=6;kind.focus();
  };
}

export function readRequestProgressMarkup(task) {
  const rows=task.read_request_progress||task.answer?.read_request_progress||[];
  if(!rows.length)return outputContractMarkup(task);
  const states={needs_clarification:'等待澄清 · 尚未交付',source_review_verified:'状态与口径已复核 · 未交付数值',fields_unavailable:'所问字段含不可计算项',required_facts_missing:'尚缺所问指标',output_plan_missing:'尚未形成输出计划',unfulfilled:'尚未交付',delivery_not_currently_verified:'交付目前未通过核验',availability_verified:'可用性已核验',result_verified:'所选结果已核验',limitation_verified:'当前限制已核验',record_unavailable:'指定记录不可用'};
  const rowState=r=>r.state==='result_verified'&&(task.answer?.artifacts||[]).some(a=>a.record_id===r.record_id&&!a.verified)
    ?'所列字段已核对 · 整体记录仍受限':states[r.state]||r.state;
  const available=task.answer?.checked_availability||[];
  const termination=task.termination||task.answer?.termination;
  const stopped=termination?.reason==='response_budget_exhausted'?'<p role="status">已到模型轮次上限。已提交内容仍按当前来源核验，未交付的目标继续标示；流程结束不等于全部任务完成。</p>':'';
  return outputContractMarkup(task)+`<section aria-label="声明读取目标进度"><h3>本次明确读取范围</h3>${stopped}<p>逐项检查声明范围，清单外问题的完整覆盖未获核验。记录存在不等于结果有效，缺失不记为零。</p>${rows.map(r=>`<article><h4>${esc(readKinds[r.kind]||r.kind)} · ${r.purpose==='availability'?'可用性':'指定结果'}</h4><p><strong>${esc(rowState(r))}</strong> · ${esc(r.request_key)}</p><small class="mono">${esc(r.record_id||'该专业完整项目目录')}</small>${available.filter(a=>a.request_key===r.request_key).map(a=>`<p>${a.state==='records_present'?'声明范围内存在记录；未据此认定工程数值有效。':'声明范围内没有可用记录；不推断其他项目或计算历史。'}</p>`).join('')}</article>`).join('')}</section>`;
}

const factLabels={total_resistance_m2k_w:'总热阻 R',layer_resistance_m2k_w:'材料层热阻',u_w_m2k:'传热系数 U',
  boundary_total_kgco2e:'声明边界碳总量',kgco2e_m2_over_study_period:'评估期单位面积碳排',material_total:'材料成本合计'};
export function outputContractMarkup(task) {
  const answer=task.answer||{},plan=answer.output_plan||task.output_plan;
  if(!task.infer_outputs&&!plan)return '';
  if(!plan)return '<section aria-label="任务产物核验"><h3>任务产物</h3><p>尚未形成指标与解释计划，不能认定已完整回答问题。</p></section>';
  const states={needs_clarification:'等待澄清 · 任务未完成',fulfilled:'计划内产物已交付',source_limited:'已说明来源限制，数值未完成',incomplete:'仍有产物未交付'};
  const invalid=answer.output_contract_coverage==='contract_changed';
  const outputs=invalid?[]:(answer.requested_outputs||[]);
  return `<section aria-label="任务产物核验"><h3>指标与解释</h3><p>每项注明要求来自用户勾选或模型解析。交付所选指标不等于完整回答自由问题；解释由应用依据当前核验来源生成。</p>${invalid?'<p role="status">解释契约已变化，历史解释已撤下，请重新核验。</p>':''}${plan.items.map(item=>{
    const out=outputs.find(o=>o.request_key===item.request_key);
    const clarification=invalid?null:(answer.clarification_requests||[]).find(q=>q.request_key===item.request_key);
    const review=invalid?null:(answer.checked_reviews||[]).find(r=>r.record_id===out?.record_id);
    const withdrawn=(answer.review_failures||[]).find(r=>r.record_id===out?.record_id);
    const purpose=(task.read_requests||[]).find(r=>r.request_key===item.request_key)?.purpose;
    const emptyLabel=item.clarification_question?'等待澄清':purpose==='availability'?'记录可用性':'仅说明口径或状态，不交付数值';
    return `<article><h4>${esc(item.request_key)} · ${esc(states[out?.state]||'待交付')}</h4><p>${item.requirement_origin==='user_selected'?'要求来自用户勾选，模型不能改换；自由问题的其他要求尚未核验。':'要求由模型从原问题解析，需核对是否符合原问题。'}</p><blockquote>${esc(item.question_excerpt)}</blockquote><p>所选指标：${esc(item.fact_keys.map(k=>factLabels[k]||k).join('、')||emptyLabel)}</p>${out?.missing_fact_keys?.length?`<p role="status">尚缺指标：${esc(out.missing_fact_keys.map(k=>factLabels[k]||k).join('、'))}</p>`:''}${clarification?`<p role="status"><strong>请补充确认：</strong>${esc(clarification.question)}</p><p>${esc(clarification.notice)}</p><p>在输入框补充说明后重新提交；本次未执行替代计算。</p>`:''}${withdrawn?`<p role="status">${esc(withdrawn.notice)}</p>`:''}${(out?.explanations||[]).map(e=>`<p>${esc(e.text)}</p>`).join('')}${review?`<p class="subtle">非数值来源复核 · ${esc(review.checked_at)}</p><small class="mono">${esc(review.record_id)} · ${esc(review.record_hash)}</small>`:''}</article>`;
  }).join('')}</section>`;
}
