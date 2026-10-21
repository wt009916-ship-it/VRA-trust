import { workflowMarkup } from './trust-ui.js';
import { escape as esc, number as num } from './api.js';

const paths = {
  plus:'M12 5v14M5 12h14', search:'m21 21-4.3-4.3M19 10.5a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0',
  folder:'M3 7V5h6l2 2h10v13H3Z', panel:'M3 4h18v16H3ZM9 4v16',
  arrow:'M12 19V5m-6 6 6-6 6 6', chevron:'m9 5 7 7-7 7',
  file:'M14 2H5v20h14V7ZM14 2v6h5M8 13h8M8 17h6',
  run:'m8 4 12 8-12 8Z', check:'m5 12 4 4L19 6',
  layers:'m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5',
  moon:'M20 14A9 9 0 0 1 10 4a9 9 0 1 0 10 10',
  sun:'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  exit:'M9 3H4v18h5M10 12h11m-4-4 4 4-4 4',
  dots:'M5 12h.01M12 12h.01M19 12h.01', bolt:'m13 2-9 12h7l-1 8 10-12h-7Z',
};
export const icon = (name) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+(paths[name] || paths.file)+'"/></svg>';
export const mark = '<span class="brandmark">'+icon('layers')+'</span>';

export function appShell(state) {
  const p = state.project;
  return `<div class="app-frame"><aside class="app-sidebar"><a class="brand" href="/">${mark}<span>稀土智暖 <small>VRA-Trust</small></span></a>
    <button class="nav-action" id="new-project">${icon('plus')}<span>新建项目</span><kbd>⌘ N</kbd></button>
    <button class="nav-action" id="search-projects">${icon('search')}<span>搜索项目</span><kbd>⌘ K</kbd></button>
    <button class="nav-action ${!p?'active':''}" id="all-projects">${icon('panel')}<span>工作台</span></button>
    <div class="sidebar-label">项目 <span>${state.projects.length}</span></div><div class="sidebar-projects">${state.projects.map(item=>`<button class="sidebar-project ${item.project_id===p?.project_id?'active':''}" data-project="${item.project_id}" title="${esc(item.name)}">${icon('folder')}<span>${esc(item.name)}</span>${item.data_nature==='engineering_reference'?'<i>示例</i>':''}</button>`).join('')||'<p class="sidebar-empty">你的项目会显示在这里</p>'}</div>
    <button class="nav-action subtle-action" id="load-reference">${icon('layers')}<span>探索参考项目</span></button>
    ${state.user.is_admin?'<button class="nav-action" id="developer-settings">'+icon('dots')+'<span>开发者设置</span></button>':''}<div class="account-row"><span class="avatar">${esc(state.user.display_name.slice(0,1))}</span><span class="account-name">${esc(state.user.display_name)}<small>本地工作区</small></span><button class="icon-button" id="theme-toggle" aria-label="切换明暗主题">${icon('moon')}</button><button class="icon-button" id="logout" aria-label="退出登录">${icon('exit')}</button></div></aside>
    <div class="app-body"><header class="topbar"><button id="toggle-sidebar" class="icon-button" aria-label="展开或收起侧栏">${icon('panel')}</button><div class="breadcrumb">${p?`<span>项目</span><span class="slash">/</span><strong>${esc(p.name)}</strong>`:'<strong>工作台</strong>'}</div><div class="topbar-end"><span class="engine-indicator"><i class="${state.health?.engine_available?'online':''}"></i>${state.health?.engine_available?'引擎就绪':'引擎未连接'}</span>${p?'<button id="toggle-inspector" class="icon-button" aria-label="查看项目详情">'+icon('file')+'</button>':''}</div></header><div id="workspace"></div></div></div><div id="toast" class="toast" role="status" hidden></div><dialog id="dialog"></dialog>`;
}

export function homeView(state) {
  const entries = [
    ['weather','sun','气候与天气','NASA 历史资料 · EPW 检查'],
    ['spatial','layers','空间与建模','图纸 / PDF / IFC · 空间复核'],
    ['simulation','bolt','仿真与比较','EnergyPlus · 原始结果'],
    ['decision','file','材料与决策','参数证据 · 方案研究'],
  ];
  return `<main class="home home-dense">
    <div class="studio-welcome"><span class="eyebrow">BUILDING PERFORMANCE STUDIO</span><span class="workspace-label"><i></i>${state.projects.length} 个项目在工作区</span></div>
    <div class="home-hero">
      <div class="home-hero-copy"><div class="home-intro"><p class="greeting">稀土智暖 · VRA-Trust</p><h1>建筑改造<span class="title-accent">工作台</span></h1><p class="home-subtitle">整理资料、复核模型、运行仿真，让每个结果都有据可查。</p></div>
        <form class="composer home-composer" id="intake-composer"><label class="sr-only" for="project-intent">项目名称或描述</label><input id="project-intent" placeholder="输入项目名称，开始新的分析…" maxlength="160"><button type="submit" class="primary">${icon('plus')}新建项目</button></form>
        <div class="starter-actions"><button id="reference-project">${icon('layers')}体验官方参考项目</button><button id="how-it-works">${icon('file')}查看操作流程</button></div>
      </div>
      <div class="building-visual" aria-label="建筑分析流程示意"><div class="visual-label"><span>BUILDING / PERSPECTIVE</span></div>${studioDrawing()}<div class="visual-caption"><strong>一栋建筑，多维度理解。</strong><span>气候 · 空间 · 能耗 · 材料</span></div><span class="visual-note">概念插画 · 非项目模型</span></div>
    </div>
    <section class="home-tools"><div class="section-title"><h2>常用工作入口</h2><span>${state.projects.length?'选择入口后进入对应项目':'先建项目，再接入工程资料'}</span></div><div class="studio-capabilities">${entries.map(([view,symbol,title,text],i)=>`<button class="capability-entry" data-entry-view="${view}" data-entry-title="${title}"><span class="capability-icon">${icon(symbol)}</span><span class="capability-copy"><strong>${title}</strong><small>${text}</small></span><span class="capability-number">0${i+1} ↗</span></button>`).join('')}</div></section>
    <div class="home-content-grid"><section class="recent"><div class="section-title"><h2>项目空间 <small>${state.projects.length}</small></h2><button id="browse-projects" class="text-button">查看全部 ${icon('chevron')}</button></div>
      <div class="recent-grid">${state.projects.slice(0,5).map(p=>`<button class="recent-project" data-project="${p.project_id}"><span class="recent-icon">${icon('folder')}</span><span class="recent-project-copy"><strong>${esc(p.name)}</strong><small>${esc(p.building.location)} · ${num(p.building.area_m2)} m²</small><em>${p.data_nature==='engineering_reference'?'官方参考 · 非实测':'工程项目'} · 声明 v${p.revision}</em></span>${icon('chevron')}</button>`).join('')||'<div class="home-empty"><strong>开始你的第一个建筑项目</strong><p>登记建筑地点、用途与面积，再补充图纸和天气资料。</p><button class="primary" id="empty-create-project">创建工程项目</button></div>'}</div>
      <div class="project-list-footer"><span>建筑声明、资料和计算结果按项目保存</span><button id="create-project">${icon('plus')}新建</button></div>
      <div class="home-preparation"><strong>开始前准备好</strong><span>建筑基本信息</span><span>图纸或已有模型</span><span>天气与参数来源</span></div>
    </section>${workflowMarkup()}</div>
    <p class="home-footnote">有依据的计算，有边界的建议。</p>
  </main>`;
}

function studioDrawing() {
  return `<svg viewBox="0 0 430 330" class="studio-drawing" aria-hidden="true">
    <g class="drawing-guides" fill="none" stroke="currentColor" stroke-width=".8"><path d="m30 222 186-98 185 98-185 98ZM58 177 216 94 374 177M58 132 216 49 374 132"/><path d="M58 132v90M374 132v90M216 49v56" stroke-dasharray="3 5"/><circle cx="216" cy="222" r="101" transform="translate(0 102) scale(1 .54)"/><path d="M27 295h34m-17-17v34M365 53h28m-14-14v28"/></g>
    <path d="m88 232 133-70 142 71-134 71Z" class="drawing-shadow"/>
    <g stroke-linejoin="round"><path d="m99 219 117-62 127 63-115 63Z" class="drawing-slab"/><path d="m114 126 114 58v89l-114-58Z" class="drawing-wall"/><path d="m228 184 102-56v89l-102 56Z" class="drawing-glass"/>
      <g class="drawing-windows"><path d="m124 142 24 12v18l-24-12Zm35 18 24 12v18l-24-12Zm35 18 24 12v18l-24-12ZM124 174l24 12v18l-24-12Zm35 18 24 12v18l-24-12Zm35 18 24 12v18l-24-12ZM124 206l24 12v17l-24-12Zm35 18 24 12v17l-24-12Zm35 18 24 12v17l-24-12Z"/></g>
      <path d="m265 165 23-13v83l-23 13Z" class="drawing-warm-glass"/>
      <path d="m109 154 119 61 107-59v6l-107 59-119-61Zm0 32 119 61 107-59v6l-107 59-119-61Z" class="drawing-slab"/>
      <path d="M249 173v88m20-99v88m20-99v88m20-99v88" class="drawing-mullions"/>
      <path d="m108 124 108-59 120 61-108 60Z" class="drawing-roof"/><path d="m108 124 120 62 108-60v6l-108 60-120-62Z" class="drawing-slab"/>
      <path d="m131 122 84-46 97 50-84 46Z" class="drawing-roof-inset"/>
      <path d="m152 106 48-26 43 22-48 26Z" class="drawing-solar"/><path d="m168 97 43 22m-27-31 43 22m-61 3 48-26m-34 33 48-26" class="drawing-solar-grid"/>
      <path d="m243 132 32-18 21 11-32 18Z" class="drawing-planter"/><path d="m243 132 21 11 32-18v7l-32 18-21-11Z" class="drawing-planter-edge"/>
      <path d="M261 131v-16m17 8v-17" class="drawing-tree-trunks"/><ellipse cx="261" cy="111" rx="9" ry="12" class="drawing-tree"/><ellipse cx="278" cy="103" rx="8" ry="11" class="drawing-tree"/>
    </g>
    <g class="drawing-annotations" fill="none" stroke="currentColor" stroke-width=".9"><path d="M147 95 106 73H51m248 99 44-25h41M161 240l-48 27H57" stroke-dasharray="3 4"/><circle cx="147" cy="95" r="3"/><circle cx="299" cy="172" r="3"/><circle cx="161" cy="240" r="3"/></g>
    <g class="drawing-labels" fill="currentColor"><text x="51" y="63">气候</text><text x="362" y="136">空间</text><text x="57" y="284">能耗</text></g>
  </svg>`;
}

export function projectView(state) {
  const p=state.project, ready=state.gate.can_simulate, pending=state.evidence.filter(e=>e.review_state==='pending').length;
  return `<div class="project-workspace"><div class="workspace-main"><nav class="view-tabs" aria-label="项目工作视图">${[['readiness','工作台'],['spatial','建模工作区'],['weather','气候与天气'],['evidence','资料'],['simulation','仿真'],['decision','材料与决策'],['robustness','反例与补证'],['trace','报告与依据']].map(([id,label])=>`<button data-view="${id}" class="${state.view===id?'selected':''}">${label}${id==='evidence'?'<span>'+state.evidence.length+'</span>':''}</button>`).join('')}</nav>
  <section class="work-view task-view" id="readiness"><div class="task-thread"><div class="task-title"><span class="eyebrow">${p.data_nature==='engineering_reference'?'官方参考 · 非实测':'工程项目'}</span><h1>${ready?'资料已就绪，可以开始计算。':'先把建筑资料准备好。'}</h1><p>${ready?'模型与天气已确认。运行后可以查看每个结果的原始依据。':'进入建模工作区生成模型，或导入已有 IDF；再确认天气与来源。'}</p></div>
  <div class="project-metrics">${projectMetricsMarkup(state)}</div>
  <div class="project-shortcuts">${[['spatial','layers','建立空间模型','导入图纸、PDF、IFC 等资料'],['weather','bolt','整理气候资料','获取公开气象 · 检查 EPW'],['decision','file','研究材料方案','参数证据 · 方案比较']].map(([view,symbol,title,text])=>`<button data-open-view="${view}"><span class="shortcut-icon">${icon(symbol)}</span><span><strong>${title}</strong><small>${text}</small></span>${icon('chevron')}</button>`).join('')}</div>
  <div class="assistant-message"><span class="message-mark">${icon('layers')}</span><div><strong>下一步 · 补齐输入与工程依据</strong><p>已登记 ${state.evidence.length} 份资料${pending?'，其中 '+pending+' 份等待人工确认':''}。</p>${state.gate.blockers.length?'<ul class="gap-list">'+state.gate.blockers.map(b=>'<li><strong>'+esc(b.message)+'</strong><span>'+esc(b.action)+'</span></li>').join('')+'</ul>':'<p class="inline-status">'+icon('check')+'关键输入通过准入检查</p>'}<div class="message-actions"><button id="task-import">${icon('plus')}导入资料</button><button id="task-next">${icon(ready?'run':'check')}${ready?'前往仿真':'查看并确认资料'}</button></div></div></div>
  <div id="task-response" aria-live="polite"></div><div class="decision-note">${icon('file')}<span>当前尚不能给出确定推荐。舒适性、模型适用性和方案稳定性仍需复核。</span></div></div>
  <form class="composer task-composer" id="task-command"><label class="sr-only" for="command">项目操作</label><textarea id="command" rows="2" placeholder="分析材料准入、补证优先级和方案取舍；AI Provider 需先配置 Key…"></textarea><div class="composer-bottom"><button type="button" class="composer-tool" id="composer-upload">${icon('plus')}资料</button><select id="agent-task" aria-label="任务类型"><option value="auto">自动任务</option><option value="weather">天气核对</option><option value="diagnose">工程诊断</option></select><select id="agent-mode" aria-label="执行模式"><option value="local">本地工程流程</option><option value="provider">AI Provider</option></select><label class="compute-opt"><input type="checkbox" id="allow-compute">允许计算</label><button class="send-button" type="submit" aria-label="执行项目操作">${icon('arrow')}</button></div></form></section>
  <section class="work-view" id="evidence" hidden><div class="view-heading"><div><h1>项目资料</h1><p>保留原文件与来源，确认后进入计算流程。</p></div><button class="primary" id="add-evidence">${icon('plus')}导入资料</button></div><div id="evidence-table"></div><div class="section-footer"><button id="review-pending">${icon('check')}确认待审模型与天气</button><span>确认操作会保留复核人和版本记录。</span></div></section>
  <section class="work-view" id="simulation" hidden><div class="view-heading"><div><h1>仿真与方案</h1><p>每次计算独立保存输入、结果和原始输出。</p></div><span id="simulation-health">${state.runs.length?'见运行记录':'未计算'}</span></div><div class="run-controls"><label>方案<select id="scheme"><option value="baseline">baseline · 基准</option><option value="R1">R1 · 候选方案</option><option value="R2">R2 · 候选方案</option></select></label><label>运行碳因子<select id="factor">${Object.keys(state.profiles).map(key=>`<option value="${esc(key)}">${esc(key==='none'?'暂不计算碳排':key==='reference_scenario'?'教学情景 · 非正式核算':key)}</option>`).join('')}</select></label><button id="run" class="primary">${icon('run')}运行仿真</button><button id="compare">比较最近三方案</button><button id="edit-factors">修改碳因子</button></div><div id="runs"></div><div id="comparison"></div></section>
  <section class="work-view" id="trace" hidden><div class="view-heading"><div><h1>报告与依据</h1><p>从结果回到输入，查看来源、版本和成立条件。</p></div></div><div id="trace-content" class="empty">请在仿真记录中选择“查看依据”。</div><p class="subtle">节点依赖、来源版本与选择性重算；报告为未签署草稿。</p></section><section class="work-view" id="decision" hidden></section><section class="work-view" id="robustness" hidden></section><section class="work-view" id="spatial" hidden></section><section class="work-view" id="weather" hidden></section></div>
  <aside class="inspector" hidden><div class="inspector-heading">项目详情<button id="close-inspector" class="icon-button" aria-label="关闭项目详情">×</button></div><div class="inspector-section"><span class="eyebrow">建筑</span><h3>${esc(p.building.use)}</h3><dl><dt>地点</dt><dd>${esc(p.building.location)}</dd><dt>建筑面积</dt><dd>${num(p.building.area_m2)} m²</dd><dt>声明版本</dt><dd>v${p.revision}</dd></dl><button id="edit-building">编辑建筑资料</button></div><div class="inspector-section"><span class="eyebrow">决策状态</span><dl><dt>仿真准入</dt><dd>${ready?'已满足':'待补齐'}</dd><dt>稳定性</dt><dd>未评估</dd><dt>工程师签署</dt><dd>未签署</dd></dl></div><div class="inspector-section"><span class="eyebrow">证据索引</span>${state.evidence.map(e=>`<button class="inspector-file" data-evidence="${e.evidence_id}">${icon('file')}<span>${esc(e.name)}<small>${e.review_state==='confirmed'?'已确认':'待复核'} · v${e.revision}</small></span></button>`).join('')||'<p class="subtle">尚未导入资料</p>'}</div></aside></div>`;
}

export function authView({setup=false, register=false}) {
  return `<div class="auth-page"><a class="brand auth-brand" href="/">${mark}<span>稀土智暖 <small>VRA-Trust</small></span></a><section class="auth-story"><span class="eyebrow">BUILDING PERFORMANCE STUDIO</span><h2>建筑的每一次改变，<br>都有迹可循。</h2><p>从天气与图纸开始，连接模型、计算与工程证据。</p>${studioDrawing()}<div class="auth-story-flow"><span>气候数据</span><b>→</b><span>空间建模</span><b>→</b><span>真实仿真</span><b>→</b><span>可复核决策</span></div></section><main class="auth-main"><div class="auth-heading"><span class="auth-emblem">${icon('layers')}</span><h1>${setup?'创建你的工作区':register?'创建账号':'欢迎回来'}</h1><p>${setup?'从一个账号开始，管理你的项目与工程证据。':register?'建立自己的建筑改造项目空间。':'登录，继续你的建筑改造项目。'}</p></div><form id="auth-form">${register||setup?'<label>怎么称呼你<input name="display_name" autocomplete="name" required maxlength="40" placeholder="你的名字"></label>':''}<label>用户名<input name="username" autocomplete="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_\\-]{3,32}" placeholder="字母、数字、下划线，3–32 位"></label><label>密码<div class="password-field"><input id="password" name="password" type="password" autocomplete="${register||setup?'new-password':'current-password'}" required minlength="10" maxlength="128" placeholder="至少 10 个字符"><button id="show-password" type="button" aria-label="显示密码">显示</button></div></label><p id="auth-error" role="alert" hidden></p><button type="submit" class="primary auth-submit">${setup?'创建工作区':register?'创建账号':'登录'}${icon('chevron')}</button></form>${setup?'<p class="auth-note">已有本机项目会归入这个首个账号。请妥善保存密码，当前不支持邮件找回。</p>':'<p class="auth-switch">'+(register?'已有账号？':'还没有账号？')+'<button id="switch-auth">'+(register?'登录':'创建账号')+'</button></p>'}<div class="auth-divider"></div><p class="auth-local">账号与项目保存在本机 · 密码不以明文保存</p></main><footer class="auth-footer">可复核 · 可拒答 · 可补证 · 可重放</footer></div><div id="toast" class="toast" role="status" hidden></div>`;
}

export function projectMetricsMarkup(state) {
  const p=state.project, ready=state.gate.can_simulate, pending=state.evidence.filter(e=>e.review_state==='pending').length;
  return `<article><span>建筑面积</span><strong>${num(p.building.area_m2,0)} <small>m²</small></strong><p>${esc(p.building.use)}</p></article><article><span>工程资料</span><strong>${state.evidence.length} <small>份</small></strong><p>${pending} 份待人工确认</p></article><article><span>仿真准入</span><strong class="status-word">${ready?'已就绪':'待补证'}</strong><p>${state.gate.blockers.length} 项当前阻断</p></article><article><span>有效仿真记录</span><strong>${state.runs.filter(r=>r.status==='succeeded').length} <small>次</small></strong><p>共 ${state.runs.length} 次运行记录</p></article>`;
}
