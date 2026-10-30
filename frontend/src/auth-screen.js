import { mfaStep, recoveryHelp } from './identity-login.js';
import { authView } from './layout.js';
import { post, escape as esc } from './api.js';

export function readPreference(key, fallback='') {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
export function writePreference(key, value) {
  try { if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value); } catch { /* Storage is optional. */ }
}

export function passwordFeedback(form, {newPassword=false}={}) {
  const input=form.querySelector('[name=password],[name=new_password]');
  if(!input)return;
  const note=document.createElement('p');note.className='password-feedback';note.setAttribute('aria-live','polite');
  input.closest('label').after(note);
  function paint(event){
    const caps=event?.getModifierState?.('CapsLock');
    if(caps){note.textContent='大写锁定已开启';return;}
    if(!newPassword){note.textContent='';return;}
    const length=Array.from(input.value).length;
    note.textContent=length===0?'15–128 个字符；可用长口令、空格或中文。支持粘贴和密码管理器。':length<15?`还需 ${15-length} 个字符。`:'长度符合要求；提交时会检查常见弱密码。';
  }
  input.addEventListener('input',paint);input.addEventListener('keyup',paint);input.addEventListener('keydown',paint);paint();
  const confirmation=form.querySelector('[name=confirm_password]');
  const match=()=>confirmation?.setCustomValidity(confirmation.value&&confirmation.value!==input.value?'两次密码不一致':'');
  input.addEventListener('input',match);confirmation?.addEventListener('input',match);
}

export function mountAuthScreen(root, {setup,register,admin,registrationMode,onSwitch,onSession,ssoAvailable=false,emailRecoveryAvailable=false}) {
  root.innerHTML=authView({setup,register,admin,registrationMode});
  const form=root.querySelector('#auth-form'), error=form.querySelector('#auth-error');
  const username=form.elements.username, rememberName=form.querySelector('[data-remember-name]');
  const saved=readPreference('vra-login-username');
  if(!setup&&!register){if(saved&&!username.value)username.value=saved;rememberName.checked=!!saved;}
  root.querySelector('#switch-auth')?.addEventListener('click',()=>onSwitch(!register));
  root.querySelector('#show-password').onclick=e=>{
    const input=form.elements.password,show=input.type==='password';input.type=show?'text':'password';
    e.currentTarget.textContent=show?'隐藏':'显示';e.currentTarget.setAttribute('aria-label',show?'隐藏密码':'显示密码');
  };
  passwordFeedback(form,{newPassword:setup||register});
  root.querySelector('[data-auth-help]').onclick=()=>root.querySelector('.auth-help').showModal();
  root.querySelector('.auth-help button').onclick=()=>root.querySelector('.auth-help').close();
  recoveryHelp(root.querySelector('.auth-help'),emailRecoveryAvailable);
  if(ssoAvailable&&!setup){const sso=document.createElement('a');sso.className='sso-login-button';sso.textContent='使用企业身份登录';sso.href='/api/auth/sso/start';form.after(sso);}
  if(location.hash==='#sso-failed'){error.textContent='企业登录未完成或身份未绑定，请重试或联系管理员。';error.hidden=false;}
  if(location.hash==='#sso-linked')history.replaceState(null,'',location.pathname);
  let submitting=false,authenticatedSession=null;
  form.onsubmit=async e=>{
    e.preventDefault();if(submitting)return;submitting=true;
    const button=form.querySelector('[type=submit]'),original=button.innerHTML;
    button.disabled=true;button.textContent='正在验证…';form.setAttribute('aria-busy','true');error.hidden=true;
    try{
      const body=Object.fromEntries(new FormData(form));body.username=body.username.trim().toLowerCase();
      body.remember_device=!!form.elements.remember_device?.checked;
      if(setup||register){if(body.password!==body.confirm_password)throw Error('两次密码不一致');delete body.confirm_password;}
      let session=authenticatedSession||await post('/auth/'+(setup||register?'register':'login'),body);
      if(session.mfa_required)session=await mfaStep(form,session.challenge);
      authenticatedSession=session;
      writePreference('vra-login-username',rememberName.checked?body.username:null);
      // Leave genuine login fields for the browser's password-manager heuristics.
      await onSession(session);
    }catch(err){if(form.isConnected){error.textContent=err.message;error.hidden=false;error.focus();}}
    finally{if(form.isConnected){submitting=false;button.disabled=false;button.innerHTML=authenticatedSession?'重新打开工作区':original;form.removeAttribute('aria-busy');}}
  };
}

export function reauthenticate(user) {
  const dialog=document.createElement('dialog');dialog.className='reauth-dialog';
  dialog.innerHTML=`<h2>登录已过期</h2><p>当前页面和未保存编辑仍保留。请用原账号重新验证，再重试刚才的操作。</p><form method="post" action="/api/auth/login"><label>账号<input name="username" autocomplete="username" readonly value="${esc(user.username)}"></label><label>密码<input name="password" type="password" autocomplete="current-password" required maxlength="128"></label><label class="check-option"><input name="remember_device" type="checkbox" ${user.remember_device?'checked':''}>在此设备保持登录 12 小时</label><p role="alert" data-error></p><div class="actions"><button type="submit" class="primary">重新登录并继续</button><button type="button" data-leave>退出到登录页</button></div></form>`;
  document.body.append(dialog);dialog.showModal();dialog.oncancel=e=>e.preventDefault();
  passwordFeedback(dialog.querySelector('form'));
  return new Promise(resolve=>{
    const finish=result=>{dialog.close();dialog.remove();resolve(result);};
    dialog.querySelector('[data-leave]').onclick=()=>finish(null);
    let busy=false;
    dialog.querySelector('form').onsubmit=async e=>{
      e.preventDefault();if(busy)return;busy=true;const button=dialog.querySelector('[type=submit]');button.disabled=true;
      try{
        let session=await post('/auth/login',{username:user.username,password:dialog.querySelector('[name=password]').value,remember_device:dialog.querySelector('[name=remember_device]').checked});
        if(session.mfa_required)session=await mfaStep(dialog.querySelector('form'),session.challenge);
        if(session.user.id!==user.id)throw Error('账号已发生变化，请退出后重新登录。');
        finish(session);
      }catch(err){dialog.querySelector('[data-error]').textContent=err.message;}
      finally{busy=false;button.disabled=false;}
    };
  });
}
