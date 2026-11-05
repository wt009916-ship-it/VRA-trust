import {request,post,escape as esc} from './api.js';

const input=(name,label,extra='')=>`<label>${label}<input name="${name}" ${extra}></label>`;
const select=(name,label,values)=>`<label>${label}<select name="${name}">${Object.entries(values).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label>`;
const numeric='type="number" min="0" step="0.000001"';
const source='required minlength="5" maxlength="1000"';
const get=(scope,name)=>scope.querySelector(`[name="${name}"]`).value;
const num=(scope,name)=>get(scope,name)===''?null:Number(get(scope,name));
const statuses={calculated:'计算完成 · 需复核适用性',incomplete:'工期资料不完整',incomplete_progress:'进度资料不完整',constraints_unresolved:'资源约束待解决',stale:'来源或计算器已变更'};
const display=x=>esc(x??'—');

export function scheduleChart(planned){
  if(!planned)return '';
  const extent=Number(planned.duration_days)||1;
  return `<figure class="schedule-chart"><figcaption>计划时间轴 · 连续经过日 · 红色及“关键”文字表示零总时差</figcaption>${planned.rows.map(r=>`<div class="schedule-chart-row"><span>${esc(r.task_id)} ${esc(r.name)}</span><div class="schedule-track"><i class="${r.critical?'critical':''}" style="left:${Number(r.start_day)/extent*100}%;width:${Math.max(0,(Number(r.finish_day)-Number(r.start_day))/extent*100)}%"></i></div><span>${display(r.start_day)} → ${display(r.finish_day)}${r.critical?' · 关键':''}</span></div>`).join('')}</figure>`;
}

function resourcesMarkup(resources){
  return `<p>资源核验：${esc(({conflict:'存在超配，未自动调平',unknown:'容量或时间区间未知',not_assessed:'未声明资源，未评估',checked_declared_resources:'声明资源未发现时间重叠超配'})[resources.status])}</p>${resources.conflicts.length?`<ul>${resources.conflicts.map(c=>`<li>${esc(c.resource_id)}：第${display(c.from_day)}–${display(c.until_day)}日，需求${display(c.demand)} / 容量${display(c.capacity)} ${esc(c.unit)}；工序${c.tasks.map(esc).join('、')}</li>`).join('')}</ul>`:''}${resources.unknown.length?'<p>待补资源资料：'+resources.unknown.map(x=>esc(x.resource_id)+' / '+esc(x.task_id)).join('、')+'</p>':''}`;
}

export async function scheduleWorkspace(state,host,action){
  const base='/projects/'+state.project.project_id;let importId=null,serial=0;
  host.innerHTML=`<div class="view-heading"><div><h1>施工进度与关键路径</h1><p>用工序依赖核对计划，再用有来源的实际进度和剩余工期判断偏差。</p></div></div>
    <div class="actions"><label>导入计划 JSON（保留原件）<input id="schedule-import" type="file" accept=".json"></label><button id="schedule-export" type="button">导出输入草稿</button></div><p id="schedule-import-note" role="status"></p>
    <form id="schedule-form"><section class="schedule-section"><h2>1. 明确计划边界</h2><div class="form-grid">${input('name','计划名称','required maxlength="160"')}${input('time_origin','第0天的时间基准','required minlength="5" maxlength="500" placeholder="例如开工会议确认的起算时刻；明确时区"')}</div><label>施工范围<textarea name="scope" required minlength="10" maxlength="2000"></textarea></label><p>日历口径：连续经过日，不自动扣除周末和节假日。仅支持完成到开始（FS）；间隔需明确填写，零工期表示里程碑。</p></section>
    <section class="schedule-section"><h2>2. 工序与依赖</h2><div id="schedule-tasks"></div><button type="button" id="schedule-add-task">添加工序</button></section>
    <details class="schedule-section"><summary>3. 资源容量与来源（未填写则不评估资源）</summary><p>资源数量最多6位小数。容量为0表示当前不可用，未知留空；占用数量至少0.000001。</p><div id="schedule-resources"></div><button type="button" id="schedule-add-resource">添加资源</button></details>
    <section class="schedule-section"><label class="check-option"><input type="checkbox" id="schedule-progress-enabled">加入现场进度情景</label><div id="schedule-progress" hidden><div class="form-grid">${input('as_of_day','报告时点（第几日）',numeric+' required')}${input('progress_source','进度报告来源',source)}</div><p>逐工序填写状态；未报告保持未知。进行中必须有实际开始日，剩余工期未知时不推算完工。完成比例不能替代剩余工期。</p></div></section>
    <details class="schedule-section"><summary>绑定项目证据</summary>${state.evidence.map(e=>`<label class="check-option"><input type="checkbox" name="evidence_ids" value="${e.evidence_id}">${esc(e.name)} · v${e.revision} · ${esc(e.review_state)}</label>`).join('')||'<p>暂无项目证据，来源将按用户声明保留。</p>'}</details>
    <button class="primary" type="submit">计算并保存计划</button></form><div id="schedule-result" aria-live="polite"></div><section class="schedule-section"><h2>历史计划与进度快照</h2><div id="schedule-history"></div></section>`;
  const form=host.querySelector('#schedule-form'),tasks=host.querySelector('#schedule-tasks'),resources=host.querySelector('#schedule-resources');
  const enabled=()=>host.querySelector('#schedule-progress-enabled').checked;
  function active(group,on){group.hidden=!on;group.querySelectorAll('input,select,textarea').forEach(el=>el.disabled=!on);}
  function addResource(data){
    const row=document.createElement('fieldset');row.innerHTML=`<legend>资源容量</legend><div class="form-grid">${input('resource_id','资源标识','required maxlength="60"')}${input('resource_name','资源名称','required maxlength="160"')}${input('capacity','可用容量（未知留空）','type="number" min="0" step="0.000001"')}${input('unit','容量单位','required maxlength="40"')}${input('resource_source','容量来源',source)}</div><button type="button" data-remove>移除资源</button>`;resources.append(row);
    row.querySelector('[data-remove]').onclick=()=>row.remove();
    row.read=()=>({resource_id:get(row,'resource_id'),name:get(row,'resource_name'),capacity:num(row,'capacity'),unit:get(row,'unit'),source:get(row,'resource_source')});
    if(data)for(const [key,v] of Object.entries({...data,resource_name:data.name,resource_source:data.source}))if(row.querySelector(`[name="${key}"]`))row.querySelector(`[name="${key}"]`).value=v??'';
  }
  function addTask(data,observation){
    serial++;const row=document.createElement('details');row.className='schedule-task';row.open=!data;
    row.innerHTML=`<summary></summary><div class="form-grid">${input('task_id','工序标识','required maxlength="60"')}${input('task_name','工序名称','required maxlength="160"')}${input('duration_days','计划工期（日，未知留空）',numeric+' max="3650"')}${input('duration_source','工期依据',source)}</div><h3>前置工序</h3><p>无前置关系时留空；填写前置工序标识，先完成前置工序及间隔后才能开始。</p><div data-dependencies></div><button type="button" data-add-dep>添加前置关系</button><details><summary>资源占用（按资源标识绑定）</summary><div data-demands></div><button type="button" data-add-demand>添加资源占用</button></details>
      <div data-observation hidden>${select('observation_state','现场状态',{not_reported:'未报告 · 保持未知',not_started:'尚未开始',in_progress:'进行中',completed:'已完成'})}<div data-observed><div class="form-grid"><div data-start>${input('actual_start_day','实际开始日',numeric+' required')}</div><div data-finish>${input('actual_finish_day','实际完成日',numeric+' required')}</div><div data-remaining>${input('remaining_days','剩余工期（日，未知留空）',numeric+' max="3650"')}</div>${input('observation_source','状态及剩余工期来源',source)}</div></div></div><button type="button" data-remove>移除此工序</button>`;
    tasks.append(row);row.querySelector('[name=task_id]').value=data?.task_id||'T'+serial;
    function heading(){row.querySelector('summary').textContent=(get(row,'task_id')||'未命名')+' · '+(get(row,'task_name')||'填写工序名称');}
    row.querySelector('[name=task_id]').oninput=heading;row.querySelector('[name=task_name]').oninput=heading;
    row.querySelector('[data-remove]').onclick=()=>row.remove();
    function addDependency(d){const box=document.createElement('fieldset');box.innerHTML=`<legend>完成到开始 FS</legend><div class="form-grid">${input('predecessor_id','前置工序标识','required maxlength="60"')}${input('lag_days','完成后间隔（日）',numeric+' required max="3650"')}${input('dependency_source','关系依据',source)}</div><button type="button">移除此关系</button>`;row.querySelector('[data-dependencies]').append(box);box.querySelector('button').onclick=()=>box.remove();if(d){box.querySelector('[name=predecessor_id]').value=d.task_id;box.querySelector('[name=lag_days]').value=d.lag_days;box.querySelector('[name=dependency_source]').value=d.source;}}
    function addDemand(d){const box=document.createElement('fieldset');box.innerHTML=`<legend>资源占用</legend><div class="form-grid">${input('resource_id','占用资源标识','required maxlength="60"')}${input('units','占用数量','type="number" min="0.000001" step="0.000001" required')}</div><button type="button">移除此占用</button>`;row.querySelector('[data-demands]').append(box);box.querySelector('button').onclick=()=>box.remove();if(d){box.querySelector('[name=resource_id]').value=d.resource_id;box.querySelector('[name=units]').value=d.units;}}
    row.querySelector('[data-add-dep]').onclick=()=>addDependency();row.querySelector('[data-add-demand]').onclick=()=>addDemand();
    row.updateProgress=()=>{const on=enabled(),s=get(row,'observation_state');active(row.querySelector('[data-observation]'),on);active(row.querySelector('[data-observed]'),on&&s!=='not_reported');active(row.querySelector('[data-start]'),on&&['in_progress','completed'].includes(s));active(row.querySelector('[data-finish]'),on&&s==='completed');active(row.querySelector('[data-remaining]'),on&&s==='in_progress');};
    row.querySelector('[name=observation_state]').onchange=row.updateProgress;
    row.read=()=>({task_id:get(row,'task_id'),name:get(row,'task_name'),duration_days:num(row,'duration_days'),duration_source:get(row,'duration_source'),
      predecessors:[...row.querySelector('[data-dependencies]').children].map(d=>({task_id:get(d,'predecessor_id'),lag_days:num(d,'lag_days'),source:get(d,'dependency_source')})),
      demands:[...row.querySelector('[data-demands]').children].map(d=>({resource_id:get(d,'resource_id'),units:num(d,'units')}))});
    row.observation=()=>{const s=get(row,'observation_state');if(s==='not_reported')return null;return {task_id:get(row,'task_id'),state:s,source:get(row,'observation_source'),...(['in_progress','completed'].includes(s)?{actual_start_day:num(row,'actual_start_day')} : {}),...(s==='completed'?{actual_finish_day:num(row,'actual_finish_day')} : {}),...(s==='in_progress'?{remaining_days:num(row,'remaining_days')} : {})};};
    if(data){for(const key of ['task_id','duration_days','duration_source'])row.querySelector(`[name=${key}]`).value=data[key]??'';row.querySelector('[name=task_name]').value=data.name;data.predecessors.forEach(addDependency);data.demands?.forEach(addDemand);}
    if(observation){row.querySelector('[name=observation_state]').value=observation.state;row.querySelector('[name=observation_source]').value=observation.source;for(const key of ['actual_start_day','actual_finish_day','remaining_days'])row.querySelector(`[name=${key}]`).value=observation[key]??'';}
    heading();row.updateProgress();
  }
  function updateProgress(){active(host.querySelector('#schedule-progress'),enabled());[...tasks.children].forEach(r=>r.updateProgress());}
  function draft(){return {name:get(form,'name'),scope:get(form,'scope'),calendar:'continuous_elapsed_days',time_origin:get(form,'time_origin'),import_file_id:importId,
    tasks:[...tasks.children].map(r=>r.read()),resources:[...resources.children].map(r=>r.read()),evidence_ids:[...form.querySelectorAll('[name=evidence_ids]:checked')].map(e=>e.value),
    progress:enabled()?{as_of_day:num(form,'as_of_day'),source:get(form,'progress_source'),observations:[...tasks.children].map(r=>r.observation()).filter(Boolean)}:null};}
  function populate(b){for(const key of ['name','scope','time_origin'])form.elements[key].value=b[key];importId=b.import_file_id||null;tasks.innerHTML='';resources.innerHTML='';host.querySelector('#schedule-progress-enabled').checked=!!b.progress;form.elements.as_of_day.value=b.progress?.as_of_day??'';form.elements.progress_source.value=b.progress?.source??'';b.resources?.forEach(addResource);b.tasks.forEach(t=>addTask(t,b.progress?.observations.find(o=>o.task_id===t.task_id)));form.querySelectorAll('[name=evidence_ids]').forEach(e=>e.checked=b.evidence_ids?.includes(e.value));updateProgress();}
  function render(record){
    if(!host.isConnected)return;const r=record.result,p=r?.planned,f=r?.forecast;
    host.querySelector('#schedule-result').innerHTML=`<section class="schedule-section"><h2>${esc(record.input.name)} · ${statuses[record.status]}</h2>${p?`<p>计划工期：<strong>${display(p.duration_days)} 连续经过日</strong> · 未做资源调平</p>${resourcesMarkup(p.resources)}${scheduleChart(p)}<div class="table-scroll"><table><tr><th>工序</th><th>开始日</th><th>完成日</th><th>最迟开始</th><th>总时差（日）</th><th>自由时差（日）</th></tr>${p.rows.map(x=>`<tr><td>${esc(x.task_id)} ${esc(x.name)}${x.critical?' · 关键':''}</td><td>${display(x.start_day)}</td><td>${display(x.finish_day)}</td><td>${display(x.latest_start_day)}</td><td>${display(x.total_float_days)}</td><td>${display(x.free_float_days)}</td></tr>`).join('')}</table></div>`:`<p>${record.status==='stale'?'来源或计算器已变更，旧数值不可用于当前决策。':'缺工期：'+(r?.missing_duration_tasks||[]).map(esc).join('、')+'；不按零工期补齐。'}</p>`}
    ${f?`<h3>第${display(f.as_of_day)}日的进度情景</h3><p>情景完工日：<strong>${display(f.finish_day)}</strong>；相对计划完成日偏差：${display(f.finish_variance_days)} 日（正值为延后）。</p>${f.status==='incomplete'?'<p>进度或剩余工期未完整报告，不能给出完整完工预测。</p>':''}${resourcesMarkup(f.resources)}<details><summary>逐工序进度与缺口</summary><pre>${esc(JSON.stringify(f,null,2))}</pre></details>`:''}
    <p>来源为用户声明；未评估施工安全、工序专业适用性或工期履约保证。</p><details><summary>输入、计算过程与来源快照</summary><pre>${esc(JSON.stringify(record,null,2))}</pre></details><p><a href="/api${base}/schedules/${record.schedule_id}" target="_blank" rel="noopener">完整JSON</a> · <a href="/api${base}/schedules/${record.schedule_id}/report.html" target="_blank" rel="noopener">打印进度报告</a></p></section>`;
  }
  async function history(){const list=await request(base+'/schedules');if(!host.isConnected)return;host.querySelector('#schedule-history').innerHTML=list.map(r=>`<p>${esc(r.input.name)} · ${statuses[r.status]} <button type="button" data-show="${r.schedule_id}">查看</button><button type="button" data-copy="${r.schedule_id}">复制为新快照</button></p>`).join('')||'<p>暂无进度记录。</p>';host.querySelectorAll('[data-show]').forEach(b=>b.onclick=()=>action(async()=>render(await request(base+'/schedules/'+b.dataset.show))));host.querySelectorAll('[data-copy]').forEach(b=>b.onclick=()=>action(async()=>{const r=await request(base+'/schedules/'+b.dataset.copy);if(host.isConnected)populate({...r.input,name:r.input.name+' · 新快照'});}));}
  host.querySelector('#schedule-add-task').onclick=()=>addTask();host.querySelector('#schedule-add-resource').onclick=()=>addResource();host.querySelector('#schedule-progress-enabled').onchange=updateProgress;
  form.onsubmit=e=>{e.preventDefault();action(async()=>{const r=await post(base+'/schedules',draft());render(r);await history();if(host.isConnected)host.querySelector('#schedule-result').scrollIntoView({block:'start'});},e.submitter);};
  host.querySelector('#schedule-import').onchange=e=>action(async()=>{const file=e.target.files[0];if(!file)return;if(file.size>2*1024*1024)throw Error('计划文件超过2 MiB');const b=await post(base+'/schedule-validation',JSON.parse(await file.text()));const data=new FormData();data.append('file',file);const saved=await request(base+'/files',{method:'POST',body:data});if(host.isConnected){populate({...b,import_file_id:saved.file_id});host.querySelector('#schedule-import-note').textContent='原件已保留，依赖结构已校验；请复核工期和来源，再计算保存。';}});
  host.querySelector('#schedule-export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(draft(),null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='construction-schedule.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  updateProgress();await history();
}
