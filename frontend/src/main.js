import './style.css';
import { request, post, escape as esc, number as num, latestSchemes, resultValue, comparisonIsCurrent, setCsrfToken } from './api.js';

import { appShell, homeView, projectView, authView, icon } from './layout.js';

const root = document.querySelector('#app');
const state = { projects: [], project: null, evidence: [], runs: [], gate: null, profiles: {}, health: null, selectedRun: null, comparedIds: [], user: null, view: 'readiness' };
let pollTimer;
let selection = 0;
const label = { queued: '排队中', running: '仿真中', succeeded: '核验通过', failed: '失败 · 结果不可用', stale: '已失效 · 需复核' };
const badge = (text, type = '') => '<span class="badge ' + type + '">' + esc(text) + '</span>';
const link = (url, text) => '<a href="' + url + '" target="_blank" rel="noopener">' + text + ' ↗</a>';
function notice(message, error = false) {
  const el = document.querySelector('#toast');
  el.textContent = message; el.className = error ? 'toast error' : 'toast'; el.hidden = false;
  clearTimeout(el.timer); el.timer = setTimeout(() => { el.hidden = true; }, 9000);
}
async function action(fn, button) {
  if (button) button.disabled = true;
  try { await fn(); } catch (err) { notice(err.message, true); }
  finally { if (button?.isConnected) button.disabled = false; }
}
function shell() {
  root.innerHTML = appShell(state);
  document.querySelector('#new-project').onclick = () => projectForm();
  document.querySelector('#all-projects').onclick = () => { selection++; clearTimeout(pollTimer); state.project = null; home(); };
  document.querySelector('#load-reference').onclick = e => loadReference(e.currentTarget);
  document.querySelector('#search-projects').onclick = searchProjects;
  document.querySelector('#toggle-sidebar').onclick = () => document.querySelector('.app-frame').classList.toggle('sidebar-collapsed');
  document.querySelector('#theme-toggle').onclick = () => { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; localStorage.setItem('vra-theme', theme); };
  document.querySelector('#logout').onclick = e => action(async () => { await post('/auth/logout', {}); clearSession(); authScreen(false); }, e.currentTarget);
  bindProjectLinks();
}
function bindProjectLinks() {
  document.querySelectorAll('[data-project]').forEach(b => { b.onclick = () => action(() => selectProject(b.dataset.project)); });
}
function loadReference(button) {
  return action(async () => { const p = await post('/reference-projects', {}); await refreshProjects(); await selectProject(p.project_id); notice('已导入参考资料。请先复核文件，再运行仿真。'); }, button);
}
function home() {
  shell();
  document.querySelector('#workspace').innerHTML = homeView(state);
  document.querySelector('#create-project').onclick = () => projectForm();
  document.querySelector('#reference-project').onclick = e => loadReference(e.currentTarget);
  document.querySelector('#intake-composer').onsubmit = e => { e.preventDefault(); const name = document.querySelector('#project-intent').value.trim(); projectForm(); if (name) document.querySelector('[name="name"]').value = name; };
  document.querySelector('#how-it-works').onclick = () => modal('从资料到可复核结果', '<ol class="workflow-steps"><li><strong>建立项目</strong><p>填写建筑用途、地点和面积。</p></li><li><strong>导入并确认资料</strong><p>上传 IDF、天气文件和工程依据，记录来源。</p></li><li><strong>运行并比较方案</strong><p>使用真实仿真结果，保留警告与不确定性。</p></li><li><strong>查看依据，导出报告</strong><p>每个结果绑定独立运行与证据版本。</p></li></ol>');
  bindProjectLinks();
}
function searchProjects() {
  const dialog = modal('搜索项目', '<input id="project-search" aria-label="搜索项目名称" placeholder="输入项目名称…" autocomplete="off"><div id="search-results"></div>');
  const update = () => { const term = document.querySelector('#project-search').value.toLowerCase(); document.querySelector('#search-results').innerHTML = state.projects.filter(p => p.name.toLowerCase().includes(term)).map(p => '<button class="search-result" data-search-project="'+p.project_id+'">'+icon('folder')+esc(p.name)+'</button>').join('') || '<p class="empty">没有匹配的项目</p>'; document.querySelectorAll('[data-search-project]').forEach(b => { b.onclick = () => { dialog.close(); action(() => selectProject(b.dataset.searchProject)); }; }); };
  document.querySelector('#project-search').oninput = update; update(); document.querySelector('#project-search').focus();
}
function modal(title, html) {
  const dialog = document.querySelector('#dialog');
  dialog.innerHTML = '<div class="dialog-heading"><h2>' + title + '</h2><button type="button" id="close-dialog" aria-label="关闭">×</button></div>' + html;
  document.querySelector('#close-dialog').onclick = () => dialog.close();
  dialog.showModal();
  return dialog;
}
function projectForm(edit = false) {
  const p = edit ? state.project : null, b = p?.building || {};
  const fields = [['use', '建筑用途', 'text', b.use || ''], ['location', '地点', 'text', b.location || ''], ['region', '地区代码（如 CN-JX / US-CO）', 'text', b.region || ''], ['area_m2', '总建筑面积 m²', 'number', b.area_m2 || ''], ['floors', '楼层数（可留空）', 'number', b.floors || ''], ['floor_height_m', '层高 m（可留空）', 'number', b.floor_height_m || ''], ['window_wall_ratio', '窗墙比 0–1（可留空）', 'number', b.window_wall_ratio ?? '']];
  const dialog = modal(edit ? '修订建筑声明' : '创建工程项目', '<form id="project-form"><p class="form-note">用于核对导入模型。当前版本不会根据表单自动生成或修改 IDF；修改声明将使已有运行失效。</p>' + (!edit ? '<label>项目名称<input name="name" required maxlength="160"></label>' : '') + '<div class="form-grid">' + fields.map(([name, text, type, value]) => '<label>' + text + '<input name="' + name + '" type="' + type + '" ' + (type === 'number' ? 'step="any"' : '') + ' value="' + esc(value) + '" ' + (['use', 'location', 'region', 'area_m2'].includes(name) ? 'required' : '') + '></label>').join('') + '</div>' + ['envelope', 'hvac', 'schedules', 'notes'].map((name, i) => '<label>' + ['围护结构说明', 'HVAC / 设备说明', '运行时段 / 内部负荷说明', '其他资料与不确定性'][i] + '<textarea name="' + name + '">' + esc(b[name] || '') + '</textarea></label>').join('') + '<button class="primary" type="submit">保存项目声明</button></form>');
  document.querySelector('#project-form').onsubmit = e => { e.preventDefault(); action(async () => {
    const data = Object.fromEntries(new FormData(e.currentTarget));
    const building = Object.fromEntries(Object.entries(data).filter(([k]) => k !== 'name'));
    for (const key of ['area_m2', 'floors', 'floor_height_m', 'window_wall_ratio']) building[key] = building[key] === '' ? null : Number(building[key]);
    const result = edit ? await request('/projects/' + p.project_id + '/building', { method: 'PUT', body: JSON.stringify({ expected_revision: p.revision, building }) }) : await post('/projects', { name: data.name, building });
    dialog.close(); await refreshProjects(); await selectProject(result.project_id);
  }, e.submitter); };
}
async function refreshProjects() { state.projects = await request('/projects'); }
async function selectProject(id) {
  clearTimeout(pollTimer);
  const token = ++selection;
  const [p, ev, runs, gate] = await Promise.all([request('/projects/' + id), request('/projects/' + id + '/evidence'), request('/projects/' + id + '/runs'), request('/projects/' + id + '/gate')]);
  if (token !== selection) return;
  const sameProject = state.project?.project_id === id;
  Object.assign(state, { project: p, evidence: ev, runs, gate, selectedRun: null, comparedIds: [], view: sameProject ? state.view : 'readiness' });
  renderProject();
  schedulePoll();
}
function switchView(view) {
  state.view = view;
  document.querySelectorAll('.work-view').forEach(el => { el.hidden = el.id !== view; });
  document.querySelectorAll('[data-view]').forEach(el => el.classList.toggle('selected', el.dataset.view === view));
}
function renderProject() {
  const p = state.project;
  shell();
  document.querySelector('#workspace').innerHTML = projectView(state);
  document.querySelectorAll('[data-view]').forEach(b => { b.onclick = () => switchView(b.dataset.view); });
  const inspector = document.querySelector('.inspector');
  document.querySelector('#toggle-inspector').onclick = () => { inspector.hidden = !inspector.hidden; };
  document.querySelector('#close-inspector').onclick = () => { inspector.hidden = true; };
  document.querySelector('#edit-building').onclick = () => projectForm(true);
  document.querySelector('#task-import').onclick = evidenceForm;
  document.querySelector('#composer-upload').onclick = evidenceForm;
  document.querySelector('#task-next').onclick = () => switchView(state.gate.can_simulate ? 'simulation' : 'evidence');
  document.querySelector('#task-command').onsubmit = e => { e.preventDefault(); const input = document.querySelector('#command'); const text = input.value.trim(); if (!text) return; action(async () => {
    if (/导入|上传/.test(text)) { evidenceForm(); return; }
    if (/仿真|计算|运行|比较/.test(text)) { switchView('simulation'); notice('请选择方案与因子，再提交计算或比较。'); return; }
    if (/报告|依据|追溯/.test(text)) { switchView('trace'); return; }
    if (/资料|证据|检查|缺/.test(text)) { state.gate = await request('/projects/'+state.project.project_id+'/gate'); document.querySelector('#task-response').innerHTML = '<div class="task-reply"><strong>资料检查完成</strong><p>'+esc(state.gate.can_simulate ? '已满足仿真准入。模型适用性和方案稳定性仍需复核。' : state.gate.blockers.map(b => b.message+'；'+b.action).join('。'))+'</p><button id="response-evidence">查看项目资料</button></div>'; document.querySelector('#response-evidence').onclick = () => switchView('evidence'); input.value = ''; return; }
    notice('当前支持检查资料、导入资料、前往仿真和查看报告。自由对话尚未接通。');
  }, e.submitter); };
  document.querySelector('#add-evidence').onclick = evidenceForm;
  document.querySelector('#review-pending').onclick = () => reviewForm(state.evidence.filter(e => ['idf', 'epw'].includes(e.type) && e.review_state === 'pending'));
  document.querySelector('#run').onclick = e => action(async () => { const run = await post('/runs', { project_id: p.project_id, scheme_id: document.querySelector('#scheme').value, factor_profile_id: document.querySelector('#factor').value }); notice('已排队：' + run.run_id); await refreshRuns(); schedulePoll(); }, e.currentTarget);
  document.querySelector('#compare').onclick = e => action(async () => {
    const latest = latestSchemes(state.runs);
    const token = selection;
    const data = await post('/comparisons', { run_ids: latest.map(r => r.run_id) });
    if (token !== selection) return;
    state.comparedIds = latest.map(r => r.run_id);
    document.querySelector('#comparison').innerHTML = '<div class="comparison"><h3>当前能耗排序：' + data.energy_order.map(esc).join(' → ') + '</h3><p>' + esc(data.note) + '</p><table><thead><tr><th>方案</th><th>节能率</th><th>工程 CO₂ 差值</th><th>综合推荐</th></tr></thead><tbody>' + data.results.map(r => '<tr><td>' + esc(r.scheme_id) + '</td><td>' + num(r.saving_rate_pct) + '%</td><td>' + num(r.engineering_reduction_kg) + ' kg</td><td>证据不足</td></tr>').join('') + '</tbody></table></div>';
  }, e.currentTarget);
  renderEvidence(); renderRuns(); switchView(state.view);
}
function renderEvidence() {
  document.querySelector('#evidence-table').innerHTML = state.evidence.length ? '<div class="table-scroll"><table><thead><tr><th>来源 / 证据</th><th>性质</th><th>人工复核</th><th>版本</th><th></th></tr></thead><tbody>' + state.evidence.map(e => '<tr><td><button class="text-button" data-evidence="' + e.evidence_id + '">' + esc(e.name) + '</button><small>' + esc(e.type.toUpperCase()) + (e.scheme_id ? ' · ' + esc(e.scheme_id) : '') + '</small></td><td>' + badge(e.status) + '</td><td>' + badge({ pending: '待确认', confirmed: '已确认', rejected: '已拒绝' }[e.review_state], e.review_state === 'confirmed' ? 'success' : 'warning') + '</td><td>v' + e.revision + '</td><td><button data-evidence="' + e.evidence_id + '">查看 →</button></td></tr>').join('') + '</tbody></table></div>' : '<div class="empty">尚无证据。上传原文件并登记来源定位，保留每一版资料。</div>';
  document.querySelectorAll('[data-evidence]').forEach(b => { b.onclick = () => evidenceDetail(state.evidence.find(e => e.evidence_id === b.dataset.evidence)); });
}
function evidenceDetail(ev) {
  const content = Object.entries(ev).map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(typeof v === 'object' ? JSON.stringify(v) : v ?? '—') + '</dd>').join('');
  const dialog = modal('证据来源 · ' + esc(ev.name), '<dl class="metadata">' + content + '</dl>' + (ev.source_file ? link('/api/projects/' + ev.project_id + '/files/' + ev.source_file, '下载原文件') : '') + '<div class="actions"><button id="review-this">更改复核状态</button><button id="history">查看版本历史</button></div><div id="history-content"></div>');
  document.querySelector('#review-this').onclick = () => { dialog.close(); reviewForm([ev]); };
  document.querySelector('#history').onclick = e => action(async () => { const history = await request('/projects/' + ev.project_id + '/evidence/' + ev.evidence_id + '/history'); document.querySelector('#history-content').innerHTML = '<pre>' + esc(JSON.stringify(history, null, 2)) + '</pre>'; }, e.currentTarget);
}
function reviewForm(items) {
  if (!items.length) { notice('没有待确认模型；可点击单条证据调整复核状态。'); return; }
  const dialog = modal('人工复核 · ' + items.length + ' 份证据', '<form id="review-form"><p class="form-note">请先查看原文件，确认模型/天气属于此项目，版本、位置、运行范围和面积声明一致。参考模型仅用于演示验证。确认不改变其 IMPORTED / ASSUMED 属性。</p><ul>' + items.map(e => '<li>' + esc(e.name) + ' · v' + e.revision + '</li>').join('') + '</ul><label>复核人<input name="person" required maxlength="100"></label><label>处理<select name="state"><option value="confirmed">确认用于当前项目计算</option><option value="pending">撤回确认，重新待审</option><option value="rejected">拒绝此证据版本</option></select></label><label>复核依据 / 限制<textarea name="note" required minlength="5" maxlength="2000" placeholder="说明你核对的文件、范围及仍未解决的不确定性"></textarea></label><button class="primary" type="submit">保存复核记录</button></form>');
  document.querySelector('#review-form').onsubmit = e => { e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); action(async () => { for (const item of items) await request('/projects/' + item.project_id + '/evidence/' + item.evidence_id, { method: 'PATCH', body: JSON.stringify({ expected_revision: item.revision, review_state: data.state, responsible_person: data.person, review_note: data.note }) }); dialog.close(); await selectProject(state.project.project_id); notice('已保存独立复核版本。受影响的旧运行会显示失效。'); }, e.submitter); };
}
function evidenceForm() {
  const dialog = modal('导入资料与登记来源', '<form id="evidence-form"><p class="form-note">PDF / 图片 / Excel 当前保存原文件并人工登记定位；尚未启用 OCR 或自动识别。IDF 目前要求 9.0 版本及原生 SQL 汇总输出。</p><label>文件（最大 20 MB）<input type="file" name="file" required accept=".idf,.epw,.pdf,.csv,.xlsx,.xls,.png,.jpg,.jpeg,.ifc,.json,.xml"></label><div class="form-grid"><label>证据类型<select name="type"><option value="idf">IDF 模型</option><option value="epw">EPW 天气</option><option value="drawing">图纸</option><option value="bill">能耗账单</option><option value="equipment_table">设备台账</option><option value="bim">BIM</option><option value="literature">文献</option><option value="sensor">传感器记录</option></select></label><label>IDF 方案<select name="scheme"><option value="baseline">baseline</option><option value="R1">R1</option><option value="R2">R2</option></select></label></div><label>来源定位<input name="locator" required placeholder="例如：A-17 第 2 页 / CSV 行 15 / IDF 对象名称"></label><label>来源与权威性<input name="authority" required placeholder="文件提供单位、版本和日期"></label><label>使用授权 / 许可<input name="permission" required placeholder="业主授权范围或开源许可来源"></label><label>登记人<input name="person" required></label><label>不确定性说明<textarea name="uncertainty"></textarea></label><button class="primary" type="submit">保存文件和证据记录</button></form>');
  document.querySelector('#evidence-form').onsubmit = e => { e.preventDefault(); const data = new FormData(e.currentTarget); action(async () => {
    const form = new FormData(); form.append('file', data.get('file'));
    const file = await request('/projects/' + state.project.project_id + '/files', { method: 'POST', body: form });
    await post('/projects/' + state.project.project_id + '/evidence', { type: data.get('type'), name: file.name, source_file: file.file_id, source_locator: data.get('locator'), authority: data.get('authority'), permission: data.get('permission'), responsible_person: data.get('person'), acquisition_method: 'manual_upload', status: 'IMPORTED', uncertainty: data.get('uncertainty') || null, scheme_id: data.get('type') === 'idf' ? data.get('scheme') : null });
    dialog.close(); await selectProject(state.project.project_id);
  }, e.submitter); };
}
function renderRuns() {
  const target = document.querySelector('#runs'); if (!target) return;
  target.innerHTML = state.runs.length ? '<div class="table-scroll"><table><thead><tr><th>方案 / run_id</th><th>状态</th><th>年能耗 kWh</th><th>EUI</th><th>运行 CO₂ kg</th><th>依据</th></tr></thead><tbody>' + state.runs.map(r => '<tr><td><strong>' + esc(r.scheme_id) + '</strong><small class="mono">' + esc(r.run_id.slice(0, 16)) + '…</small></td><td>' + badge(label[r.status], r.status === 'succeeded' ? 'success' : 'warning') + (r.warnings_count ? '<small>' + r.warnings_count + ' warnings · 待复核</small>' : '') + (r.error ? '<small class="error-text">' + esc(r.error) + '</small>' : '') + (r.stale_reasons?.length ? '<small class="error-text">' + r.stale_reasons.map(esc).join('；') + '</small>' : '') + '</td><td class="numeric">' + num(resultValue(r, 'annual_energy_kwh')) + '</td><td class="numeric">' + num(resultValue(r, 'eui_kwh_m2a')) + '</td><td class="numeric">' + num(r.status === 'succeeded' ? r.carbon?.operating_carbon_kg : null) + (r.carbon?.scenario ? '<small>教学情景</small>' : '') + '</td><td><button data-trace="' + r.run_id + '">查看依据</button></td></tr>').join('') + '</tbody></table></div>' : '<div class="empty">未计算 · 没有历史数值补位</div>';
  document.querySelectorAll('[data-trace]').forEach(b => { b.onclick = () => action(() => trace(b.dataset.trace)); });
}
function graphMarkup(nodes) {
  const node = n => '<button class="graph-node ' + n.state.toLowerCase() + '" data-node="' + n.id + '"><small>' + esc(n.kind) + ' · ' + esc(n.state) + '</small><strong>' + esc(n.label) + '</strong></button>';
  const inputs = '<div class="graph-inputs">' + nodes.filter(n => n.kind === 'Evidence').map(node).join('') + '</div>';
  return [inputs, ...nodes.filter(n => n.kind !== 'Evidence').map(node)].join('<span class="graph-arrow">→</span>');
}
async function trace(id, scroll = true) {
  state.selectedRun = id;
  const report = await request('/runs/' + id + '/report.json');
  const r = report.run;
  document.querySelector('#trace-content').className = 'trace-content';
  document.querySelector('#trace-content').innerHTML = '<div class="trace-heading"><strong class="mono">' + esc(id) + '</strong>' + badge(label[r.status]) + '</div><div class="graph">' + graphMarkup(report.claims.nodes) + '</div><div class="report-actions">' + link('/api/runs/' + id + '/report.json', '完整 JSON') + link('/api/runs/' + id + '/report.html', '证据报告') + link('/api/runs/' + id + '/report.pdf', '下载 PDF') + link('/api/runs/' + id + '/artifacts', '原始证据 ZIP') + '</div><div class="certificate"><p class="eyebrow">DECISION CERTIFICATE · DRAFT</p><h3>当前拒绝给出确定最优推荐</h3><p>状态：' + esc(report.certificate.status) + ' · 工程师未签署</p><p>成立条件：当前输入适用；失效条件：证据、模型、代码或引擎版本变化。</p><p>尚未排除：模型偏差、舒适性问题、方案翻转风险。建议先复核 Warning，再补充账单和运行时段。</p></div><details><summary>完整版本、SQL 来源定位及未满足设定点时间</summary><pre>' + esc(JSON.stringify({ provenance: r.provenance, metrics: r.metrics, evidence: report.evidence, limitations: r.limitations }, null, 2)) + '</pre></details>';
  document.querySelectorAll('[data-node]').forEach(b => { b.onclick = () => { const ev = report.evidence.find(e => e.evidence_id === b.dataset.node); if (ev) evidenceDetail(ev); else notice('该节点依赖与原始 SQL 定位见下方完整版本信息。'); }; });
  if (scroll) switchView('trace');
}
async function refreshRuns() {
  if (!state.project) return;
  const id = state.project.project_id, token = selection;
  const runs = await request('/projects/' + id + '/runs');
  if (token !== selection) return;
  const old = state.runs.find(r => r.run_id === state.selectedRun);
  const current = runs.find(r => r.run_id === state.selectedRun);
  if (JSON.stringify(state.runs) !== JSON.stringify(runs)) {
    state.runs = runs;
    renderRuns();
  }
  const health = document.querySelector('#simulation-health');
  const healthText = runs.some(r => r.status === 'running') ? '仿真中' : runs.length ? '见运行记录' : '未计算';
  if (health && health.textContent !== healthText) health.textContent = healthText;
  if (current && old && JSON.stringify(current) !== JSON.stringify(old)) await trace(current.run_id, false);
  const comparison = document.querySelector('#comparison');
  if (comparison && !comparisonIsCurrent(runs, state.comparedIds)) {
    comparison.innerHTML = '';
    state.comparedIds = [];
  }
}
function schedulePoll() {
  clearTimeout(pollTimer);
  if (!state.project) return;
  pollTimer = setTimeout(async () => { try { await refreshRuns(); schedulePoll(); } catch (err) { notice(err.message, true); } }, 3000);
}
function clearSession() {
  selection++; clearTimeout(pollTimer); setCsrfToken('');
  Object.assign(state, {user:null, projects:[], project:null, evidence:[], runs:[], selectedRun:null, comparedIds:[]});
}
async function enterWorkspace(session) {
  state.user = session.user; setCsrfToken(session.csrf_token);
  [state.health, state.profiles] = await Promise.all([request('/health'), request('/factor-profiles')]);
  await refreshProjects(); home();
}
function authScreen(setup, register = false) {
  root.innerHTML = authView({setup, register});
  const toggle = document.querySelector('#switch-auth'); if (toggle) toggle.onclick = () => authScreen(false, !register);
  document.querySelector('#show-password').onclick = e => { const password = document.querySelector('#password'); password.type = password.type === 'password' ? 'text' : 'password'; e.currentTarget.textContent = password.type === 'password' ? '显示' : '隐藏'; e.currentTarget.setAttribute('aria-label', password.type === 'password' ? '显示密码' : '隐藏密码'); };
  document.querySelector('#auth-form').onsubmit = async e => {
    e.preventDefault(); const button=e.submitter, error=document.querySelector('#auth-error');
    button.disabled=true; error.hidden=true;
    try { const body=Object.fromEntries(new FormData(e.currentTarget)); const session=await post('/auth/'+(setup||register?'register':'login'),body); await enterWorkspace(session); }
    catch (err) { error.textContent=err.message; error.hidden=false; button.disabled=false; }
  };
}
document.addEventListener('session-expired', () => { clearSession(); authScreen(false); });
document.addEventListener('keydown', e => {
  if (!state.user || document.querySelector('dialog[open]')) return;
  if ((e.ctrlKey || e.metaKey) && ['k','n'].includes(e.key.toLowerCase())) { e.preventDefault(); if (e.key.toLowerCase()==='k') searchProjects(); else projectForm(); }
});
document.documentElement.dataset.theme = localStorage.getItem('vra-theme') || 'light';
root.innerHTML = '<div class="boot-screen">稀土智暖 <span>正在打开工作区…</span></div>';
(async () => { try { const status=await request('/auth/status'); if (status.setup_required) { authScreen(true); return; } try { await enterWorkspace(await request('/auth/me')); } catch(err) { if(err.status===401) authScreen(false); else throw err; } } catch(err) { root.innerHTML='<div class="boot-screen"><strong>暂时无法连接工作区</strong><p>'+esc(err.message)+'</p><button id="retry-connection">重试</button></div>'; document.querySelector('#retry-connection').onclick=()=>location.reload(); } })();
