import {request,post,escape as esc,number as fmt} from './api.js';
export const maintenanceActions={open:['triage'],triaged:['record_work'],work_recorded:['record_work','recheck'],recheck_failed:['record_work','recheck'],rechecked:['recheck','close'],closed_under_declared_rule:['reopen']};
const gapLabels={observation_window_too_short:'观察时长不足',source_quality_or_cadence:'原始数据质量或采样间隔不符',unknown_or_gated_samples:'存在未知或工况排除样本',insufficient_evaluated_coverage:'有效评估覆盖不足'};
const labels={open:'待核查',triaged:'已核查',work_recorded:'已记录处置',recheck_failed:'复验未通过',rechecked:'限定规则复验通过',closed_under_declared_rule:'人工结案（限定规则）',stale:'来源已变更',triage:'记录核查',record_work:'记录人工处置',recheck:'用新数据复验',close:'人工审核结案',reopen:'重新打开'};
const input=(name,label,attrs='required')=>`<label>${label}<input name="${name}" ${attrs}></label>`;
export function maintenanceResult(r){
 const result=r.status==='stale'?null:r.recheck;
 return `<h3>${esc(r.input.name)} · ${esc(labels[r.status]||r.status)}</h3><p>设备：${esc(r.equipment)} · 资料性质：${esc({measured:'用户声明实测，未独立核验',simulation:'仿真数据',synthetic:'人工合成数据'}[r.data_nature]||r.data_nature)} · 版本 ${r.revision}</p><p>处置责任人是人工声明，实际提交账号另行记录。此流程不证明设备健康、根因确诊或维修认证。</p>${r.status==='stale'?'<p>来源已变更，当前复验结论已撤下。历史保留，需重新审核后建立新工单。</p>':result?`<p>复验：${esc({no_violation_in_observed_window:'本观测窗口未发现规则越限',rule_violation_remains:'仍存在规则越限',inconclusive:'数据或观察时长不足'}[result.outcome])}；观察 ${fmt(result.observed_seconds)} 秒，要求至少 ${fmt(result.required_seconds)} 秒。</p><p>缺口：${result.gaps.map(x=>esc(gapLabels[x]||x)).join('、')||'本规则检查未发现覆盖缺口'}</p>`:'<p>尚无当前复验结果。</p>'}<details><summary>历史处置记录（不作为当前复验结论）</summary><pre>${esc(JSON.stringify(r.actions,null,2))}</pre></details>`;
}
export function readMaintenanceAction(data,revision){
 const action=data.get('action'),body={expected_revision:revision,action,note:data.get('note'),responsible_person:data.get('responsible_person'),evidence_ids:data.getAll('evidence_ids')};
 if(action==='record_work')body.work_completed_at=data.get('work_completed_at');
 if(action==='recheck')body.after_operation_id=data.get('after_operation_id');
 if(action==='close')body.same_equipment_and_conditions=data.get('same_equipment_and_conditions')==='on';
 return body;
}
export async function maintenanceWorkspace(state,host,action){
 const base='/projects/'+state.project.project_id;let events=[],operations=[],evidence=[],selected=null,serial=0;
 host.innerHTML=`<h2>维修处置与复验</h2><p>先保存带明确时区的异常分析，再从具体事件建单。新分析不能靠换记录编号、放宽阈值或忽略缺测证明恢复。</p><button type="button" data-refresh>刷新分析与工单</button><details><summary>从异常事件建立工单</summary><form data-open><label>来源事件<select name="event" required></select></label><div class="form-grid">${input('name','工单名称')}${input('responsible_person','声明责任人')}${input('minimum_observation_seconds','维修后最短观察时间 / 秒','type="number" step="any" min="0.001" max="604800" required')}${input('observation_basis','观察时长与适用工况依据（创建后冻结）','required minlength="20" maxlength="2000"')}</div><button type="submit">建立工单</button></form></details><div data-orders></div><div data-order-view aria-live="polite"></div>`;
 const create=host.querySelector('[data-open]');
 async function refresh(){
  const values=await Promise.all([request(base+'/operations'),request(base+'/evidence'),request(base+'/maintenance-orders')]);if(!host.isConnected)return;
  [operations,evidence]=values;events=[];
  for(const op of operations)if(op.result&&op.status!=='stale'&&op.input.clock_basis==='offset_aware')for(const rule of op.result.rules)rule.events.forEach((event,index)=>events.push({operation_id:op.operation_id,rule_id:rule.rule_id,event_index:index,label:`${op.input.name} / ${rule.name} / 行${event.first_line}–${event.last_line}`}));
  create.elements.event.innerHTML='<option value="">选择一个当前异常事件</option>'+events.map((e,i)=>`<option value="${i}">${esc(e.label)}</option>`).join('');
  host.querySelector('[data-orders]').innerHTML=values[2].map(r=>`<button type="button" data-order="${esc(r.maintenance_id)}">${esc(r.input.name)} · ${esc(labels[r.status]||r.status)}</button>`).join('')||'<p>暂无工单。</p>';
  host.querySelectorAll('[data-order]').forEach(b=>b.onclick=()=>action(()=>load(b.dataset.order),b));
 }
 async function load(id){const token=++serial;const r=await request(base+'/maintenance-orders/'+id);if(!host.isConnected||token!==serial)return;selected=r;render();}
 function render(){
  const r=selected,out=host.querySelector('[data-order-view]');if(!r)return;
  const choices=r.status==='stale'?[]:maintenanceActions[r.state]||[];
  const usedFiles=new Set((r.operation_snapshots||[]).map(s=>operations.find(o=>o.operation_id===s.operation_id)?.file_snapshot?.hash).filter(Boolean));
  out.innerHTML=maintenanceResult(r)+`<p><a target="_blank" rel="noopener" href="/api${base}/maintenance-orders/${r.maintenance_id}/report.html">同源报告 / 打印</a> · <a target="_blank" rel="noopener" href="/api${base}/maintenance-orders/${r.maintenance_id}">完整 JSON</a></p>`;
  if(!choices.length)return;
  out.insertAdjacentHTML('beforeend',`<form data-action><label>下一动作<select name="action">${choices.map(k=>`<option value="${k}">${labels[k]}</option>`).join('')}</select></label>${input('responsible_person','声明责任人')}<label>核查、处置或审核记录<textarea name="note" minlength="20" maxlength="4000" required></textarea></label><fieldset><legend>本次依据（处置及结案必须选择）</legend>${evidence.filter(e=>e.review_state!=='rejected').map(e=>`<label class="check-option"><input name="evidence_ids" value="${esc(e.evidence_id)}" type="checkbox">${esc(e.name)} · v${e.revision}</label>`).join('')||'<p>请先在项目证据中登记处置或设备映射依据。</p>'}</fieldset><div data-work>${input('work_completed_at','处置完成时间，含时区（例如 2026-01-01T08:30:00+08:00）')}</div><div data-recheck><label>新的运维分析<select name="after_operation_id" required><option value="">请选择新数据的分析记录</option>${operations.filter(o=>o.result&&o.status!=='stale'&&o.operation_id!==r.input.operation_id&&!usedFiles.has(o.file_snapshot?.hash)).map(o=>`<option value="${o.operation_id}">${esc(o.input.name)} · ${esc(o.input.equipment)} · ${esc(o.input.data_nature)}</option>`).join('')}</select></label><p>每轮必须使用新的原件；新的处置时间须晚于上一轮复验结束。服务器同时核对规则、设备、资料性质和有效覆盖。</p></div><div data-close><label class="check-option"><input name="same_equipment_and_conditions" type="checkbox" required>已依据所选证据复核为同一声明设备及可比工况；此确认不代表根因或设备健康认证。</label></div><button type="submit">保存本次动作</button></form>`);
  const form=out.querySelector('[data-action]');
  const toggle=()=>{for(const [selector,type] of [['[data-work]','record_work'],['[data-recheck]','recheck'],['[data-close]','close']]){const el=form.querySelector(selector),show=form.elements.action.value===type;el.hidden=!show;el.querySelectorAll('input,select').forEach(n=>n.disabled=!show);}};
  form.elements.action.onchange=toggle;toggle();
  form.onsubmit=e=>{e.preventDefault();const id=r.maintenance_id,token=serial;const body=readMaintenanceAction(new FormData(form),r.revision);action(async()=>{await post(base+'/maintenance-orders/'+id+'/actions',body);await refresh();if(serial===token)await load(id);},e.submitter);};
 }
 create.onsubmit=e=>{e.preventDefault();const data=new FormData(create),chosen=events[Number(data.get('event'))];if(data.get('event')===''||!chosen)return;const {label,...source}=chosen;void label;action(async()=>{const r=await post(base+'/maintenance-orders',{...source,name:data.get('name'),responsible_person:data.get('responsible_person'),minimum_observation_seconds:Number(data.get('minimum_observation_seconds')),observation_basis:data.get('observation_basis')});await refresh();await load(r.maintenance_id);},e.submitter);};
 host.querySelector('[data-refresh]').onclick=e=>action(async()=>{await refresh();if(selected)await load(selected.maintenance_id);},e.currentTarget);
 await refresh();return refresh;
}
