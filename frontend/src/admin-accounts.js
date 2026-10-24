import { request, post, escape as esc } from './api.js';

const adminPassword='<label>管理员当前密码 <span class="required-mark">必填</span><input name="current_password" type="password" autocomplete="current-password" required minlength="10" maxlength="128"></label>';
const newPassword='<label>成员新密码 <span class="required-mark">必填</span><input name="new_password" type="password" autocomplete="new-password" required minlength="12" maxlength="128" placeholder="至少 12 位，包含字母和符号"></label><label>确认成员新密码<input name="confirmation" type="password" autocomplete="new-password" required minlength="12" maxlength="128"></label>';

export function accountWorkspace(host,data,user,{modal,action,notice,refresh}){
  host.innerHTML=`<div class="admin-section-heading"><div><h2>账号与密码</h2><p>集中管理登录账号、成员状态与访问权限。密码以哈希保存，在这里设置新密码。</p></div><button id="create-member" class="primary">＋ 新增成员</button></div><section class="admin-panel"><div class="admin-toolbar"><label>搜索成员<input id="account-search" type="search" placeholder="用户名或显示名称"></label><span>${data.users.length} 个账号 · ${data.users.filter(u=>!u.disabled).length} 个可登录</span></div><div class="admin-table-wrap"><table class="admin-data-table"><thead><tr><th>成员</th><th>用户名</th><th>权限 / 状态</th><th>项目</th><th>有效会话</th><th>操作</th></tr></thead><tbody id="account-rows"></tbody></table></div></section><section class="admin-panel"><h2>邀请注册</h2><p>当前：${data.registration_mode==='invitation'?'仅邀请码注册':'开放注册'}。也可用“新增成员”直接创建账号。</p><form id="invite-form" class="admin-inline-form"><label>邀请备注<input name="label" required maxlength="80" placeholder="项目组 · 成员名称"></label><label>有效天数<input name="days" required type="number" min="1" max="30" value="7"></label><button>生成邀请码</button></form><div id="invite-token" role="status"></div><div class="admin-invitations">${data.invitations.map(i=>`<p>${esc(i.label)} <span>${i.used_by?'已使用':i.revoked?'已撤销':i.expires*1000<Date.now()?'已过期':'待使用'}</span> ${!i.used_by&&!i.revoked?`<button data-revoke-invite="${i.id}">撤销</button>`:''}</p>`).join('')||'<p class="subtle">还没有邀请码</p>'}</div></section>`;
  function openForm(title,content,submit){
    const d=modal(title,`<form id="account-form" class="admin-edit-form">${content}<p id="account-form-error" class="error-text" role="alert"></p><button class="primary">确认保存</button></form>`);
    d.querySelector('form').onsubmit=e=>{e.preventDefault();const values=Object.fromEntries(new FormData(e.currentTarget));action(async()=>{try{await submit(values);d.close();await refresh();notice('账号操作已保存。');}catch(err){d.querySelector('#account-form-error').textContent=err.message;}},e.submitter);};
  }
  function passwordValues(values){if(values.new_password!==values.confirmation)throw Error('两次成员密码不一致');delete values.confirmation;return values;}
  function paint(q=''){
    host.querySelector('#account-rows').innerHTML=data.users.filter(u=>(u.username+' '+u.display_name).toLowerCase().includes(q.toLowerCase())).map(u=>`<tr><td><strong>${esc(u.display_name)}</strong><small>${u.id===user.id?'当前账号':esc(u.id)}</small></td><td class="mono">${esc(u.username)}</td><td><span class="admin-pill ${u.disabled?'muted':''}">${u.is_admin?'管理员':u.disabled?'已停用':'成员'}</span></td><td>${u.projects}</td><td>${u.sessions}</td><td><div class="admin-row-actions"><button data-edit-user="${u.id}">编辑账号</button>${u.id===user.id?'<span class="subtle">改密见右上角</span>':`<button data-reset-user="${u.id}">重置密码</button>`}<button data-revoke-user="${u.id}">撤销登录</button>${!u.is_admin?`<button data-disable-user="${u.id}" data-disabled="${u.disabled?'false':'true'}">${u.disabled?'启用':'停用'}</button>`:''}</div></td></tr>`).join('')||'<tr><td colspan="6">没有匹配的账号</td></tr>';
    host.querySelectorAll('[data-edit-user]').forEach(b=>b.onclick=()=>{
      const u=data.users.find(u=>u.id===b.dataset.editUser);
      openForm('编辑账号 · '+u.username,`<p>修改用户名后该账号须重新登录，原项目归属保留。</p><label>用户名<input name="username" required minlength="3" maxlength="32" value="${esc(u.username)}"></label><label>显示名称<input name="display_name" required maxlength="40" value="${esc(u.display_name)}"></label>${adminPassword}`,async f=>{
        const result=await request('/admin/users/'+u.id+'/profile',{method:'PUT',body:JSON.stringify({...f,expected_username:u.username,expected_display_name:u.display_name})});if(result.reauthenticate)location.assign('/admin');
      });
    });
    host.querySelectorAll('[data-reset-user]').forEach(b=>b.onclick=()=>{
      const u=data.users.find(u=>u.id===b.dataset.resetUser);
      openForm('重置成员密码 · '+u.username,`<p>重置后该成员所有登录会话与 API 令牌将失效；原项目和资料保留。</p>${newPassword}${adminPassword}`,f=>post('/admin/users/'+u.id+'/password',passwordValues(f)));
    });
    host.querySelectorAll('[data-revoke-user]').forEach(b=>b.onclick=()=>{
      const u=data.users.find(u=>u.id===b.dataset.revokeUser);
      openForm('撤销登录 · '+u.username,`<p>将撤销这个账号的所有登录会话与 API 令牌。${u.id===user.id?'包括你当前的登录。':''}账号和项目会保留。</p>${adminPassword}`,async f=>{const r=await post('/admin/users/'+u.id+'/revoke-access',f);if(r.reauthenticate)location.assign('/admin');});
    });
    host.querySelectorAll('[data-disable-user]').forEach(b=>b.onclick=()=>action(async()=>{await request('/admin/users/'+b.dataset.disableUser,{method:'PATCH',body:JSON.stringify({disabled:b.dataset.disabled==='true'})});await refresh();notice('成员状态已更新。');},b));
  }
  paint();host.querySelector('#account-search').oninput=e=>paint(e.target.value);
  host.querySelector('#create-member').onclick=()=>openForm('新增成员账号',`<label>用户名<input name="username" required minlength="3" maxlength="32" placeholder="字母、数字、下划线，至少包含字母"></label><label>显示名称<input name="display_name" required maxlength="40"></label>${newPassword}${adminPassword}`,f=>{passwordValues(f);const {new_password,...rest}=f;return post('/admin/users',{...rest,password:new_password});});
  host.querySelector('#invite-form').onsubmit=e=>{e.preventDefault();const f=Object.fromEntries(new FormData(e.currentTarget));action(async()=>{const r=await post('/admin/invitations',{label:f.label,days:Number(f.days)});await refresh();host.querySelector('#invite-token').innerHTML=`<label>一次性邀请码 · 请立即复制<input readonly aria-label="一次性邀请码" value="${esc(r.invitation)}"></label><p>有效至 ${new Date(r.expires*1000).toLocaleString()}</p>`;},e.submitter);};
  host.querySelectorAll('[data-revoke-invite]').forEach(b=>b.onclick=()=>action(async()=>{await request('/admin/invitations/'+b.dataset.revokeInvite,{method:'DELETE'});await refresh();},b));
}
