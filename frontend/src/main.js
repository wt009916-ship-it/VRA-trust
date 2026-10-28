import { mfaStep, recoveryRoute } from './identity-login.js';
import { mountAuthScreen, reauthenticate, readPreference, writePreference } from './auth-screen.js';
import { confirmNavigation } from './editing-guard.js';
import { mountWorkspace, readRoute } from './workspace-ui.js';
import { thermalResults } from './thermal-results.js';
import { uploadLimitMB } from './api.js';
import './style.css';
import './studio.css';
import { weatherWorkspace } from './weather-ui.js';
import { createPoller } from './polling.js';
import { createEvidenceImporter } from './evidence-import.js';
import { spatialWorkspace } from './model-ui.js';
import { changePassword } from './account-ui.js';
import { intakeWorkspace } from './intake-ui.js';
import { reviewDocument } from './document-review.js';
const adminWorkspace=async root=>{root.textContent='Private console excluded';};
import './intake.css';
import './enterprise.css';
import './professional-ui.css';
import { robustnessWorkspace } from './robustness-ui.js';
import { decisionWorkspace } from './decision-ui.js';
import { engineeringReviewWorkspace } from './review-ui.js';
import {componentWorkspace} from './component-ui.js';
import './review.css';
import { runAgent, factorEditor } from './trust-ui.js';
import { request, post, escape as esc, number as num, latestSchemes, resultValue, comparisonIsCurrent, setCsrfToken } from './api.js';

import { appShell, projectView, icon, projectMetricsMarkup } from './layout.js';

const root = document.querySelector('#app');
const state = { projects: [], project: null, evidence: [], runs: [], gate: null, profiles: {}, health: null, selectedRun: null, comparedIds: [], user: null, view: 'readiness', syncError: false };
const poller = createPoller(refreshRuns, { onError: markDisconnected });
let selection = 0, disposeWorkspace = () => {}, pendingProjectNavigation = null;
function writeRoute(view='projects') {
  const hash=state.project?'#project/'+state.project.project_id+'/'+view:view==='tasks'?'#tasks':'#projects';
  if(location.hash!==hash)history.pushState(null,'',hash);
}
async function restoreRoute() {
  const route=readRoute(location.hash);
  if(route.projectId&&state.projects.some(p=>p.project_id===route.projectId))await selectProject(route.projectId,route.view);
  else if(route.projectId){selection++;poller.stop();state.project=null;home();notice('该项目不存在或当前账号无访问权限。',true);}
  else {selection++;poller.stop();state.project=null;home(route.view==='tasks');}
}
let runsRequest = 0, traceRequest = 0;
const label = { queued: '排队中', running: '仿真中', succeeded: '核验通过', failed: '失败 · 结果不可用', stale: '已失效 · 需复核' };
const badge = (text, type = '') => '<span class="badge ' + type + '">' + esc(text) + '</span>';
const link = (url, text) => '<a href="' + url + '" target="_blank" rel="noopener">' + text + ' ↗</a>';
function notice(message, error = false) {
  const el = document.querySelector('#toast');
  if (!el) return;
  el.textContent = message; el.className = error ? 'toast error' : 'toast'; el.hidden = false;
  clearTimeout(el.timer); el.timer = setTimeout(() => { el.hidden = true; }, 9000);
}
async function action(fn, button) {
  const token = selection;
  if (button) button.disabled = true;
  try { await fn(); } catch (err) { if (token === selection) notice(err.message, true); }
  finally { if (button?.isConnected) button.disabled = state.syncError && ['run', 'compare'].includes(button.id); }
}
function shell() {
  disposeWorkspace();disposeWorkspace=()=>{};
  root.innerHTML = appShell(state);
  document.querySelector('#new-project').onclick = () => openIntake();
  document.querySelector('#all-projects').onclick = async () => { if(!await confirmNavigation())return; selection++; poller.stop(); state.project = null; home(); };
  document.querySelector('#workspace-tasks').onclick=async()=>{if(!await confirmNavigation())return;selection++;poller.stop();state.project=null;home(true);};
  document.querySelector('#load-reference').onclick = e => loadReference(e.currentTarget);
  document.querySelector('#search-projects').onclick = () => searchProjects();
  document.querySelector('#toggle-sidebar').onclick = () => document.querySelector('.app-frame').classList.toggle('sidebar-collapsed');
  document.querySelector('#theme-toggle').onclick = () => { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; writePreference('vra-theme', theme); };
  document.querySelector('#logout').onclick = e => action(async () => { if(!await confirmNavigation())return; try{await post('/auth/logout', {});}catch(error){if(error.status!==401)throw error;} clearSession(); authScreen(false); }, e.currentTarget);

  document.querySelector('#account-settings').onclick=()=>changePassword(modal,action,notice,state.user);
  bindProjectLinks();
}
function bindProjectLinks() {
  document.querySelectorAll('[data-project]').forEach(b => { b.onclick = () => action(() => selectProject(b.dataset.project)); });
}
function loadReference(button) {
  return action(async () => { const p = await post('/reference-projects', {}); await refreshProjects(); await selectProject(p.project_id); notice('已导入参考资料。请先复核文件，再运行仿真。'); }, button);
}
function home(tasks=false) {
  shell();writeRoute(tasks?'tasks':'projects');
  document.querySelector('#workspace-tasks').classList.toggle('active',tasks);
  document.querySelector('#all-projects').classList.toggle('active',!tasks);
  disposeWorkspace=mountWorkspace(document.querySelector('#workspace'),{
    state,tasks,
    openProject:(id,view)=>action(async()=>{await refreshProjects();await selectProject(id,view==='intake'?'readiness':view);if(view==='intake')openIntake(state.project);}),
    openIntake:(id,files=[],resume=null)=>action(async()=>{
      const project=id?await request('/projects/'+id):null;openIntake(project,files,'evidence',resume);
    }),
    reference:e=>loadReference(e?.currentTarget),manual:()=>projectForm()
  });
}
async function openIntake(project = null, files = [], destination = 'evidence', resume = null) {
  if(!await confirmNavigation())return;
  selection++; poller.stop(); state.project=project; shell();
  action(()=>intakeWorkspace(document.querySelector('#workspace'), {
    project, initialFiles:files, destination, resume,
    onCommitted:async()=>{
      try{
        await refreshProjects();
        const template=document.createElement('template');template.innerHTML=appShell(state);
        for(const selector of ['.sidebar-projects','.sidebar-label']){
          const current=root.querySelector(selector), updated=template.content.querySelector(selector);
          if(current&&updated)current.replaceWith(updated);
        }
        bindProjectLinks();
      }catch(error){notice('资料已归档，项目列表暂未刷新：'+error.message,true);}
    },
    back:()=>project?action(()=>selectProject(project.project_id)):home(),
    openProject:async(id,view)=>{await refreshProjects();await selectProject(id,view);notice('资料已归档为待审证据；请核对来源、许可与工程适用性。');}
  }));
}
function searchProjects(view = null, title = '搜索项目') {
  const dialog = modal(title, '<input id="project-search" aria-label="搜索项目名称" placeholder="输入项目名称…" autocomplete="off"><div id="search-results"></div>');
  const update = () => { const term = document.querySelector('#project-search').value.toLowerCase(); document.querySelector('#search-results').innerHTML = state.projects.filter(p => p.name.toLowerCase().includes(term)).map(p => '<button class="search-result" data-search-project="'+p.project_id+'">'+icon('folder')+esc(p.name)+'</button>').join('') || '<p class="empty">没有匹配的项目</p>'; document.querySelectorAll('[data-search-project]').forEach(b => { b.onclick = () => { dialog.close(); action(() => selectProject(b.dataset.searchProject, view)); }; }); };
  document.querySelector('#project-search').oninput = update; update(); document.querySelector('#project-search').focus();
}
function modal(title, html) {
  const dialog = document.querySelector('#dialog');
  dialog.innerHTML = '<div class="dialog-heading"><h2>' + title + '</h2><button type="button" id="close-dialog" aria-label="关闭">×</button></div>' + html;
  document.querySelector('#close-dialog').onclick = () => dialog.close();
  dialog.showModal();
  return dialog;
}
function projectForm(edit = false, view = null) {
  const p = edit ? state.project : null, b = p?.building || {};
  const fields = [['use', '建筑用途', 'text', b.use || ''], ['location', '地点', 'text', b.location || ''], ['region', '地区代码（如 CN-JX / US-CO）', 'text', b.region || ''], ['area_m2', '总建筑面积 m²', 'number', b.area_m2 || ''], ['floors', '楼层数（可留空）', 'number', b.floors || ''], ['floor_height_m', '层高 m（可留空）', 'number', b.floor_height_m || ''], ['window_wall_ratio', '窗墙比 0–1（可留空）', 'number', b.window_wall_ratio ?? '']];
  const dialog = modal(edit ? '修订建筑声明' : '创建工程项目', '<form id="project-form"><p class="form-note">标注必填的项目必须填写；其余可留空。这里登记建筑声明。创建后进入「建模工作区」导入图纸、复核空间并生成 IDF；修订声明会重新核验已有结果。</p>' + (!edit ? '<label>项目名称 <span class="required-mark">必填</span><input name="name" required maxlength="160"></label>' : '') + '<div class="form-grid">' + fields.map(([name, text, type, value]) => '<label>' + text + (['use','location','region','area_m2'].includes(name)?' <span class="required-mark">必填</span>':'') + '<input name="' + name + '" type="' + type + '" ' + (type === 'number' ? 'step="any"' : '') + ' value="' + esc(value) + '" ' + (['use', 'location', 'region', 'area_m2'].includes(name) ? 'required' : '') + '></label>').join('') + '</div>' + ['envelope', 'hvac', 'schedules', 'notes'].map((name, i) => '<label>' + ['围护结构说明', 'HVAC / 设备说明', '运行时段 / 内部负荷说明', '其他资料与不确定性'][i] + '<textarea name="' + name + '">' + esc(b[name] || '') + '</textarea></label>').join('') + '<button class="primary" type="submit">保存项目声明</button></form>');
  document.querySelector('#project-form').onsubmit = e => { e.preventDefault(); action(async () => {
    const data = Object.fromEntries(new FormData(e.currentTarget));
    const building = Object.fromEntries(Object.entries(data).filter(([k]) => k !== 'name'));
    for (const key of ['area_m2', 'floors', 'floor_height_m', 'window_wall_ratio']) building[key] = building[key] === '' ? null : Number(building[key]);
    const result = edit ? await request('/projects/' + p.project_id + '/building', { method: 'PUT', body: JSON.stringify({ expected_revision: p.revision, building }) }) : await post('/projects', { name: data.name, building });
    dialog.close(); await refreshProjects(); await selectProject(result.project_id, view);
  }, e.submitter); };
}
async function refreshProjects() { state.projects = await request('/projects'); }
async function selectProject(id, view = null) {
  if(!await confirmNavigation()){writeRoute(state.view);return;}
  poller.stop();
  const token = ++selection;
  const navigation = {id, view};pendingProjectNavigation=navigation;
  let snapshot;
  try {
    snapshot = await Promise.all([request('/projects/' + id), request('/projects/' + id + '/evidence'), request('/projects/' + id + '/runs'), request('/projects/' + id + '/gate')]);
  } catch (error) {
    if(pendingProjectNavigation===navigation)pendingProjectNavigation=null;
    if (token === selection) { markDisconnected(error); schedulePoll(); }
    throw error;
  }
  const [p, ev, runs, gate] = snapshot;
  if (token !== selection) return;
  const sameProject = state.project?.project_id === id;
  Object.assign(state, { project: p, evidence: ev, runs, gate, selectedRun: null, comparedIds: [], syncError: false, view: navigation.view || (sameProject ? state.view : 'readiness') });
  pendingProjectNavigation=null;
  renderProject();
  schedulePoll();
}
function switchView(view) {
  if(pendingProjectNavigation){pendingProjectNavigation.view=view;return;}
  state.view = view;writeRoute(view);
  document.querySelectorAll('.work-view').forEach(el => { el.hidden = el.id !== view; });
  document.querySelectorAll('[data-view]').forEach(el => el.classList.toggle('selected', el.dataset.view === view));
  const host=document.querySelector('#'+view);
  if(host&&view==='components')action(()=>componentWorkspace(state,host,action,notice));
  if(host&&view==='review')action(()=>engineeringReviewWorkspace(state,host,action,modal,id=>{state.reviewRoomId=id;switchView('spatial');document.querySelector('#spatial')?.reviewFocus?.(id);}));
  if(host && ['spatial','robustness','decision','weather'].includes(view) && !host.dataset.loaded){host.dataset.loaded='true';action(async()=>{try{await (view==='weather'?weatherWorkspace(state,host,action,notice,modal,syncModelViews):view==='decision'?decisionWorkspace(state,host,action,modal,switchView):view==='spatial'?spatialWorkspace(state,host,action,notice,syncModelViews):robustnessWorkspace(state,host,action));}catch(error){delete host.dataset.loaded;throw error;}});}
}
async function syncModelViews(projectId) {
  if(state.project?.project_id!==projectId)return;
  const token=selection;
  renderEvidence();renderRuns();
  const count=document.querySelector('[data-view="evidence"] span');if(count)count.textContent=state.evidence.length;
  const base='/projects/'+state.project.project_id;
  const gate=await request(base+'/gate');
  if(token!==selection||state.project?.project_id!==projectId)return;
  state.gate=gate;
  await refreshRuns();
}
function renderProject() {
  const p = state.project;
  shell();
  document.querySelector('#workspace').innerHTML = projectView(state);
  document.querySelectorAll('[data-view]').forEach(b => { b.onclick = () => switchView(b.dataset.view); });
  document.querySelectorAll('[data-open-view]').forEach(b => { b.onclick = () => switchView(b.dataset.openView); });
  const inspector = document.querySelector('.inspector');
  document.querySelector('#toggle-inspector').onclick = () => { inspector.hidden = !inspector.hidden; };
  document.querySelector('#close-inspector').onclick = () => { inspector.hidden = true; };
  document.querySelector('#edit-building').onclick = () => projectForm(true);
  document.querySelector('#overview-edit-building').onclick = () => projectForm(true);
  document.querySelector('#task-import').onclick = () => openIntake(state.project);
  document.querySelector('#composer-upload').onclick = () => openIntake(state.project);
  document.querySelector('#task-next').onclick = () => switchView(state.gate.can_simulate ? 'simulation' : 'evidence');
  document.querySelector('#task-command').onsubmit = e => {e.preventDefault();const input=document.querySelector('#command');if(!input.value.trim())return;const target=document.querySelector('#task-response');action(()=>runAgent(state,input.value.trim(),target,document.querySelector('#agent-mode').value,document.querySelector('#allow-compute').checked,null,document.querySelector('#agent-task').value,switchView),e.submitter);};
  const history=document.createElement('div');history.className='actions agent-history';
  history.innerHTML='<label>持久任务记录<select aria-label="历史助手任务"><option value="">选择已保存任务</option></select></label><button>刷新记录</button>';
  document.querySelector('#task-response').before(history);
  let savedTasks=[];
  const loadHistory=async()=>{savedTasks=await request('/projects/'+p.project_id+'/agent');if(!history.isConnected)return;history.querySelector('select').innerHTML='<option value="">选择已保存任务</option>'+savedTasks.map(t=>`<option value="${esc(t.agent_id)}">${esc(t.created_at)} · ${esc(t.status)} · ${esc(t.question.slice(0,40))}</option>`).join('');};
  history.querySelector('button').onclick=e=>action(loadHistory,e.currentTarget);
  history.querySelector('select').onchange=e=>{const t=savedTasks.find(t=>t.agent_id===e.target.value);if(t)action(()=>runAgent(state,'',document.querySelector('#task-response'),t.mode,false,null,t.task,switchView,t));};
  action(loadHistory);
  document.querySelector('#edit-factors').onclick=()=>factorEditor(state,modal,action,refreshRuns);
  document.querySelector('#add-evidence').onclick = () => openIntake(state.project);
  document.querySelector('#manual-evidence').onclick = evidenceForm;
  document.querySelector('#review-pending').onclick = () => reviewForm(state.evidence.filter(e => ['idf', 'epw'].includes(e.type) && e.review_state === 'pending'));
  document.querySelector('#run').onclick = e => action(async () => { const run = await post('/runs', { project_id: p.project_id, scheme_id: document.querySelector('#scheme').value, factor_profile_id: document.querySelector('#factor').value }); notice('已排队：' + run.run_id); await refreshRuns(); schedulePoll(); }, e.currentTarget);
  document.querySelector('#compare').onclick = e => action(async () => {
    const latest = latestSchemes(state.runs);
    const token = selection;
    const data = await post('/comparisons', { run_ids: latest.map(r => r.run_id) });
    if (token !== selection || state.syncError || !comparisonIsCurrent(state.runs, latest.map(r => r.run_id))) return;
    state.comparedIds = latest.map(r => r.run_id);
    document.querySelector('#comparison').innerHTML = '<div class="comparison"><h3>当前能耗排序：' + data.energy_order.map(esc).join(' → ') + '</h3><p>' + esc(data.note) + '</p><table><thead><tr><th>方案</th><th>节能率</th><th>工程 CO₂ 差值</th><th>综合推荐</th></tr></thead><tbody>' + data.results.map(r => '<tr><td>' + esc(r.scheme_id) + '</td><td>' + num(r.saving_rate_pct) + '%</td><td>' + num(r.engineering_reduction_kg) + ' kg</td><td>证据不足</td></tr>').join('') + '</tbody></table></div>';
  }, e.currentTarget);
  renderEvidence(); renderRuns(); switchView(state.view);
  const mode=document.querySelector('#agent-mode');request('/agent/status').then(info=>{if(mode?.isConnected){mode.options[1].textContent=info.provider_ready?'AI · '+info.model:'AI · 请先配置 Key';if(info.provider_ready)mode.value='provider';}}).catch(()=>{});
}
function renderEvidence() {
  document.querySelector('#evidence-table').innerHTML = state.evidence.length ? '<div class="table-scroll"><table><thead><tr><th>来源 / 证据</th><th>性质</th><th>人工复核</th><th>版本</th><th></th></tr></thead><tbody>' + state.evidence.map(e => '<tr><td><button class="text-button" data-evidence="' + e.evidence_id + '">' + esc(e.name) + '</button><small>' + esc(e.type.toUpperCase()) + (e.scheme_id ? ' · ' + esc(e.scheme_id) : '') + '</small></td><td>' + badge(e.status) + '</td><td>' + badge({ pending: '待确认', confirmed: '已确认', rejected: '已拒绝' }[e.review_state], e.review_state === 'confirmed' ? 'success' : 'warning') + '</td><td>v' + e.revision + '</td><td><button data-evidence="' + e.evidence_id + '">查看 →</button></td></tr>').join('') + '</tbody></table></div>' : '<div class="empty">尚无证据。上传原文件并登记来源定位，保留每一版资料。</div>';
  document.querySelectorAll('[data-evidence]').forEach(b => { b.onclick = () => evidenceDetail(state.evidence.find(e => e.evidence_id === b.dataset.evidence)); });
}
function evidenceDetail(ev) {
  const content = Object.entries(ev).map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(typeof v === 'object' ? JSON.stringify(v) : v ?? '—') + '</dd>').join('');
  const dialog = modal('证据来源 · ' + esc(ev.name), '<p>来源：'+esc(ev.authority)+' · 使用许可：'+esc(ev.permission)+'</p><p>定位：'+esc(ev.source_locator)+'</p>'+ (ev.value?.analysis?'<details><summary>自动提取的完整记录（待核对）</summary><pre>'+esc(JSON.stringify(ev.value.analysis,null,2))+'</pre></details>':'')+'<details><summary>完整证据记录</summary><dl class="metadata">' + content + '</dl></details>' + (ev.source_file ? link('/api/projects/' + ev.project_id + '/files/' + ev.source_file, '下载原文件') : '') + '<div class="actions"><button id="amend-source">完善来源与许可</button><button id="review-this">更改复核状态</button><button id="history">查看版本历史</button></div><div id="history-content"></div>');
  if(ev.value?.intake_id&&ev.value?.analysis?.facts?.document_pages?.length){
    const button=document.createElement('button');button.textContent='对照原图与校正历史';
    dialog.querySelector('.actions').prepend(button);
    button.onclick=()=>action(async()=>{
      const batch=await request('/intakes/'+ev.value.intake_id);
      const source=batch.files.find(s=>s.file_id===ev.source_file);
      if(!source)throw new Error('资料原件记录不存在，请核对来源');
      dialog.close();reviewDocument(root,batch,source,async()=>{});
    },button);
  }
  document.querySelector('#amend-source').onclick=()=>{
    dialog.close();
    const fields=[['source_locator','来源定位',1000],['authority','来源单位 / 版本',300],['permission','使用许可 / 授权范围',1000],['responsible_person','登记人',100]];
    const editor=modal('完善资料来源', '<form id="source-form"><p>保存为新版本，并恢复待复核状态；原文件和旧记录保留。</p>'+fields.map(([key,label,max])=>'<label>'+label+'<input name="'+key+'" required maxlength="'+max+'" value="'+esc(ev[key])+'"></label>').join('')+'<label>不确定性（可选）<textarea name="uncertainty" maxlength="2000">'+esc(ev.uncertainty||'')+'</textarea></label><button class="primary">保存来源修订</button></form>');
    document.querySelector('#source-form').onsubmit=e=>{e.preventDefault();const values=Object.fromEntries(new FormData(e.currentTarget));action(async()=>{await request('/projects/'+ev.project_id+'/evidence/'+ev.evidence_id+'/metadata',{method:'PUT',body:JSON.stringify({...values,expected_revision:ev.revision})});editor.close();await selectProject(ev.project_id,'evidence');},e.submitter);};
  };
  document.querySelector('#review-this').onclick = () => { dialog.close(); reviewForm([ev]); };
  document.querySelector('#history').onclick = e => action(async () => { const history = await request('/projects/' + ev.project_id + '/evidence/' + ev.evidence_id + '/history'); document.querySelector('#history-content').innerHTML = '<pre>' + esc(JSON.stringify(history, null, 2)) + '</pre>'; }, e.currentTarget);
}
function reviewForm(items) {
  if (!items.length) { notice('没有待确认模型；可点击单条证据调整复核状态。'); return; }
  const dialog = modal('人工复核 · ' + items.length + ' 份证据', '<form id="review-form"><p class="form-note">请先查看原文件，确认模型/天气属于此项目，版本、位置、运行范围和面积声明一致。参考模型仅用于演示验证。确认不改变其 IMPORTED / ASSUMED 属性。</p><ul>' + items.map(e => '<li>' + esc(e.name) + ' · v' + e.revision + '</li>').join('') + '</ul><label>复核人<input name="person" required maxlength="100"></label><label>处理<select name="state"><option value="confirmed">确认用于当前项目计算</option><option value="pending">撤回确认，重新待审</option><option value="rejected">拒绝此证据版本</option></select></label><label>复核依据 / 限制<textarea name="note" required minlength="5" maxlength="2000" placeholder="说明你核对的文件、范围及仍未解决的不确定性"></textarea></label><button class="primary" type="submit">保存复核记录</button></form>');
  document.querySelector('#review-form').onsubmit = e => { e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); action(async () => { for (const item of items) await request('/projects/' + item.project_id + '/evidence/' + item.evidence_id, { method: 'PATCH', body: JSON.stringify({ expected_revision: item.revision, review_state: data.state, responsible_person: data.person, review_note: data.note }) }); dialog.close(); await selectProject(state.project.project_id); notice('已保存独立复核版本。受影响的旧运行会显示失效。'); }, e.submitter); };
}
function evidenceForm() {
  const projectId = state.project.project_id, token = selection;
  const importEvidence = createEvidenceImporter(projectId);
  const dialog = modal('导入资料与登记来源', '<form id="evidence-form"><p class="form-note">这里保存原文件并登记出处。图纸识别请进入「建模工作区」；IDF 要求 9.0 版本及原生 SQL 汇总输出。</p><label>文件（最大 ' + uploadLimitMB() + ' MB）<input type="file" name="file" required accept=".idf,.epw,.pdf,.csv,.xlsx,.xls,.png,.jpg,.jpeg,.ifc,.dxf,.dwg,.json,.xml"></label><div class="form-grid"><label>证据类型<select name="type"><option value="idf">IDF 模型</option><option value="epw">EPW 天气</option><option value="drawing">图纸</option><option value="bill">能耗账单</option><option value="equipment_table">设备台账</option><option value="bim">BIM</option><option value="literature">文献</option><option value="sensor">传感器记录</option></select></label><label>IDF 方案<select name="scheme"><option value="baseline">baseline</option><option value="R1">R1</option><option value="R2">R2</option></select></label></div><label>来源定位<input name="locator" required placeholder="例如：A-17 第 2 页 / CSV 行 15 / IDF 对象名称"></label><label>来源与权威性<input name="authority" required placeholder="文件提供单位、版本和日期"></label><label>使用授权 / 许可<input name="permission" required placeholder="业主授权范围或开源许可来源"></label><label>登记人<input name="person" required></label><label>不确定性说明<textarea name="uncertainty"></textarea></label><button class="primary" type="submit">保存文件和证据记录</button></form>');
  document.querySelector('#evidence-form').onsubmit = e => { e.preventDefault(); const data = new FormData(e.currentTarget), file = e.currentTarget.elements.file.files[0]; action(async () => {
    await importEvidence(file, { type: data.get('type'), source_locator: data.get('locator'), authority: data.get('authority'), permission: data.get('permission'), responsible_person: data.get('person'), acquisition_method: 'manual_upload', status: 'IMPORTED', uncertainty: data.get('uncertainty') || null, scheme_id: data.get('type') === 'idf' ? data.get('scheme') : null });
    if (token !== selection || !dialog.isConnected) return;
    dialog.close(); await selectProject(projectId);
  }, e.submitter); };
}
function renderRuns() {
  const summary=document.querySelector('.project-metrics');
  if(summary && state.project)summary.innerHTML=state.syncError?'<p class="empty">连接中断，等待重新核验项目状态。</p>':projectMetricsMarkup(state);
  const target = document.querySelector('#runs'); if (!target) return;
  for (const id of ['run', 'compare']) { const button = document.querySelector('#' + id); if (button) button.disabled = state.syncError; }
  if (state.syncError) {
    target.innerHTML = '<p class="empty" role="status">连接中断，当前数值有效性尚未核对。正在自动重连，恢复后重新显示核验结果。</p>';
    return;
  }
  target.innerHTML = state.runs.length ? '<div class="table-scroll"><table><thead><tr><th>方案 / run_id</th><th>状态</th><th>年能耗 kWh</th><th>EUI</th><th>运行 CO₂ kg</th><th>依据</th></tr></thead><tbody>' + state.runs.map(r => '<tr><td><strong>' + esc(r.scheme_id) + '</strong><small class="mono">' + esc(r.run_id.slice(0, 16)) + '…</small></td><td>' + badge(label[r.status], r.status === 'succeeded' ? 'success' : 'warning') + (r.warnings_count ? '<small>' + r.warnings_count + ' warnings · 待复核</small>' : '') + (r.error ? '<small class="error-text">' + esc(r.error) + '</small>' : '') + (r.stale_reasons?.length ? '<small class="error-text">' + r.stale_reasons.map(esc).join('；') + '</small>' : '') + '</td><td class="numeric">' + num(resultValue(r, 'annual_energy_kwh')) + '</td><td class="numeric">' + num(resultValue(r, 'eui_kwh_m2a')) + '</td><td class="numeric">' + num(r.status === 'succeeded' ? r.carbon?.operating_carbon_kg : null) + (r.carbon?.scenario ? '<small>教学情景</small>' : '') + (r.carbon?.node_state==='STALE'?'<small class="error-text">STALE · 因子已更新</small><button data-recarbon="'+r.run_id+'">仅重算碳排</button>':'') + '</td><td><button data-trace="' + r.run_id + '">查看依据</button></td></tr>').join('') + '</tbody></table></div>' : '<div class="empty">未计算 · 没有历史数值补位</div>';
  document.querySelectorAll('[data-recarbon]').forEach(b=>{b.onclick=()=>action(async()=>{await post('/runs/'+b.dataset.recarbon+'/recalculate-carbon',{});await refreshRuns();notice('碳排已重算；EnergyPlus 调用 0 次。');},b);});
  document.querySelectorAll('[data-trace]').forEach(b => { b.onclick = () => action(() => trace(b.dataset.trace)); });
}
function graphMarkup(nodes) {
  const index=new Map(nodes.map(n=>[n.id,n])), depth=new Map();
  const level=(id,seen=new Set())=>{if(depth.has(id))return depth.get(id);if(seen.has(id))return 0;seen.add(id);const node=index.get(id),value=node?.depends_on?.length?1+Math.max(...node.depends_on.map(d=>level(d,new Set(seen)))):0;depth.set(id,value);return value;};
  const counts=new Map(),positions=new Map();nodes.forEach(n=>{const col=level(n.id),row=counts.get(col)||0;counts.set(col,row+1);positions.set(n.id,{x:col*205+12,y:row*100+18});});
  const width=(Math.max(...depth.values())+1)*205+12,height=Math.max(...counts.values())*100+20;
  const edges=nodes.flatMap(n=>(n.depends_on||[]).map(d=>{const a=positions.get(d),b=positions.get(n.id);return a&&b?'<path d="M '+(a.x+174)+' '+(a.y+34)+' C '+(a.x+190)+' '+(a.y+34)+','+(b.x-18)+' '+(b.y+34)+','+b.x+' '+(b.y+34)+'" fill="none" stroke="currentColor" marker-end="url(#claim-arrow)"/>':'';})).join('');
  return '<div class="dag-canvas" style="width:'+width+'px;height:'+height+'px"><svg width="'+width+'" height="'+height+'" aria-hidden="true"><defs><marker id="claim-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="none" stroke="currentColor"/></marker></defs>'+edges+'</svg>'+nodes.map(n=>{const p=positions.get(n.id);return '<button style="left:'+p.x+'px;top:'+p.y+'px" class="graph-node '+n.state.toLowerCase()+'" data-node="'+esc(n.id)+'"><small>'+esc(n.kind)+' · '+esc(n.state)+'</small><strong>'+esc(n.label)+'</strong></button>';}).join('')+'</div>';
}
async function trace(id, scroll = true) {
  const token = selection, requestId = ++traceRequest;
  state.selectedRun = id;
  const report = await request('/runs/' + id + '/report.json');
  if (token !== selection || requestId !== traceRequest || state.selectedRun !== id || state.syncError) return;
  const r = report.run;
  document.querySelector('#trace-content').className = 'trace-content';
  document.querySelector('#trace-content').innerHTML = '<div class="trace-heading"><strong class="mono">' + esc(id) + '</strong>' + badge(label[r.status]) + '</div>' + thermalResults(r) + '<div class="graph">' + graphMarkup(report.claims.nodes) + '</div><div class="report-actions">' + link('/api/runs/' + id + '/report.json', '完整 JSON') + link('/api/runs/' + id + '/report.html', '证据报告') + link('/api/runs/' + id + '/report.pdf', '下载 PDF') + link('/api/runs/' + id + '/artifacts', '原始证据 ZIP') + '</div><div class="certificate"><p class="eyebrow">DECISION CERTIFICATE · DRAFT</p><h3>当前拒绝给出确定最优推荐</h3><p>状态：' + esc(report.certificate.status) + ' · 工程师未签署</p><p>成立条件：当前输入适用；失效条件：证据、模型、代码或引擎版本变化。</p><p>尚未排除：模型偏差、舒适性问题、方案翻转风险。建议先复核 Warning，再补充账单和运行时段。</p></div><details><summary>完整版本、SQL 来源定位及未满足设定点时间</summary><pre>' + esc(JSON.stringify({ provenance: r.provenance, metrics: r.metrics, evidence: report.evidence, limitations: r.limitations }, null, 2)) + '</pre></details>';
  document.querySelectorAll('[data-node]').forEach(b => { b.onclick = () => { const ev = report.evidence.find(e => e.evidence_id === report.claims.nodes.find(n=>n.id===b.dataset.node)?.evidence_id); if (ev) evidenceDetail(ev); else {const node=report.claims.nodes.find(n=>n.id===b.dataset.node);modal('结论节点与依赖','<pre>'+esc(JSON.stringify(node,null,2))+'</pre>');} }; });
  if (scroll) switchView('trace');
}
async function refreshRuns() {
  if (!state.project) return;
  const id = state.project.project_id, token = selection, requestId = ++runsRequest;
  const runs = await request('/projects/' + id + '/runs');
  if (token !== selection || requestId !== runsRequest) return;
  const reconnecting = state.syncError;
  state.syncError = false;
  const old = state.runs.find(r => r.run_id === state.selectedRun);
  const current = runs.find(r => r.run_id === state.selectedRun);
  const carbonChanged=runs.some(r=>state.comparedIds.includes(r.run_id)&&JSON.stringify(r.carbon)!==JSON.stringify(state.runs.find(previous=>previous.run_id===r.run_id)?.carbon));
  if(carbonChanged){const table=document.querySelector('#comparison');if(table)table.innerHTML='';state.comparedIds=[];}
  if (reconnecting || JSON.stringify(state.runs) !== JSON.stringify(runs)) {
    state.runs = runs;
    renderRuns();
  }
  const health = document.querySelector('#simulation-health');
  const healthText = runs.some(r => r.status === 'running') ? '仿真中' : runs.length ? '见运行记录' : '未计算';
  if (health && health.textContent !== healthText) health.textContent = healthText;
  if (current && (reconnecting || (old && JSON.stringify(current) !== JSON.stringify(old)))) await trace(current.run_id, false);
  if (token !== selection) return;
  const comparison = document.querySelector('#comparison');
  if (comparison && !comparisonIsCurrent(runs, state.comparedIds)) {
    comparison.innerHTML = '';
    state.comparedIds = [];
  }
}
function schedulePoll() {
  if (state.project) poller.start();
}
function markDisconnected(error) {
  if (!state.project || error.status === 401) return;
  state.syncError = true;
  state.comparedIds = [];
  renderRuns();
  const comparison = document.querySelector('#comparison');
  if (comparison) comparison.innerHTML = '';
  const traceContent = document.querySelector('#trace-content');
  if (traceContent) traceContent.textContent = '连接中断，暂时无法核对报告是否仍然有效。恢复连接后自动重新核验。';
  const health = document.querySelector('#simulation-health');
  if (health) health.textContent = '连接中断 · 正在自动重连';
}
function clearSession() {
  selection++; poller.stop(); disposeWorkspace();disposeWorkspace=()=>{};setCsrfToken('');
  Object.assign(state, {user:null, projects:[], project:null, evidence:[], runs:[], selectedRun:null, comparedIds:[]});
}
async function enterWorkspace(session) {
  state.user = session.user; setCsrfToken(session.csrf_token);
  if(location.pathname.replace(/\/$/,'')==='/admin'){
    await adminWorkspace(root,state.user,async()=>{try{await post('/auth/logout',{});}catch(error){if(error.status!==401)throw error;}clearSession();authScreen(false);});return;
  }
  [state.health, state.profiles] = await Promise.all([request('/health'), request('/factor-profiles')]);
  await refreshProjects(); await restoreRoute();
}
async function resumeSSOFactor(){
  authScreen(false);
  try{const pending=await request('/auth/mfa/pending');await enterWorkspace(await mfaStep(root.querySelector('#auth-form'),pending.challenge));}
  catch(error){history.replaceState(null,'',location.pathname);authScreen(false);const message=root.querySelector('#auth-error');message.textContent=error.message;message.hidden=false;}
}
function authScreen(setup, register = false) {
  mountAuthScreen(root,{setup,register,admin:location.pathname.startsWith('/admin'),registrationMode:state.registrationMode,ssoAvailable:state.ssoAvailable,emailRecoveryAvailable:state.emailRecoveryAvailable,
    onSwitch:next=>authScreen(false,next),onSession:()=>{
      // A successful password submission navigates the document, giving native
      // password managers an unambiguous completion signal. Cookie bootstrap
      // then opens the requested workspace; no password crosses the navigation.
      if(/^#sso-/.test(location.hash))history.replaceState(null,'',location.pathname);
      location.reload();
    }});
}
let recoveringSession=false;
async function recoverSession(){
  if(recoveringSession)return;
  if(!state.user){authScreen(false);return;}
  recoveringSession=true;poller.stop();
  try{
    const session=await reauthenticate(state.user);
    if(!session){clearSession();authScreen(false);return;}
    state.user=session.user;setCsrfToken(session.csrf_token);
    if(state.project)poller.start();
    notice('已重新登录，编辑已保留。请重试刚才的操作。');
  }finally{recoveringSession=false;}
}
let handlingRecovery=false;
async function handleRecoveryHash(){
  const route=location.hash.match(/^#(verify-email|reset-password)\/(.+)$/);
  if(!route){if(root.querySelector('.recovery-page'))location.reload();return false;}
  if(handlingRecovery)return false;
  handlingRecovery=true;
  try{if(!await confirmNavigation()){writeRoute(state.view);return true;}clearSession();await recoveryRoute(root,route[1],route[2]);return true;}
  finally{handlingRecovery=false;}
}
window.addEventListener('popstate',()=>{if(/^#(verify-email|reset-password)\//.test(location.hash)){handleRecoveryHash();return;}if(state.user&&!location.pathname.startsWith('/admin'))action(restoreRoute);});
window.addEventListener('hashchange',event=>{if(event.newURL===location.href)handleRecoveryHash();});
document.addEventListener('session-expired',recoverSession);
let refreshingIdentity=false;
async function refreshIdentity(){
  if(!state.user||refreshingIdentity||recoveringSession)return;
  refreshingIdentity=true;
  try{
    const session=await request('/auth/me');
    if(session.user.id!==state.user.id){clearSession();authScreen(false);notice('浏览器已切换账号，请重新登录后打开对应的项目。',true);return;}
    state.user=session.user;setCsrfToken(session.csrf_token);
  }catch(error){if(error.status===401)await recoverSession();}
  finally{refreshingIdentity=false;}
}
document.addEventListener('session-refresh-required',refreshIdentity);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshIdentity();});
window.addEventListener('pageshow',event=>{if(event.persisted)refreshIdentity();});

document.addEventListener('keydown', e => {
  if (!state.user || location.pathname.startsWith('/admin') || document.querySelector('dialog[open]')) return;
  if ((e.ctrlKey || e.metaKey) && ['k','n'].includes(e.key.toLowerCase())) { e.preventDefault(); if (e.key.toLowerCase()==='k') searchProjects(); else openIntake(); }
});
document.documentElement.dataset.theme = readPreference('vra-theme','light');
root.innerHTML = '<div class="boot-screen">稀土智暖 <span>正在打开工作区…</span></div>';
(async () => { try { const route=location.hash.match(/^#(verify-email|reset-password)\/(.+)$/);if(route){await recoveryRoute(root,route[1],route[2]);return;}const status=await request('/auth/status'); state.registrationMode=status.registration_mode;state.ssoAvailable=status.sso_available;state.emailRecoveryAvailable=status.email_recovery_available;if(location.hash==='#sso-mfa'){await resumeSSOFactor();return;} if (status.setup_required) { authScreen(true); return; } try { await enterWorkspace(await request('/auth/me')); } catch(err) { if(err.status===401) authScreen(false); else throw err; } } catch(err) { root.innerHTML='<div class="boot-screen"><strong>暂时无法连接工作区</strong><p>'+esc(err.message)+'</p><button id="retry-connection">重试</button></div>'; document.querySelector('#retry-connection').onclick=()=>location.reload(); } })();

// Apply one consistent required-field cue to dynamic forms in every workspace.
new MutationObserver(()=>{
  root.querySelectorAll('input[required],select[required],textarea[required]').forEach(input=>{
    const label=input.closest('label');
    if(!label||label.querySelector('.required-mark')||label.textContent.includes('必填')||label.textContent.includes('必选'))return;
    const mark=document.createElement('span');mark.className='required-mark';mark.textContent='必填';label.append(mark);
  });
}).observe(root,{childList:true,subtree:true});
