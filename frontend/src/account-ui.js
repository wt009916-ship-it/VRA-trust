import { mountIdentityPanels } from './identity-ui.js';
import { post, request, escape as esc, setCsrfToken } from './api.js';
import { passwordFeedback } from './auth-screen.js';

export function changePassword(modal, action, notice, user=null) {
  const dialog=modal('修改当前账号密码', '<form id="password-form"><p>修改后其他会话与项目 API Token 会失效；当前浏览器换发新会话。</p><label>当前密码（必填）<input type="password" name="current_password" autocomplete="current-password" required minlength="1" maxlength="128"></label><label>新密码（必填）<input type="password" name="new_password" autocomplete="new-password" required minlength="15" maxlength="128" placeholder="15–128 个字符，支持长口令"></label><label>确认新密码（必填）<input type="password" name="confirm_password" autocomplete="new-password" required minlength="15" maxlength="128"></label><p id="password-result" role="alert"></p><button class="primary">修改密码</button></form>');
  dialog.querySelector('.dialog-heading h2').textContent='账号与安全';
  const form=dialog.querySelector('#password-form');
  const passwordPage=document.createElement('div');passwordPage.dataset.accountPage='password';form.before(passwordPage);passwordPage.append(form);
  passwordPage.insertAdjacentHTML('beforebegin','<nav class="account-tabs" aria-label="账号设置"><button type="button" data-account-tab="password" class="selected">修改密码</button><button type="button" data-account-tab="sessions">登录会话</button></nav>');
  form.method='post';form.action='/api/auth/password';
  if(user)form.insertAdjacentHTML('afterbegin',`<label>当前账号<input name="username" autocomplete="username" readonly value="${esc(user.username)}"></label>`);
  passwordFeedback(form,{newPassword:true});
  dialog.addEventListener('close',()=>dialog.querySelectorAll('input[type=password]').forEach(i=>{i.value='';}),{once:true});
  dialog.insertAdjacentHTML('beforeend','<section class="account-sessions" data-account-page="sessions" hidden><h3>登录会话</h3><div data-sessions role="status">正在读取…</div><form data-revoke-sessions><label>验证当前密码后退出其他会话<input name="current_password" type="password" autocomplete="current-password" required maxlength="128"></label><button>退出其他会话</button><p data-session-error role="status"></p></form></section>');
  async function loadSessions(){
    const sessions=await request('/auth/sessions');
    dialog.querySelector('[data-sessions]').innerHTML=sessions.map(s=>`<p><strong>${s.current?'当前会话':'其他会话'}</strong><small>${esc(s.id.slice(-8))} · 创建于 ${new Date(s.created_at*1000).toLocaleString()}<br>到期 ${new Date(s.expires_at*1000).toLocaleString()} · ${s.remember_device?'在设备保持登录':'浏览器会话'}</small></p>`).join('')||'暂无会话';
  }
  if(user)dialog.querySelector('[data-revoke-sessions]').insertAdjacentHTML('afterbegin',`<input type="text" hidden name="username" autocomplete="username" value="${esc(user.username)}">`);
  mountIdentityPanels(dialog,user,action,notice);
  dialog.querySelectorAll('[data-account-tab]').forEach(b=>b.onclick=()=>{
    dialog.querySelectorAll('[data-account-tab]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});
    dialog.querySelectorAll('[data-account-page]').forEach(x=>{x.hidden=x.dataset.accountPage!==b.dataset.accountTab;});
  });
  action(loadSessions);
  dialog.querySelector('[data-revoke-sessions]').onsubmit=e=>{
    e.preventDefault();const f=e.currentTarget;
    action(async()=>{try{const r=await post('/auth/sessions/revoke-others',{current_password:f.elements.current_password.value,...(f.elements.factor_code?{factor_code:f.elements.factor_code.value}:{})});f.reset();await loadSessions();dialog.querySelector('[data-session-error]').textContent=`已退出 ${r.revoked} 个其他会话。`;}catch(err){dialog.querySelector('[data-session-error]').textContent=err.message;}},e.submitter);
  };
  dialog.querySelector('#password-form').onsubmit=e=>{
    e.preventDefault();const f=Object.fromEntries(new FormData(e.currentTarget));
    action(async()=>{
      try{
        if(f.new_password!==f.confirm_password)throw new Error('两次新密码不一致');
        delete f.confirm_password;delete f.username;const result=await post('/auth/password',f);setCsrfToken(result.csrf_token);dialog.close();notice('密码已修改，其他会话和旧 Token 已失效。');
      }catch(err){dialog.querySelector('#password-result').textContent=err.message;}
    },e.submitter);
  };
}
