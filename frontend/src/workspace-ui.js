import { request, escape as esc, number as num } from './api.js';
import { createPoller } from './polling.js';

export const statusNames = { preparing:'待准备', review:'待复核', running:'计算中', queued:'排队中', succeeded:'已计算', failed:'计算失败', stale:'结果待更新', unavailable:'需检查' };
export function filterProjects(projects, {query='', filter='all', sort='updated'} = {}) {
  const q=query.trim().toLocaleLowerCase();
  const items=projects.filter(p=>(!q||[p.name,p.building.location,p.building.use,p.project_id].join(' ').toLocaleLowerCase().includes(q)) &&
    (filter==='all'||(filter==='attention'?(p.pending_count>0||['failed','stale','unavailable'].includes(p.status)):filter==='reference'?p.data_nature==='engineering_reference':p.status===filter)));
  return items.sort(sort==='name'?(a,b)=>a.name.localeCompare(b.name,'zh-CN'):sort==='area'?(a,b)=>b.building.area_m2-a.building.area_m2:(a,b)=>b.updated_at.localeCompare(a.updated_at));
}
export function dateLabel(value) {
  const date=new Date(value);return Number.isNaN(+date)?'—':date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
}
export function readRoute(hash) {
  const match=hash.match(/^#project\/(project_[a-f0-9]{32})\/(readiness|spatial|components|measurements|weather|evidence|simulation|decision|robustness|trace|review)$/);
  return match?{projectId:match[1],view:match[2]}:{projectId:null,view:hash==='#tasks'?'tasks':'projects'};
}
export function projectRows(projects, layout='list') {
  return projects.map(p=>`<article class="project-record ${layout==='grid'?'project-record-card':''}">
    <button class="project-record-title" data-open-project="${p.project_id}" aria-label="打开项目 ${esc(p.name)}"><span class="project-monogram">${esc(p.name.slice(0,1))}</span><span><strong>${esc(p.name)}</strong><small>${esc(p.building.location)} · ${esc(p.building.use)}${p.data_nature==='engineering_reference'?' · 官方参考':''}</small></span></button>
    <div class="project-record-area">${num(p.building.area_m2,0)} <small>m²</small><span>${p.evidence_count} 份资料 · ${p.run_count} 次运行</span></div>
    <div class="project-record-state"><span class="work-status ${esc(p.status)}">${statusNames[p.status]||'需检查'}</span><small>${dateLabel(p.updated_at)}</small></div>
    <button class="project-record-action" data-project-action="${p.project_id}" data-target-view="${p.next_action.view}">${esc(p.next_action.label)} <span>↗</span></button></article>`).join('');
}

export function mountWorkspace(host, {state, openProject, openIntake, reference, manual, tasks=false}) {
  let data=null, page=1, busy=false, prefs={query:'',filter:'all',sort:'updated',layout:'list'};
  try { const stored=JSON.parse(localStorage.getItem('vra-project-view')||'{}');for(const [k,values] of Object.entries({filter:['all','attention','running','succeeded','reference'],sort:['updated','name','area'],layout:['list','grid']}))if(values.includes(stored[k]))prefs[k]=stored[k]; } catch { /* Keep usable defaults when browser storage is unavailable. */ }
  host.innerHTML=`<main class="enterprise-workspace"><header class="workspace-heading"><div><span class="workspace-kicker">VRA / PROJECT OPERATIONS</span><h1>${tasks?'任务中心':'项目中心'}</h1><p>${esc(state.user.display_name)}，从当前项目和待办继续工作。</p></div><div class="workspace-heading-actions"><button id="workspace-refresh">刷新状态</button><button class="primary" id="workspace-new">＋ 导入项目资料</button></div></header>
    <div id="workspace-alert" role="status" hidden></div><section class="workspace-stats" id="workspace-stats" aria-label="工作区统计"><div>正在读取项目、资料和任务…</div></section>
    <div class="workspace-columns"><section class="workspace-projects"><header class="workspace-section-head"><div><h2>${tasks?'需要处理的任务':'全部项目'}</h2><span id="workspace-result-count">从数据库读取</span></div><div class="view-switch" aria-label="项目显示方式"><button data-layout="list" aria-label="列表视图">☷</button><button data-layout="grid" aria-label="卡片视图">▦</button></div></header>
      <div class="workspace-toolbar"><label class="workspace-search"><span>⌕</span><input id="workspace-query" type="search" placeholder="搜索名称、地点或建筑用途" aria-label="搜索项目"></label><select id="workspace-filter" aria-label="筛选项目状态"><option value="all">全部状态</option><option value="attention">需要处理</option><option value="running">计算中</option><option value="succeeded">已计算</option><option value="reference">参考项目</option></select><select id="workspace-sort" aria-label="项目排序"><option value="updated">最近更新</option><option value="name">项目名称</option><option value="area">建筑面积</option></select></div>
      <div id="workspace-records" class="workspace-records" aria-live="polite"><div class="workspace-loading">正在整理工作区…</div></div><footer class="workspace-pagination"><span id="workspace-page-label"></span><div><button id="workspace-previous">上一页</button><button id="workspace-next">下一页</button></div></footer>
    </section><aside class="workspace-right"><section class="workspace-panel"><header><h2>继续未完成的资料</h2><span id="workspace-intake-count">—</span></header><div id="workspace-intakes">正在读取…</div></section><section class="workspace-panel"><header><h2>项目动态</h2><small>最近 12 条</small></header><div id="workspace-activity">正在读取…</div></section><section class="workspace-start"><span class="workspace-kicker">GET STARTED</span><h2>从现有文件开始</h2><p>批量导入图纸、模型或天气，逐项核对提取结果。</p><div id="workspace-drop" tabindex="0" role="button" aria-label="拖入文件或选择项目资料">拖入文件 / 选择资料 <span>PDF · IFC · DXF · IDF · EPW</span></div><button id="workspace-manual">手动建立项目</button><button id="workspace-reference">打开官方参考流程 ↗</button></section></aside></div>
    <footer class="workspace-footer"><span id="workspace-updated">状态尚未同步</span><span>工程结果保留来源与版本</span></footer></main>`;
  const $=s=>host.querySelector(s);
  const persist=()=>{try{localStorage.setItem('vra-project-view',JSON.stringify({filter:prefs.filter,sort:prefs.sort,layout:prefs.layout}));}catch{/* Preferences are optional. */}};
  const open=(id,view='readiness')=>openProject(id,view);
  function paint() {
    if(!data||!host.isConnected)return;
    let items=filterProjects(data.projects,prefs);
    if(tasks)items=items.filter(p=>p.pending_count||p.active_count||['failed','stale','unavailable'].includes(p.status));
    page=Math.min(page,Math.max(1,Math.ceil(items.length/10)));
    $('#workspace-result-count').textContent=`${items.length} 个${tasks?'项目有待办':'项目'}`;
    $('#workspace-records').className='workspace-records '+prefs.layout;
    $('#workspace-records').innerHTML=items.length?projectRows(items.slice((page-1)*10,page*10),prefs.layout):`<div class="workspace-empty"><span>◇</span><h3>${data.projects.length?'当前条件下没有项目':'建立第一个工程项目'}</h3><p>${data.projects.length?'调整搜索或筛选条件，查看其他项目。':'导入现有图纸、天气或模型，开始整理与分析。'}</p><button id="workspace-empty-action">${data.projects.length?'清除筛选':'导入项目资料'}</button></div>`;
    $('#workspace-empty-action')?.addEventListener('click',()=>{if(!data.projects.length)openIntake();else{prefs={...prefs,query:'',filter:'all'};$('#workspace-query').value='';$('#workspace-filter').value='all';paint();}});
    host.querySelectorAll('[data-open-project]').forEach(b=>b.onclick=()=>open(b.dataset.openProject));
    host.querySelectorAll('[data-project-action]').forEach(b=>b.onclick=()=>open(b.dataset.projectAction,b.dataset.targetView));
    $('#workspace-page-label').textContent=items.length?`${(page-1)*10+1}–${Math.min(page*10,items.length)} / ${items.length} · 第 ${page} 页`:'0 个项目';
    $('#workspace-previous').disabled=page===1;$('#workspace-next').disabled=page*10>=items.length;
    host.querySelectorAll('[data-layout]').forEach(b=>{b.classList.toggle('selected',prefs.layout===b.dataset.layout);b.setAttribute('aria-pressed',String(prefs.layout===b.dataset.layout));});
  }
  async function refresh() {
    if(busy||!host.isConnected)return;busy=true;$('#workspace-refresh').disabled=true;
    try {
      const result=await request('/workspace');if(!host.isConnected)return;data=result;
      const c=data.counts;
      $('#workspace-alert').hidden=true;
      $('#workspace-stats').innerHTML=[['项目总数',c.projects,'all','项目按账号隔离'],['待复核资料',c.pending_evidence,'attention','从来源确认开始'],['进行中的计算',c.active_runs,'running','排队与运行任务'],['未完成资料批次',c.unfinished_intakes,'intakes','分析进度已保存']].map(([title,value,filter,note],i)=>`<button class="workspace-stat" data-stat-filter="${filter}"><span>${title}<i>0${i+1}</i></span><strong>${value}<small>${i===0?'项':i===1?'份':'个'}</small></strong><small>${note} <b>↗</b></small></button>`).join('');
      host.querySelectorAll('[data-stat-filter]').forEach(b=>b.onclick=()=>{if(b.dataset.statFilter==='intakes'){$('#workspace-intakes').scrollIntoView({block:'center',behavior:'smooth'});return;}prefs.filter=b.dataset.statFilter;$('#workspace-filter').value=prefs.filter;page=1;paint();persist();});
      $('#workspace-intake-count').textContent=data.intakes.length;
      $('#workspace-intakes').innerHTML=data.intakes.length?data.intakes.map(b=>`<button class="workspace-intake" data-resume-intake="${b.id}" data-intake-project="${b.project_id||''}"><span class="work-status review">${({collecting:'待添加资料',analyzing:'正在分析',review:'待核对归档',interrupted:'中断可重试'})[b.status]||esc(b.status)}</span><strong>${esc(b.names.join('、')||'尚未添加文件')}</strong><small>${b.file_count} 份 · ${dateLabel(b.created_at)} <b>继续 →</b></small></button>`).join(''):'<p class="workspace-muted">暂无未完成批次。导入后的进度会保存在这里。</p>';
      host.querySelectorAll('[data-resume-intake]').forEach(b=>b.onclick=()=>openIntake(b.dataset.intakeProject||null,[],b.dataset.resumeIntake));
      $('#workspace-activity').innerHTML=data.activity.length?data.activity.map(a=>`<button class="workspace-activity" data-activity-project="${a.project_id}" data-activity-view="${a.view}"><i></i><span><strong>${esc(a.title)}</strong><small>${esc(a.project_name)}${a.detail?' · '+esc(a.detail):''}</small><time>${dateLabel(a.at)}</time></span></button>`).join(''):'<p class="workspace-muted">项目建立、资料复核和计算记录会显示在这里。</p>';
      host.querySelectorAll('[data-activity-project]').forEach(b=>b.onclick=()=>open(b.dataset.activityProject,b.dataset.activityView));
      $('#workspace-updated').textContent='已同步 · '+dateLabel(data.generated_at);paint();
    }catch(error){if(host.isConnected){$('#workspace-alert').hidden=false;$('#workspace-alert').textContent='同步失败，保留上次状态：'+error.message;$('#workspace-updated').textContent='连接异常 · 正在重试';if(!data)$('#workspace-records').innerHTML='<div class="workspace-empty"><h3>暂时无法读取工作区</h3><p>点击右上角“刷新状态”重试。</p></div>';}throw error;}
    finally{busy=false;if(host.isConnected)$('#workspace-refresh').disabled=false;}
  }
  $('#workspace-query').oninput=e=>{prefs.query=e.target.value;page=1;paint();};
  for(const k of ['filter','sort']){$('#workspace-'+k).value=prefs[k];$('#workspace-'+k).onchange=e=>{prefs[k]=e.target.value;page=1;paint();persist();};}
  host.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{prefs.layout=b.dataset.layout;paint();persist();});
  $('#workspace-previous').onclick=()=>{page--;paint();};$('#workspace-next').onclick=()=>{page++;paint();};
  $('#workspace-new').onclick=()=>openIntake();$('#workspace-refresh').onclick=()=>refresh().catch(()=>{});
  $('#workspace-reference').onclick=reference;$('#workspace-manual').onclick=manual;
  const drop=$('#workspace-drop');drop.onclick=()=>openIntake();drop.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();openIntake();}};
  drop.ondragover=e=>{e.preventDefault();drop.classList.add('dragging');};drop.ondragleave=()=>drop.classList.remove('dragging');drop.ondrop=e=>{e.preventDefault();openIntake(null,Array.from(e.dataTransfer.files));};
  const poller=createPoller(refresh,{interval:15000});refresh().catch(()=>{});poller.start();
  return ()=>poller.stop();
}
