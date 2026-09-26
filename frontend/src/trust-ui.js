import { request, post, escape as esc, number as num } from './api.js';

export const walkthroughSteps = [
  ['导入残缺资料', '图纸、台账、IDF 与天气进入项目。每份资料保留来源和版本。', 'Evidence Manifest', '未确认 → 待复核'],
  ['承认未知，先过准入', '构造不明、版本冲突时暂停计算，列出缺口与确认动作。', 'Evidence Gate', '缺少证据 · 拒绝确定推荐'],
  ['让工具真实执行', 'Agent 编排任务，EnergyPlus 计算能耗；每次运行保留输入和原始输出。', 'Tool Timeline', '锁定输入 → 仿真 → SQL 核验'],
  ['追溯每一个结论', '从推荐回到指标、计算和资料，点击节点就能看到依赖。', 'Claim DAG', '证据 → 仿真 → 能耗 → 碳排'],
  ['寻找推翻建议的条件', '在明确参数域和预算内搜索排序翻转；未发现不等于证明稳定。', 'Counterexample Search', '搜索域 · 预算 · 覆盖 · 反例'],
  ['按风险与成本补证', '基于已搜索的情景评估补证价值；费用由工程师提供。', 'Evidence Action Planner', '缺什么 → 怎么补 → 是否值得'],
  ['只重算受影响部分', '修改碳因子，保留能耗与 EUI，仅更新碳排和证书。', 'Selective Recomputation', 'Energy VALID · Carbon STALE'],
  ['交付可复核证书', '记录成立条件、未排除风险、证据索引与 run_id，交给工程师复核。', 'Decision Certificate', '证据 · 反例 · 版本 · 未签署'],
];

export function workflowMarkup() {
  return `<section class="workflow-demo" aria-label="项目工作流演示"><header><div><span class="eyebrow">VRA-TRUST IN ACTION</span><h2>从一份不完整的资料，到可复核的决策。</h2></div><span class="badge">流程示意 · 非实时计算</span></header><div class="demo-stage"><div class="demo-story"><span id="demo-count"></span><h3 id="demo-title"></h3><p id="demo-description"></p></div><div class="demo-terminal"><span id="demo-system"></span><strong id="demo-status"></strong><div class="demo-rail">${['证据','准入','工具','结论'].map((s,i)=>`<i data-rail="${i}">${s}</i>`).join('<b>→</b>')}</div></div></div><footer><div class="demo-progress">${walkthroughSteps.map((s,i)=>`<button data-demo-step="${i}" aria-label="第 ${i+1} 步：${s[0]}">${String(i+1).padStart(2,'0')}</button>`).join('')}</div><button id="demo-play">暂停</button></footer></section>`;
}

export function bindWorkflow() {
  const host = document.querySelector('.workflow-demo'); if (!host) return;
  let index=0, paused=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const paint=()=>{ const s=walkthroughSteps[index]; for(const [id,value] of Object.entries({'demo-count':String(index+1).padStart(2,'0')+' / 08','demo-title':s[0],'demo-description':s[1],'demo-system':s[2],'demo-status':s[3]})) host.querySelector('#'+id).textContent=value; host.querySelectorAll('[data-demo-step]').forEach(b=>{b.classList.toggle('selected',Number(b.dataset.demoStep)===index); b.setAttribute('aria-current',Number(b.dataset.demoStep)===index?'step':'false');}); host.querySelector('#demo-play').textContent=paused?'播放':'暂停'; host.dataset.stage=String(index); };
  host.querySelectorAll('[data-demo-step]').forEach(b=>{b.onclick=()=>{index=Number(b.dataset.demoStep);paused=true;paint();};});
  host.querySelector('#demo-play').onclick=()=>{paused=!paused;paint();}; paint();
  const timer=setInterval(()=>{if(!host.isConnected){clearInterval(timer);return;}if(!paused&&!document.hidden){index=(index+1)%walkthroughSteps.length;paint();}},4500);
}

export function developerSettings(modal, action, notice) {
  action(async()=>{
    const config=await request('/developer/provider');
    modal('开发者设置 · AI Provider', `<form id="provider-form"><p class="form-note">使用 DeepSeek 官方 API。Key 只提交给本机后端，Windows 使用系统账户加密保存，不写入浏览器存储。启用后，提问、项目摘要和工具结果会发送给服务商；原始文件不自动上传。</p><label>Provider<input value="DeepSeek" disabled></label><label>模型<input name="model" required value="${esc(config.model)}" maxlength="80"></label><label>API Key<input type="password" name="api_key" autocomplete="off" placeholder="${config.key_configured?'已配置；留空保留原 Key':'填写你的 API Key'}"></label><label class="check-option"><input type="checkbox" name="enabled" ${config.enabled?'checked':''}>启用外部 AI 服务</label><label class="check-option"><input type="checkbox" name="clear_key">删除已保存的 Key</label><p class="subtle">${esc(config.endpoint)} · ${esc(config.key_storage)}</p><div class="actions"><button class="primary" type="submit">保存配置</button><button type="button" id="test-provider">测试连接与 Tool Calling</button></div><p id="provider-result" role="status"></p></form>`);
    document.querySelector('#provider-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);const body={model:f.get('model'),enabled:f.has('enabled'),clear_key:f.has('clear_key')};if(f.get('api_key'))body.api_key=f.get('api_key');action(async()=>{const s=await request('/developer/provider',{method:'PUT',body:JSON.stringify(body)});document.querySelector('[name=api_key]').value='';document.querySelector('#provider-result').textContent=s.enabled?'配置已保存。请测试服务商连接。':'已保存，外部 AI 当前关闭。';notice('配置已保存');},e.submitter);};
    document.querySelector('#test-provider').onclick=e=>action(async()=>{document.querySelector('#provider-result').textContent='正在实际请求服务商…';const r=await post('/developer/provider/test',{});document.querySelector('#provider-result').textContent=r.tool_calling_observed?'连接成功，服务商返回了真实工具调用。':'连接成功，但本次未观察到工具调用，请检查模型。';},e.currentTarget);
  });
}

export async function runAgent(state, message, target, mode, allowCompute, studyPlan = null) {
  const pid=state.project.project_id;
  const toolLabels={project_diagnose:'诊断材料、证据与方案决策',material_list:'核对材料参数和实测证据',material_targets:'定位模型构造与表面',material_study_create:'执行材料方案研究',decision_status:'评估工程约束与候选',decision_report:'生成材料决策报告',project_get:'读取项目声明',evidence_list:'读取证据与来源',evidence_validate:'核验资料与仿真准入','llm.request':'调用 AI 服务商',simulation_create:'提交真实 EnergyPlus 仿真',simulation_result:'核验并读取工程结果',simulation_status:'检查仿真任务状态',carbon_calculate:'仅重算运行碳排',claim_trace:'追溯结论依赖',counterexample_search:'搜索方案排序反例',counterexample_status:'读取搜索范围与结果',evidence_action_rank:'评估补证成本情景',scheme_compare:'比较有效方案',certificate_generate:'生成决策证书草稿',report_generate:'生成同源报告',building_get:'读取建筑参数',evidence_gap_rank:'检查当前证据缺口'};
  const task=await post('/projects/'+pid+'/agent/chat',{message,mode,allow_compute:allowCompute,study_plan:studyPlan});
  const paint=t=>{target.innerHTML=`<div class="task-reply agent-reply"><header><strong>${t.mode==='provider'?'AI 工程助手':'本地工程流程'}</strong><span class="badge">${esc(t.status)}</span></header><ol class="tool-timeline">${t.events.map(e=>`<li class="${e.status}"><span class="timeline-dot"></span><details><summary>${esc(toolLabels[e.tool]||e.tool)}<small>${e.status==='running'?'执行中':num(e.duration_ms,0)+' ms'}</small></summary><code>${esc(e.tool)}</code><pre>${esc(JSON.stringify(e.result??{error:e.error},null,2))}</pre></details></li>`).join('')}</ol>${t.answer?'<p><strong>'+esc(t.answer.summary)+'</strong></p><ul>'+t.answer.gaps.map(g=>'<li>'+esc(g.message)+' · '+esc(g.action)+'</li>').join('')+'</ul>':''}${t.answer?.diagnosis?'<section class="agent-diagnosis"><h3>下一步工程行动</h3><ol>'+t.answer.diagnosis.tasks.slice(0,6).map(task=>'<li><strong>'+esc(task.title)+'</strong><p>'+esc(task.action)+'</p></li>').join('')+'</ol>'+(t.answer.diagnosis.current_assessment?'<p>当前非支配候选：'+t.answer.diagnosis.current_assessment.pareto_option_ids.map(esc).join('、')+'。完整约束和比较依据见「材料与决策」。</p>':'<p>在「材料与决策」登记参数、创建真实研究后，可获得条件候选比较。</p>')+'</section>':''}${t.llm_commentary?'<details><summary>AI 解释 · 非核验工程结论</summary><p class="model-prose">'+esc(t.llm_commentary)+'</p></details>':''}${t.error?'<p class="error-text">'+esc(t.error)+'</p>':''}<small class="mono">${esc(t.agent_id)}</small></div>`;};
  paint(task);
  if(task.status==='running')await new Promise((resolve,reject)=>{const timer=setInterval(async()=>{if(!target.isConnected||state.project?.project_id!==pid){clearInterval(timer);resolve();return;}try{const t=await request('/projects/'+pid+'/agent/'+task.agent_id);paint(t);if(t.status!=='running'){clearInterval(timer);resolve();}}catch(err){clearInterval(timer);reject(err);}},1200);});
}

export function factorEditor(state, modal, action, refresh) {
  action(async()=>{const pid=state.project.project_id, old=await request('/projects/'+pid+'/carbon-factors');const profile=old?.profile||state.profiles.reference_scenario;
    const dialog=modal('运行碳因子 · 选择性重算', `<form id="carbon-form"><p>保存后，当前能耗和 EUI 保持有效；碳排变为 STALE。再点“仅重算碳排”生成新记录，EnergyPlus 调用数为 0。</p><label>适用地区<input name="region" required value="${esc(profile.region)}"></label><label class="check-option"><input name="scenario" type="checkbox" ${profile.scenario?'checked':''}>教学 / 假设因子情景</label><label>分能源因子（含单位、来源和版本）<textarea name="factors" rows="13" required>${esc(JSON.stringify(profile.factors,null,2))}</textarea></label><button class="primary">保存新因子版本</button></form>`);
    document.querySelector('#carbon-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{await request('/projects/'+pid+'/carbon-factors',{method:'PUT',body:JSON.stringify({expected_revision:old?.revision||0,region:f.get('region'),scenario:f.has('scenario'),factors:JSON.parse(f.get('factors'))})});dialog.close();await refresh();},e.submitter);};
  });
}
