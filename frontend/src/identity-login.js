import { request, post, escape as esc } from './api.js';

export function mfaStep(original, challenge) {
  const pane=document.createElement('section');pane.className='mfa-login-stage';
  pane.innerHTML='<h2>完成双重验证</h2><p>输入认证器当前验证码，或一个未使用的恢复码。验证码与恢复码均不能重复使用。</p><form method="post" action="/api/auth/mfa/verify"><label>验证码或恢复码<input name="code" autocomplete="one-time-code" required maxlength="40" autofocus></label><p role="alert"></p><button type="submit" class="primary">验证并登录</button><button type="button" data-back>返回登录</button></form>';
  original.hidden=true;original.after(pane);
  return new Promise((resolve,reject)=>{
    const finish=()=>{pane.remove();original.hidden=false;};
    pane.querySelector('[data-back]').onclick=()=>{finish();reject(Error('已取消双重验证，请重新登录。'));};
    let busy=false;
    pane.querySelector('form').onsubmit=async e=>{
      e.preventDefault();if(busy)return;busy=true;const button=pane.querySelector('[type=submit]');button.disabled=true;
      try{const session=await post('/auth/mfa/verify',{challenge,code:pane.querySelector('input').value});finish();resolve(session);}
      catch(error){pane.querySelector('[role=alert]').textContent=error.message;}
      finally{busy=false;button.disabled=false;}
    };
    pane.querySelector('input').focus();
  });
}

export function recoveryHelp(dialog, enabled){
  if(!enabled)return;
  dialog.innerHTML='<h2>通过已验证邮箱找回</h2><p>仅已绑定并验证的恢复邮箱可找回账号。启用双重验证的账号仍须验证码或恢复码。</p><form><label>恢复邮箱<input name="address" type="email" autocomplete="email" required></label><p role="status"></p><div class="actions"><button type="submit" class="primary">发送找回邮件</button><button type="button" data-close>关闭</button></div></form>';
  dialog.querySelector('[data-close]').onclick=()=>dialog.close();
  dialog.querySelector('form').onsubmit=async e=>{
    e.preventDefault();const button=e.submitter;button.disabled=true;
    try{const r=await post('/auth/recovery/request',{address:dialog.querySelector('input').value});dialog.querySelector('[role=status]').textContent=r.message;}
    catch(error){dialog.querySelector('[role=status]').textContent=error.message;}
    finally{button.disabled=false;}
  };
}

export async function recoveryRoute(root, kind, token){
  history.replaceState(null,'',location.pathname+'#'+kind);
  root.innerHTML='<main class="recovery-page"><a href="/">稀土智暖 · 返回登录</a><h1></h1><p role="status">正在验证链接…</p><div data-content></div></main>';
  const heading=root.querySelector('h1'),status=root.querySelector('[role=status]'),content=root.querySelector('[data-content]');
  try{
    if(kind==='verify-email'){
      heading.textContent='验证恢复邮箱';const r=await post('/auth/email/verify',{token});status.textContent=r.message;return;
    }
    heading.textContent='重置登录密码';
    const info=await post('/auth/recovery/inspect',{token});status.textContent='设置新密码后须重新登录，原会话和API令牌将失效。';
    content.innerHTML=`<form method="post" action="/api/auth/recovery/complete"><label>账号<input name="username" autocomplete="username" readonly value="${esc(info.username)}"></label><label>新密码<input name="new_password" type="password" autocomplete="new-password" required minlength="15" maxlength="128"></label><label>确认新密码<input name="confirmation" type="password" autocomplete="new-password" required minlength="15" maxlength="128"></label>${info.mfa_required?'<label>认证器验证码或恢复码<input name="factor_code" autocomplete="one-time-code" required maxlength="40"></label>':''}<p role="alert"></p><button class="primary">重置密码</button></form>`;
    const f=content.querySelector('form');
    const match=()=>f.elements.confirmation.setCustomValidity(f.elements.new_password.value!==f.elements.confirmation.value?'两次密码不一致':'');
    f.elements.confirmation.oninput=match;f.elements.new_password.oninput=match;
    f.onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;
      try{const r=await post('/auth/recovery/complete',{token,new_password:f.elements.new_password.value,...(f.elements.factor_code?{factor_code:f.elements.factor_code.value}:{})});content.innerHTML='';status.textContent=r.message;}
      catch(error){f.querySelector('[role=alert]').textContent=error.message;}
      finally{button.disabled=false;}
    };
  }catch(error){status.textContent=error.message;}
}
