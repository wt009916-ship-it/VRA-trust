import {refreshAgentMode} from './agent-mode-status.js';
import {captureTaskEditor} from './task-editor.js';
import {validateReadRequests,readRequestProgressMarkup} from './agent-requests.js';
import { request, post, escape as esc, number as num } from './api.js';
import {professionalArtifactMarkup,modelCommentaryMarkup,checkedDeliveryMarkup,selectedReadProgressMarkup} from './agent-artifacts.js';
import {parseCalculationPlans, calculationProgressMarkup} from './agent-calculations.js';
import {capabilityMarkup} from './agent-capabilities.js';

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

function eventOriginLabel(event) {
  if (Number.isInteger(event.parent_event)) return ' · 批量子操作';
  if (event.origin === 'model') return ' · 模型选择';
  return event.origin === 'controller' ? ' · 流程读取' : '';
}

export function developerSettings(modal, action, notice) {
  action(async()=>{
    const config=await request('/developer/provider');
    modal('开发者设置 · AI Provider', `<form id="provider-form"><p class="form-note">使用 DeepSeek 官方 API。Key 只提交给本机后端，Windows 使用系统账户加密保存，不写入浏览器存储。启用后，提问、项目摘要和工具结果会发送给服务商；原始文件不自动上传。</p><label>Provider<input value="DeepSeek" disabled></label><label>模型<input name="model" required value="${esc(config.model)}" maxlength="80"></label><label>API Key<input type="password" name="api_key" autocomplete="off" placeholder="${config.key_configured?'已配置；留空保留原 Key':'填写你的 API Key'}"></label><label class="check-option"><input type="checkbox" name="enabled" ${config.enabled?'checked':''}>启用外部 AI 服务</label><label class="check-option"><input type="checkbox" name="clear_key">删除已保存的 Key</label><p class="subtle">${esc(config.endpoint)} · ${esc(config.key_storage)}</p><div class="actions"><button class="primary" type="submit">保存配置</button><button type="button" id="test-provider">测试连接与 Tool Calling</button></div><p id="provider-result" role="status"></p></form>`);
    document.querySelector('#provider-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);const body={model:f.get('model'),enabled:f.has('enabled'),clear_key:f.has('clear_key')};if(f.get('api_key'))body.api_key=f.get('api_key');action(async()=>{const s=await request('/developer/provider',{method:'PUT',body:JSON.stringify(body)});document.querySelector('[name=api_key]').value='';document.querySelector('#provider-result').textContent=s.enabled?'配置已保存。请测试服务商连接。':'已保存，外部 AI 当前关闭。';notice('配置已保存');await refreshAgentMode();},e.submitter);};
    document.querySelector('#test-provider').onclick=e=>action(async()=>{document.querySelector('#provider-result').textContent='正在实际请求服务商…';const r=await post('/developer/provider/test',{});document.querySelector('#provider-result').textContent=r.tool_calling_observed?'连接成功，服务商返回了真实工具调用。':'连接成功，但本次未观察到工具调用，请检查模型。';},e.currentTarget);
    const local=await request('/developer/local-model');
    const providerForm=document.querySelector('#provider-form');
    if(!providerForm?.isConnected)return;
    providerForm.insertAdjacentHTML('afterend',localModelMarkup(local));
    document.querySelector('#local-model-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{await request('/developer/local-model',{method:'PUT',body:JSON.stringify({enabled:f.has('enabled'),port:Number(f.get('port')),model:f.get('model')})});document.querySelector('#local-model-result').textContent='本地配置已保存，请测试连接；配置就绪不代表能力验收通过。';await refreshAgentMode();},e.submitter);};
    document.querySelector('#test-local-model').onclick=e=>action(async()=>{const result=document.querySelector('#local-model-result');result.textContent='正在请求本机模型…';const r=await post('/developer/local-model/test',{});if(result.isConnected)result.textContent=r.tool_calling_observed?'本机连接成功，观察到工具调用；本次未执行工程工具。':'本机连接成功，本次未观察到要求的工具调用。';},e.currentTarget);
  });
}

export function localModelMarkup(config) {
  return `<form id="local-model-form"><h3>本机模型</h3><p>提问、项目摘要与工具结果仅发送至本机。需要先启动模型服务，并由启动环境配置访问令牌；这里不接收或显示令牌。</p><label>本机端口<input name="port" type="number" min="1024" max="65535" required value="${esc(config.port)}"></label><label>模型名称<input name="model" required maxlength="80" value="${esc(config.model)}"></label><label class="check-option"><input name="enabled" type="checkbox" ${config.enabled?'checked':''}>启用本机模型</label><p class="subtle">访问令牌${config.key_configured?'已配置':'未配置'} · 配置就绪不等于连通或工程能力通过验收</p><div class="actions"><button class="primary" type="submit">保存本机配置</button><button id="test-local-model" type="button">测试本机连接与工具调用</button></div><p id="local-model-result" role="status"></p></form>`;
}

export async function runAgent(state, message, target, mode, allowCompute, objective='open_ended', continuePrevious=false, calculationText='', readRows=[]) {
  const calculationPlans=parseCalculationPlans(calculationText,{mode,allowCompute,objective});
  const readRequests=validateReadRequests(readRows,{mode,allowCompute,objective,calculationPlans});
  const pid=state.project.project_id;
  const revealResult=captureTaskEditor(target);
  const toolLabels={requested_availability:'核验声明的记录可用性',requested_availability_recheck:'重新核对声明可用性',professional_inventory:'查询所选专业目录',professional_missing_recheck:'复核目录中的缺失状态',professional_missing:'核验项目记录缺失',calculation_prepare:'执行并读取所选计划',professional_read_many:'读取所选专业记录',calculation_execute:'执行已授权计算',project_get:'读取项目声明',evidence_list:'读取证据与来源',evidence_validate:'核验资料与仿真准入','llm.request':'调用所选 AI 模型',simulation_create:'提交真实 EnergyPlus 仿真',simulation_result:'核验并读取工程结果',simulation_status:'检查仿真任务状态',carbon_calculate:'仅重算运行碳排',claim_trace:'追溯结论依赖',counterexample_search:'搜索方案排序反例',counterexample_status:'读取搜索范围与结果',evidence_action_rank:'评估补证成本情景',scheme_compare:'比较有效方案',certificate_generate:'生成决策证书草稿',report_generate:'生成同源报告',building_get:'读取建筑参数',evidence_gap_rank:'检查当前证据缺口'};
  const history=continuePrevious?await request('/projects/'+pid+'/agent-tasks'):[];
  const previous=history.find(t=>t.status!=='running');
  const task=await post('/projects/'+pid+'/agent/chat',{message,mode,allow_compute:allowCompute,objective,previous_agent_id:previous?.agent_id||null,calculation_plans:calculationPlans,read_requests:readRequests});
  const outcomes={verified:'所选目标已核验',partial:'部分内容已核验',incomplete:'目标尚未完成',not_assessed:'自由任务未核验'};
  const paint=t=>{if(!target.isConnected||state.project?.project_id!==pid)return;target.innerHTML=`<div class="task-reply agent-reply"><header><strong>${t.mode==='local_model'?'本机 AI 工程助手':t.mode==='provider'?'AI 工程助手':'本地工程流程'}</strong><span class="badge">${esc(t.status==='succeeded'?(outcomes[t.answer?.task_completion]||'流程结束 · 任务待核验'):t.status)}</span></header><p class="subtle">引用历史摘要 ${t.context_snapshot?.length||0} 轮 · 工具纠错 ${t.recovery_attempts||0} 次 · 模型恢复尝试 ${t.provider_recovery_attempts||0} 次</p>${capabilityMarkup(t.answer)}${calculationProgressMarkup(t.calculation_progress)}${professionalArtifactMarkup(t.answer?.artifact)}${checkedDeliveryMarkup(t.answer)}${selectedReadProgressMarkup(t)}${readRequestProgressMarkup(t)}<p class="subtle">${esc(t.event_snapshot_notice||'工具时间线记录当时的输入输出；流程读取与模型调用分别标记。')}</p><ol class="tool-timeline">${t.events.map(e=>`<li class="${e.status}"><span class="timeline-dot"></span><details><summary>${esc(toolLabels[e.tool]||e.tool)}${eventOriginLabel(e)}${e.reused?' · 复用本任务提交，未重复执行':''}<small>${e.status==='running'?'执行中':num(e.duration_ms,0)+' ms'}</small></summary><code>${esc(e.tool)}</code><pre>${esc(JSON.stringify(e.result??{error:e.error,recovery:e.recovery,provider_recovery:e.provider_recovery},null,2))}</pre></details></li>`).join('')}</ol>${t.answer?'<p class="subtle">'+esc(t.answer.task_notice||'流程状态不代表专业任务已完成')+'</p><p><strong>'+esc(t.answer.summary)+'</strong></p><ul>'+(t.answer.verification||[]).map(v=>'<li>'+esc(v.meaning)+'：'+(v.passed?'通过':'未通过')+'</li>').join('')+t.answer.gaps.map(g=>'<li>'+esc(g.message)+' · '+esc(g.action)+'</li>').join('')+'</ul>':''}${modelCommentaryMarkup(t)}${t.error?'<p class="error-text">'+esc(t.error)+'</p>':''}<small class="mono">${esc(t.agent_id)}</small></div>`;};
  paint(task);
  if(target.isConnected&&state.project?.project_id===pid)revealResult();
  if(task.status==='running')await new Promise((resolve,reject)=>{const timer=setInterval(async()=>{if(!target.isConnected||state.project?.project_id!==pid){clearInterval(timer);resolve();return;}try{const t=await request('/projects/'+pid+'/agent/'+task.agent_id);paint(t);if(t.status!=='running'){clearInterval(timer);resolve();}}catch(err){clearInterval(timer);reject(err);}},1200);});
}

export function factorEditor(state, modal, action, refresh) {
  action(async()=>{const pid=state.project.project_id, old=await request('/projects/'+pid+'/carbon-factors');const profile=old?.profile||state.profiles.reference_scenario;
    const assurance=await request('/projects/'+pid+'/carbon-factor-assurance');
    const sources=state.evidence.filter(e=>e.source_file&&e.review_state==='confirmed'&&!['ASSUMED','AI_INFERRED','MISSING'].includes(e.status));
    const dialog=modal('运行碳因子 · 选择性重算', `<form id="carbon-form"><p>保存后，当前能耗和 EUI 保持有效；碳排变为 STALE。再点“仅重算碳排”生成新记录，EnergyPlus 调用数为 0。</p><label>适用地区<input name="region" required value="${esc(profile.region)}"></label><label class="check-option"><input name="scenario" type="checkbox" ${profile.scenario?'checked':''}>教学 / 假设因子情景</label><label>分能源因子（含单位、来源和版本）<textarea name="factors" rows="13" required>${esc(JSON.stringify(profile.factors,null,2))}</textarea></label><button class="primary">保存新因子版本</button></form><hr><h3>当前已保存版本的来源复核</h3><p>${esc(assurance.status)} · 自填来源不代表已核证。人工复核不证明碳资产资格。</p><p>先保存因子，再复核对应文件。每项因子须填写 publisher（发布机构）、document_version（文档版本）和 reference_year（数据年份）。勾选已确认的资料后，在说明中逐项记录能源、因子与文件页码的对应关系。</p><form id="factor-review-form">${sources.map(e=>`<label class="check-option"><input type="checkbox" name="source" value="${esc(e.evidence_id)}">${esc(e.name)}</label>`).join('')||'<p>尚无已确认的来源文件，请先在资料库导入并复核。</p>'}<label>人工核对说明<textarea name="note" required minlength="10" maxlength="2000" rows="3"></textarea></label><button ${!old||!sources.length||profile.scenario?'disabled':''}>记录已保存版本 ${old?.revision||'—'} 的人工复核</button></form>`);
    document.querySelector('#carbon-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{await request('/projects/'+pid+'/carbon-factors',{method:'PUT',body:JSON.stringify({expected_revision:old?.revision||0,region:f.get('region'),scenario:f.has('scenario'),factors:JSON.parse(f.get('factors'))})});dialog.close();await refresh();},e.submitter);};
    document.querySelector('#factor-review-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{await post('/projects/'+pid+'/carbon-factor-reviews',{factor_revision:old.revision,evidence_ids:f.getAll('source'),note:f.get('note')});dialog.close();await refresh();},e.submitter);};
  });
}
