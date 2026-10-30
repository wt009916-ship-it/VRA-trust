import { post, request, escape as esc, setCsrfToken } from './api.js';

const credentials=(mfa=false)=>`<label>当前密码<input name="current_password" type="password" autocomplete="current-password" required maxlength="128"></label>${mfa?'<label>认证器验证码或恢复码<input name="factor_code" autocomplete="one-time-code" required maxlength="40"></label>':''}`;
const body=form=>{const value=Object.fromEntries(new FormData(form));delete value.username;return value;};

export function mountIdentityPanels(dialog, user, action, notice) {
  const tabs=dialog.querySelector('.account-tabs');
  for(const [key,title] of [['mfa','双重验证'],['email','恢复邮箱'],['sso','企业登录']]){
    tabs.insertAdjacentHTML('beforeend',`<button type="button" data-account-tab="${key}">${title}</button>`);
    dialog.insertAdjacentHTML('beforeend',`<section data-account-page="${key}" class="identity-panel" hidden><p>正在读取账号安全状态…</p></section>`);
  }
  const page=key=>dialog.querySelector(`[data-account-page="${key}"]`);
  function rotated(result){setCsrfToken(result.csrf_token);if(user)Object.assign(user,result.user);}
  function recoveryCodes(result){
    rotated(result);
    page('mfa').innerHTML='<h3>保存恢复码</h3><p>恢复码只在本次显示，每个只能使用一次。请保存在可信密码管理器或离线安全位置；丢失认证器时可代替验证码。</p><textarea readonly aria-label="一次性恢复码" rows="10"></textarea><label class="check-option"><input type="checkbox" data-saved>我已安全保存恢复码</label><button class="primary" data-finish disabled>完成</button>';
    page('mfa').querySelector('textarea').value=result.recovery_codes.join('\n');
    page('mfa').querySelector('[data-saved]').onchange=e=>{page('mfa').querySelector('[data-finish]').disabled=!e.target.checked;};
    page('mfa').querySelector('[data-finish]').onclick=()=>action(load);
  }
  async function load(){
    const state=await request('/auth/security');
    if(!dialog.isConnected)return;
    dialog.querySelectorAll('[data-factor-field]').forEach(el=>el.remove());
    if(state.mfa.enabled){
      for(const form of dialog.querySelectorAll('#password-form,[data-revoke-sessions]'))form.querySelector('button[type=submit],button:not([type])')?.insertAdjacentHTML('beforebegin','<label data-factor-field>双重验证码或恢复码<input name="factor_code" autocomplete="one-time-code" required maxlength="40"></label>');
    }
    page('mfa').innerHTML=state.mfa.enabled?`<h3>双重验证已启用</h3><p>登录须密码与认证器验证码。剩余恢复码 ${state.mfa.recovery_codes_remaining} 个。</p><form data-manage>${credentials(true)}<div class="actions"><button name="operation" value="rotate">重新生成恢复码</button><button name="operation" value="disable">关闭双重验证</button></div><p role="status"></p></form>`:`<h3>为账号启用双重验证</h3><p>使用标准 TOTP 认证器扫描二维码，输入验证码确认后才启用。支持恢复码，不会替你自动绑定设备。</p><form data-enroll>${credentials()}<button class="primary">开始绑定认证器</button><p role="status"></p></form>`;
    const enroll=page('mfa').querySelector('[data-enroll]');
    if(enroll)enroll.onsubmit=e=>{e.preventDefault();action(async()=>{
      try{const result=await post('/auth/mfa/enroll',body(enroll));
        page('mfa').innerHTML='<h3>扫描并确认认证器</h3><p>用你自己的认证器扫描；绑定信息10分钟后失效。请勿将二维码或密钥分享给他人。</p><img class="mfa-qr" alt="仅供本人认证器绑定的二维码"><details><summary>无法扫码？手动复制绑定地址</summary><textarea readonly aria-label="认证器绑定地址"></textarea></details><form data-enable><label>认证器当前的6位验证码<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" required maxlength="6"></label><button class="primary">验证并启用</button><p role="status"></p></form>';
        page('mfa').querySelector('img').src=result.qr_image;page('mfa').querySelector('textarea').value=result.provisioning_uri;
        page('mfa').querySelector('[data-enable]').onsubmit=event=>{event.preventDefault();action(async()=>{try{recoveryCodes(await post('/auth/mfa/enable',body(event.currentTarget)));}catch(error){page('mfa').querySelector('[role=status]').textContent=error.message;}},event.submitter);};
      }catch(error){enroll.querySelector('[role=status]').textContent=error.message;}
    },e.submitter);};
    const manage=page('mfa').querySelector('[data-manage]');
    if(manage)manage.onsubmit=e=>{e.preventDefault();const op=e.submitter.value;action(async()=>{
      try{const result=await post('/auth/mfa/'+(op==='disable'?'disable':'recovery-codes'),body(manage));if(op==='disable'){rotated(result);notice('双重验证已关闭，旧会话与Token已撤销。');await load();}else recoveryCodes(result);}catch(error){manage.querySelector('[role=status]').textContent=error.message;}
    },e.submitter);};
    page('email').innerHTML=`<h3>账号恢复邮箱</h3><p>${state.email.verified?'已验证：'+esc(state.email.address):'尚未绑定已验证的恢复邮箱'}</p><p>邮件中的确认链接30分钟内有效；确认新地址前原恢复邮箱仍有效。重置密码会撤销旧会话与项目Token，并保留双重验证。</p>${state.email.delivery_configured?`<form data-email><label>恢复邮箱<input name="address" type="email" autocomplete="email" required value="${esc(state.email.address||'')}"></label>${credentials(state.mfa.enabled)}<button>发送邮箱验证邮件</button><p role="status"></p></form>`:'<p>请管理员先在后台配置邮件服务。</p>'}`;
    const email=page('email').querySelector('form');if(email)email.onsubmit=e=>{e.preventDefault();action(async()=>{try{const r=await post('/auth/email/bind',body(email));email.reset();email.querySelector('[role=status]').textContent=r.message;}catch(error){email.querySelector('[role=status]').textContent=error.message;}},e.submitter);};
    page('sso').innerHTML=`<h3>企业身份登录</h3><p>按身份平台的 issuer + subject 显式绑定，邮箱相同也不会自动合并账号。首次绑定需要验证本地账号。</p>${state.sso.linked_issuers.map(issuer=>`<p class="sso-linked">已绑定 ${esc(issuer)}</p>`).join('')}${state.sso.configured?`<form data-sso>${credentials(state.mfa.enabled)}<div class="actions"><button name="operation" value="link">绑定当前企业身份</button>${state.sso.linked_issuers.length?'<button name="operation" value="unlink">解除企业身份绑定</button>':''}</div><p role="status"></p></form>`:'<p>请管理员先配置企业OIDC连接。</p>'}`;
    const sso=page('sso').querySelector('form');if(sso)sso.onsubmit=e=>{e.preventDefault();const op=e.submitter.value;action(async()=>{try{if(op==='unlink'){rotated(await post('/auth/sso/unlink',{...body(sso),issuer:state.sso.linked_issuers[0]}));await load();notice('企业身份绑定已解除，旧会话和令牌已撤销。');}else{const r=await post('/auth/sso/link',body(sso));location.assign(r.authorization_url);}}catch(error){sso.querySelector('[role=status]').textContent=error.message;}},e.submitter);};
    for(const form of dialog.querySelectorAll('.identity-panel form'))form.insertAdjacentHTML('afterbegin',`<input type="text" name="username" autocomplete="username" hidden value="${esc(user?.username||'')}">`);
    // Username is for password-manager association, never part of identity API writes.
    dialog.addEventListener('close',()=>{for(const el of dialog.querySelectorAll('.mfa-qr'))el.removeAttribute('src');for(const el of dialog.querySelectorAll('.identity-panel textarea'))el.value='';},{once:true});
  }
  action(load);
}

