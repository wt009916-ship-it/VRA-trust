import {escape as esc,post} from './api.js';

const reasons={resource_demands_not_confirmed:'尚未确认全部资源占用',progress_present_requires_separate_plan_snapshot:'含现场进度，请另建仅含基准计划的快照',no_declared_resources:'未声明资源容量',single_task_exceeds_capacity:'单个工序占用已超过容量',execution_budget_exhausted:'本次计算达到预算，未生成可行方案'};

export function levelingMarkup(record){
  if(record.calculation_type!=='resource_leveling')return '';
  const r=record.status==='stale'?null:record.result?.leveled,p=r?.schedule;
  if(!p)return `<section class="schedule-section"><h3>资源受限方案待补证</h3><p>${record.status==='stale'?'来源或版本已变化，已撤下历史排程数值。':(r?.reasons||[]).map(x=>esc(reasons[x]||x)).join('；')}</p></section>`;
  return `<section class="schedule-section"><h3>满足声明容量的排程方案</h3><p>完成日 <strong>${esc(p.duration_days)}</strong>；原CPM ${esc(p.cpm_duration_days)} 日；相对CPM延后 <strong>${esc(p.delay_vs_cpm_days)}</strong> 日。均按连续经过日计算。</p><p>数学下界 ${esc(r.lower_bound.days_floor_6dp)} 日（显示值向下保留6位小数）。${r.lower_bound.attained?'本方案达到精确下界，仅在声明模型内证明最短。':'尚未证明全局最优；其他优先序可能更短。'}</p><div class="table-scroll"><table><tr><th>工序</th><th>开始日</th><th>完成日</th><th>相对CPM开始延后</th></tr>${p.rows.map(x=>`<tr><td>${esc(x.task_id)} ${esc(x.name)}</td><td>${esc(x.start_day)}</td><td>${esc(x.finish_day)}</td><td>${esc(x.start_delay_days)}</td></tr>`).join('')}</table></div><details><summary>各资源峰值与容量</summary><ul>${p.resource_peaks.map(x=>`<li>${esc(x.resource_id)}：峰值 ${esc(x.peak_units)} / 容量 ${esc(x.capacity_units)}（沿用原声明单位）</li>`).join('')}</ul></details><p>工期、资源及占用由用户声明；不是现场可施工证明或履约保证。</p></section>`;
}

export function attachLeveling(host,record,base,action,onCreated){
  if(record.calculation_type||record.status==='stale')return;
  const box=document.createElement('details');box.className='schedule-section';
  box.innerHTML='<summary>按资源容量生成新的排程方案</summary><p>保留当前CPM记录，另存资源受限方案。优先序只决定下一道可安排工序，允许在前方空档插入；不保证最优。</p><form><label>新方案名称<input name="name" required maxlength="160"></label><details><summary>调整工序优先序</summary><ol data-priority></ol></details><label class="check-option"><input type="checkbox" name="complete" required>已核对全部工序占用；无占用项确实不占用本计划声明的资源</label><label>资源占用完整性依据<textarea name="basis" required minlength="20" maxlength="2000"></textarea></label><button type="submit">生成并另存方案</button></form>';
  host.append(box);const form=box.querySelector('form'),order=record.input.tasks.map(t=>t.task_id),byId=new Map(record.input.tasks.map(t=>[t.task_id,t]));
  form.elements.name.value=(record.input.name+' · 资源受限方案').slice(0,160);
  function draw(){box.querySelector('[data-priority]').innerHTML=order.map((k,i)=>`<li>${esc(k)} ${esc(byId.get(k).name)} <button type="button" data-index="${i}" data-move="-1" ${i===0?'disabled':''} aria-label="上移 ${esc(k)}">上移</button> <button type="button" data-index="${i}" data-move="1" ${i===order.length-1?'disabled':''} aria-label="下移 ${esc(k)}">下移</button></li>`).join('');box.querySelectorAll('[data-move]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.index),j=i+Number(b.dataset.move);[order[i],order[j]]=[order[j],order[i]];draw();});}
  draw();form.onsubmit=e=>{e.preventDefault();action(async()=>{const r=await post(base+'/schedules/'+record.schedule_id+'/resource-levelings',{name:form.elements.name.value,source_hash:record.hash,priority:[...order],resource_demands_complete:form.elements.complete.checked,demand_basis:form.elements.basis.value});await onCreated(r);},e.submitter);};
}
