import './style.css';
import { request, post, escape as esc, number as num, latestSchemes, resultValue, comparisonIsCurrent } from './api.js';

const root = document.querySelector('#app');
const state = { projects: [], project: null, evidence: [], runs: [], gate: null, profiles: {}, health: null, selectedRun: null, comparedIds: [] };
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
  root.innerHTML = '<header><a class="brand" href="/"><span class="brandmark">V</span><strong>稀土智暖 <small>VRA-Trust</small></strong></a><div class="header-right"><span class="live-dot"></span>本地工程工作区 <span class="divider"></span><span id="engine-health">连接中</span></div></header><div id="workspace"></div><div id="toast" class="toast" role="status" hidden></div><dialog id="dialog"></dialog>';
}
function home() {
  document.querySelector('#workspace').innerHTML = '<main class="home"><p class="eyebrow">EVIDENCE-AWARE ENGINEERING DECISIONS</p><h1>让每个建筑节能决策<br>都有<span>证据。</span></h1><p class="intro">从不完整资料，到可复核的工程判断。<br>知道依据是什么，也知道什么时候还不能下结论。</p><div class="actions"><button class="primary" id="create-project">创建项目 <span>＋</span></button><button id="reference-project">导入官方参考模型</button></div><p class="subtle">参考输入将单独建档、人工确认并重新仿真，不加载历史结果。</p><section class="project-list"><div class="section-title"><h2>项目工作区</h2><span>' + state.projects.length + ' PROJECTS</span></div><div id="projects"></div></section><div class="principles"><span>01 可复核</span><span>02 可拒答</span><span>03 可补证</span><span>04 可重放</span></div></main>';
  document.querySelector('#projects').innerHTML = state.projects.length ? state.projects.map(p => '<button class="project-row" data-project="' + p.project_id + '"><span><strong>' + esc(p.name) + '</strong><small>' + esc(p.building.location) + ' · ' + num(p.building.area_m2) + ' m² · ' + esc(p.project_id.slice(-6)) + '</small></span>' + badge(p.data_nature === 'engineering_reference' ? 'REFERENCE · 非实测' : '用户项目') + '<span>进入工作区 →</span></button>').join('') : '<div class="empty"><strong>从一份资料开始</strong><p>创建项目后，导入 IDF、天气及工程资料。系统会先检查是否具备计算条件。</p></div>';
  document.querySelector('#create-project').onclick = () => projectForm();
  document.querySelector('#reference-project').onclick = e => action(async () => { const p = await post('/reference-projects', {}); await refreshProjects(); await selectProject(p.project_id); notice('已导入 4 份参考输入，等待人工确认；尚未产生计算结果。'); }, e.currentTarget);
  document.querySelectorAll('[data-project]').forEach(b => { b.onclick = () => action(() => selectProject(b.dataset.project)); });
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
  Object.assign(state, { project: p, evidence: ev, runs, gate, selectedRun: null, comparedIds: [] });
  renderProject();
  schedulePoll();
}
function renderProject() {
  const p = state.project, ready = state.gate.can_simulate;
  document.querySelector('#workspace').innerHTML = '<div class="layout"><aside class="sidebar"><button class="back" id="all-projects">← 全部项目</button><p class="eyebrow">PROJECT</p><h2>' + esc(p.name) + '</h2>' + badge(p.data_nature === 'engineering_reference' ? 'REFERENCE · 非实测' : '用户项目') + '<nav><a href="#readiness">◉ 项目准入</a><a href="#evidence">▤ 证据清单 <small>' + state.evidence.length + '</small></a><a href="#simulation">↗ 仿真与结果</a><a href="#trace">◇ 依据追溯</a></nav><div class="sidebar-foot">PROJECT REVISION ' + p.revision + '<p>' + esc(p.building.location) + '<br>' + num(p.building.area_m2) + ' m²</p><button id="edit-building">修订建筑声明</button><p class="subtle">Agent、反例搜索与空间证据界面尚未接通。本页不生成推测结论。</p></div></aside><main class="project-main"><div class="breadcrumbs">工程工作区 / ' + esc(p.building.use) + '</div><section id="readiness"><div class="section-title"><div><p class="eyebrow">PROJECT READINESS</p><h1>现在，能下结论吗？</h1></div>' + badge('尚不能确定推荐', 'warning') + '</div><div class="readiness-banner"><span class="status-symbol">' + (ready ? '↗' : '!') + '</span><div><h2>' + (ready ? '资料已满足仿真准入' : '先补齐关键证据') + '</h2><p>' + (ready ? '可以进行真实计算。模型适用性、舒适性与决策稳定性仍需复核。' : '系统暂不发布能耗或方案推荐。以下缺口决定下一步工作。') + '</p></div></div><div class="readiness-grid"><div><small>关键输入</small><strong>' + (ready ? '已人工确认' : '待确认') + '</strong></div><div><small>仿真健康</small><strong id="simulation-health">' + (state.runs.length ? '见运行记录' : '未计算') + '</strong></div><div><small>决策稳定性</small><strong>未评估</strong></div><div><small>工程师签署</small><strong>未签署</strong></div></div><div id="gaps">' + (state.gate.blockers.map(b => '<div class="gap"><span class="warning-dot"></span><div><strong>' + esc(b.message) + '</strong><p>' + esc(b.action) + '</p></div>' + badge(b.field.toUpperCase()) + '</div>').join('') || '<p class="subtle">准入检查通过不意味着已证明模型准确。所有数值仍需计算及输出核验。</p>') + '</div></section><section id="evidence"><div class="section-title"><div><p class="eyebrow">EVIDENCE MANIFEST</p><h2>每一项输入，都有出处</h2></div><button id="add-evidence">＋ 导入资料</button></div><div id="evidence-table"></div><button id="review-pending" class="text-button">人工确认待审模型与天气 →</button></section><section id="simulation"><div class="section-title"><div><p class="eyebrow">PHYSICS TOOL LAYER</p><h2>真实计算，独立运行</h2></div><span class="subtle">EnergyPlus 9.0.1</span></div><div class="run-controls"><label>方案<select id="scheme"><option value="baseline">baseline · 基准</option><option value="R1">R1 · 候选方案</option><option value="R2">R2 · 候选方案</option></select></label><label>运行碳因子<select id="factor">' + Object.entries(state.profiles).map(([key]) => '<option value="' + esc(key) + '">' + esc(key === 'none' ? '不计算碳排（无适用因子）' : key === 'reference_scenario' ? '教学因子情景 · 非正式核算' : key) + '</option>').join('') + '</select></label><button id="run" class="primary">提交真实仿真 ↗</button><button id="compare">比较最近三方案</button></div><p class="subtle">每次提交保留独立输入快照和原始输出。计算失败后数值保持为空。</p><div id="runs"></div><div id="comparison"></div></section><section id="trace"><p class="eyebrow">WHY THIS RESULT?</p><h2>沿着证据，追到结果</h2><div id="trace-content" class="empty">选择运行记录中的“查看依据”，展开输入与计算依赖。</div><p class="subtle">当前为运行级依赖视图；完整 Claim DAG、选择性重算及稳定性证明仍待后续阶段。</p></section></main></div>';
  document.querySelector('#all-projects').onclick = () => { selection++; clearTimeout(pollTimer); state.project = null; action(async () => { await refreshProjects(); home(); }); };
  document.querySelector('#edit-building').onclick = () => projectForm(true);
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
  renderEvidence(); renderRuns();
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
  if (scroll) document.querySelector('#trace').scrollIntoView({ behavior: 'smooth', block: 'start' });
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
shell();
action(async () => { [state.health, state.profiles] = await Promise.all([request('/health'), request('/factor-profiles')]); document.querySelector('#engine-health').textContent = state.health.engine_available ? 'EnergyPlus 已连接' : 'EnergyPlus 未配置'; await refreshProjects(); home(); });
