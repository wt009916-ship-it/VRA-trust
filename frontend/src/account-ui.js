import { post, setCsrfToken } from './api.js';

export function changePassword(modal, action, notice) {
  const dialog=modal('修改当前账号密码', '<form id="password-form"><p>修改后其他会话与项目 API Token 会失效；当前浏览器换发新会话。</p><label>当前密码（必填）<input type="password" name="current_password" autocomplete="current-password" required minlength="10" maxlength="128"></label><label>新密码（必填）<input type="password" name="new_password" autocomplete="new-password" required minlength="12" maxlength="128" placeholder="至少 12 位，包含字母与符号"></label><label>确认新密码（必填）<input type="password" name="confirm_password" autocomplete="new-password" required minlength="12" maxlength="128"></label><p id="password-result" role="alert"></p><button class="primary">修改密码</button></form>');
  dialog.querySelector('#password-form').onsubmit=e=>{
    e.preventDefault();const f=Object.fromEntries(new FormData(e.currentTarget));
    action(async()=>{
      try{
        if(f.new_password!==f.confirm_password)throw new Error('两次新密码不一致');
        delete f.confirm_password;const result=await post('/auth/password',f);setCsrfToken(result.csrf_token);dialog.close();notice('密码已修改，其他会话和旧 Token 已失效。');
      }catch(err){dialog.querySelector('#password-result').textContent=err.message;}
    },e.submitter);
  };
}
