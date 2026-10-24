import { request, escape as esc, number as num } from './api.js';
import { changePassword } from './account-ui.js';
import { developerSettings } from './developer-ui.js';
import { accountWorkspace } from './admin-accounts.js';
import { databaseWorkspace } from './admin-database.js';
import './admin.css';

export async function adminWorkspace(root,user,logout){
  if(!user.is_admin){root.innerHTML='<main class="admin-console"><h1>无管理权限</h1><p>请使用工作区管理员账号登录后台。</p><a href="/">返回项目工作台</a><button id="admin-logout">退出当前账号</button></main>';root.querySelector('#admin-logout').onclick=logout;return;}
  const views={accounts:['账号与密码','成员、登录与访问'],database:['数据库管理','记录、历史与备份'],services:['AI / API 配置','模型与工程服务'],operations:['任务与审计','队列状态与操作日志']};
  let current=Object.hasOwn(views,location.hash.slice(1))?location.hash.slice(1):'accounts',sequence=0;
  root.innerHTML=`<main class="admin-system"><aside class="admin-sidebar"><a class="admin-brand" href="/admin"><span>稀土智暖</span><small>DEVELOPER CONSOLE</small></a><p class="admin-sidebar-label">工作区管理</p><nav aria-label="开发者后台导航">${Object.entries(views).map(([key,[title,sub]],i)=>`<button data-admin="${key}"><span class="admin-nav-number">0${i+1}</span><span><strong>${title}</strong><small>${sub}</small></span></button>`).join('')}</nav><div class="admin-sidebar-bottom"><span>管理员 · ${esc(user.display_name)}</span><a href="/">进入项目工作台 ↗</a></div></aside><section class="admin-main"><header class="admin-topbar"><div><small>开发者后台 / 工作区</small><h1 id="admin-view-title">账号与密码</h1></div><div class="admin-row-actions"><button id="admin-password">修改我的密码</button><button id="admin-logout">退出登录</button></div></header><div class="admin-overview" id="admin-overview"></div><p id="admin-error" class="admin-feedback" role="status"></p><section id="admin-content"></section></section></main><dialog id="dialog" class="admin-dialog"></dialog>`;
  root.querySelector('#admin-logout').onclick=logout;
  const host=root.querySelector('#admin-content');
  const notice=message=>{root.querySelector('#admin-error').textContent=message;};
  async function action(fn,button){if(button)button.disabled=true;notice('');try{await fn();}catch(e){notice(e.message);}finally{if(button?.isConnected)button.disabled=false;}}
  const modal=(title,html)=>{const d=root.querySelector('#dialog');d.innerHTML='<div class="dialog-heading"><h2>'+esc(title)+'</h2><button id="admin-close" aria-label="关闭">×</button></div>'+html;d.querySelector('#admin-close').onclick=()=>d.close();d.showModal();return d;};
  root.querySelector('#admin-password').onclick=()=>changePassword(modal,action,notice);
  async function show(view){
    current=view;const ticket=++sequence;
    history.replaceState(null,'','#'+view);
    root.querySelectorAll('[data-admin]').forEach(b=>{b.classList.toggle('selected',b.dataset.admin===view);b.setAttribute('aria-current',b.dataset.admin===view?'page':'false');});
    root.querySelector('#admin-view-title').textContent=views[view][0];host.innerHTML='<p role="status">正在读取后台数据…</p>';
    const data=await request('/admin/overview');if(ticket!==sequence||!root.isConnected)return;
    root.querySelector('#admin-overview').innerHTML=[['成员账号',data.users.length],['工程项目',data.projects],['运行中任务',data.jobs.filter(j=>j.state==='running'||j.state==='queued').reduce((s,j)=>s+j.count,0)],['持久化数据库',data.database.engine]].map(([label,value])=>`<div><small>${label}</small><strong>${typeof value==='number'?num(value,0):esc(value)}</strong></div>`).join('');
    const panel=document.createElement('div');host.replaceChildren(panel);
    const helpers={modal,action,notice,refresh:()=>show(current)};
    if(view==='accounts'){accountWorkspace(panel,data,user,helpers);return;}
    if(view==='database'||view==='operations'){await databaseWorkspace(panel,helpers,view==='operations'?'jobs':'projects',view==='operations');return;}
    panel.innerHTML='<div class="admin-section-heading"><div><h2>模型与 API 连接</h2><p>管理文本、视觉模型和工程工具连接。</p></div></div><section class="admin-panel"><h3>AI 服务配置</h3><p>API 地址、模型名称、凭据和连接测试集中在此维护。</p><button id="admin-provider" class="primary">管理模型与 API 连接</button></section>';
    const ocr=data.document_ocr;
    panel.insertAdjacentHTML('beforeend',`<section class="admin-panel"><h3>本地图纸与文档识别</h3><p>${ocr.available?esc(ocr.engine+' '+ocr.version+' · '+ocr.runtime):esc(ocr.error)}</p><p>文档在本机识别。${ocr.available?'每份最多 '+ocr.max_ocr_pages+' 页 OCR、'+ocr.max_text_pages+' 页文字。':''}项目用户可在收件箱对照原图校正，保留修订历史。</p></section>`);
    panel.querySelector('#admin-provider').onclick=()=>developerSettings(modal,action,notice);
  }
  root.querySelectorAll('[data-admin]').forEach(b=>b.onclick=()=>action(()=>show(b.dataset.admin),b));await show(current);
}
