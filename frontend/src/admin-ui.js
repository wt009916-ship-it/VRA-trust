import { request, post, escape as esc } from './api.js';
import { changePassword } from './account-ui.js';
import { developerSettings } from './developer-ui.js';

export async function adminWorkspace(root, user, logout) {
  if(!user.is_admin){root.innerHTML='<main class="admin-console"><h1>无管理权限</h1><p>请使用首个工作区管理员账号登录后台。</p><a href="/">返回项目工作台</a><button id="admin-logout">退出当前账号</button></main>';root.querySelector('#admin-logout').onclick=logout;return;}
  root.innerHTML=`<main class="admin-console"><header class="view-heading"><div><span class="eyebrow">ADMINISTRATION / 管理后台</span><h1>稀土智暖 · 工作区管理</h1><p>账号、服务连接与运行记录；工程项目在独立工作台中处理。</p></div><div><a href="/">进入项目工作台 ↗</a> <button id="admin-password">修改密码</button> <button id="admin-logout">退出</button></div></header><nav class="admin-tabs"><button data-admin="accounts">账号与准入</button><button data-admin="services">AI / 开发者配置</button><button data-admin="operations">数据库与运行</button></nav><p id="admin-error" class="error-text" role="alert"></p><section id="admin-content"></section></main><dialog id="dialog"></dialog>`;
  root.querySelector('#admin-logout').onclick=logout;
  const host=root.querySelector('#admin-content');
  const notice=message=>{root.querySelector('#admin-error').textContent=message;};
  async function action(fn,button){if(button)button.disabled=true;notice('');try{await fn();}catch(e){notice(e.message);}finally{if(button?.isConnected)button.disabled=false;}}
  const modal=(title,html)=>{const d=root.querySelector('#dialog');d.innerHTML='<div class="dialog-heading"><h2>'+esc(title)+'</h2><button id="admin-close" aria-label="关闭">×</button></div>'+html;d.querySelector('#admin-close').onclick=()=>d.close();d.showModal();return d;};
  root.querySelector('#admin-password').onclick=()=>changePassword(modal,action,notice);
  async function show(view){
    root.querySelectorAll('[data-admin]').forEach(b=>b.classList.toggle('selected',b.dataset.admin===view));
    const data=await request('/admin/overview');
    if(view==='services'){
      host.innerHTML='<section class="admin-panel"><h2>AI 与工程服务</h2><p>配置兼容 API、视觉模型和工程工具连接。项目用户无权读取或修改这些配置。</p><button id="admin-provider" class="primary">管理模型与 API 连接</button><p>服务商配置后需执行真实连接测试；未配置时，资料收件箱仍可使用本地解析工具。</p></section>';
      const ocr=data.document_ocr;
      host.insertAdjacentHTML('beforeend',`<section class="admin-panel"><h2>扫描件与图片识别</h2><p>${ocr.available?esc(ocr.engine+' '+ocr.version+' · '+ocr.runtime):esc(ocr.error)}</p><p>文档在本机识别，不发送至外部 API。${ocr.available?'每份最多 '+ocr.max_ocr_pages+' 页 OCR、'+ocr.max_text_pages+' 页文字；超限或超时会保留原因。':''}</p><p>项目用户可在资料收件箱对照原图逐页校正，原始识别和校正历史均保留。</p></section>`);
      host.querySelector('#admin-provider').onclick=()=>developerSettings(modal,action,notice);return;
    }
    if(view==='operations'){
      host.innerHTML=`<div class="admin-grid"><section class="admin-panel"><h2>持久化数据库</h2><dl><dt>引擎</dt><dd>${esc(data.database.engine)}</dd><dt>日志模式</dt><dd>${esc(data.database.journal_mode)}</dd><dt>项目数</dt><dd>${data.projects}</dd></dl><p>账号、会话、项目、资料索引、任务及审计存入 SQLite；原文件按哈希关联保存在服务端。</p><p>当前为单实例本地工作区。备份与恢复、跨机器部署仍须单独验收。</p></section><section class="admin-panel"><h2>计算队列</h2>${data.jobs.map(j=>`<p>${esc(j.state)}：${j.count}</p>`).join('')||'<p>暂无计算任务</p>'}</section></div><section class="admin-panel"><h2>管理操作记录</h2><div class="admin-table-wrap"><table><thead><tr><th>时间</th><th>动作</th><th>执行者</th><th>对象</th></tr></thead><tbody>${data.audit.map(a=>`<tr><td>${new Date(a.timestamp*1000).toLocaleString()}</td><td>${esc(a.action)}</td><td>${esc(a.actor)}</td><td>${esc(a.target)}</td></tr>`).join('')}</tbody></table></div></section>`;return;
    }
    host.innerHTML=`<div class="admin-grid"><section class="admin-panel"><h2>成员与访问</h2><p>当前注册方式：${data.registration_mode==='invitation'?'仅邀请码':'开放注册（环境配置）'}。停用会立即撤销会话与项目 Token。</p>${data.users.map(u=>`<article class="admin-user"><span><strong>${esc(u.display_name)}</strong><small>@${esc(u.username)} · ${u.id===user.id?'管理员':u.disabled?'已停用':'项目成员'}</small></span>${u.id!==user.id?`<button data-user="${u.id}" data-disabled="${u.disabled?'false':'true'}">${u.disabled?'启用':'停用'}</button>`:''}</article>`).join('')}</section><section class="admin-panel"><h2>邀请新成员</h2><form id="invite-form"><label>邀请备注 <span class="required-mark">必填</span><input name="label" required maxlength="80" placeholder="如 项目组 · 李工程师"></label><label>有效天数 <span class="required-mark">必填</span><input name="days" required type="number" min="1" max="30" value="7"></label><button class="primary">生成一次性邀请码</button></form><div id="invite-token" role="status"></div><h3>最近的邀请码</h3>${data.invitations.map(i=>`<p>${esc(i.label)} · ${i.used_by?'已使用':i.revoked?'已撤销':i.expires*1000<Date.now()?'已过期':'待使用'} ${!i.used_by&&!i.revoked?`<button data-revoke="${i.id}">撤销</button>`:''}</p>`).join('')||'<p>尚未创建邀请码</p>'}</section></div>`;
    host.querySelector('#invite-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{const r=await post('/admin/invitations',{label:f.get('label'),days:Number(f.get('days'))});await show('accounts');host.querySelector('#invite-token').innerHTML=`<label>请立即复制，仅显示这一次<input readonly aria-label="一次性邀请码" value="${esc(r.invitation)}"></label><p>有效至 ${new Date(r.expires*1000).toLocaleString()}；成员在登录页选择“受邀注册”。</p>`;},e.submitter);};
    host.querySelectorAll('[data-user]').forEach(b=>b.onclick=()=>action(async()=>{await request('/admin/users/'+b.dataset.user,{method:'PATCH',body:JSON.stringify({disabled:b.dataset.disabled==='true'})});await show('accounts');},b));
    host.querySelectorAll('[data-revoke]').forEach(b=>b.onclick=()=>action(async()=>{await request('/admin/invitations/'+b.dataset.revoke,{method:'DELETE'});await show('accounts');},b));
  }
  root.querySelectorAll('[data-admin]').forEach(b=>b.onclick=()=>action(()=>show(b.dataset.admin),b));
  await show('accounts');
}
