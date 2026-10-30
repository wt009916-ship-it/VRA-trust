import {request,post,escape as esc} from './api.js';
export function projectTokens(pid, host, action, notice) {
  action(async()=>{
    const base='/projects/'+pid,dialog=document.createElement('dialog');
    dialog.className='token-dialog';document.body.append(dialog);
    dialog.innerHTML=`<div class="dialog-heading"><h2>项目 API / MCP</h2><button id="close-token" aria-label="关闭">×</button></div><p>Token 仅限当前项目。密钥只显示一次，后端只保存哈希；可随时撤销。</p><form id="token-form"><label>用途名称<input name="name" required maxlength="80" placeholder="如 Codex 工程助手"></label><label>有效期 · 天<input name="days" type="number" value="30" min="1" max="90"></label><label class="check-option"><input name="read" type="checkbox" checked>读取模型、证据和结果</label><label class="check-option"><input name="write" type="checkbox">编辑资料与模型</label><label class="check-option"><input name="compute" type="checkbox">提交真实计算</label><button class="primary">创建专属 Token</button></form><div id="new-token" role="status"></div><div id="token-list"></div><details><summary>MCP 客户端配置示例</summary><pre id="mcp-config"></pre></details><p class="subtle">将 command 与 args 改成项目虚拟环境 Python 和 scripts/run_mcp.py 的绝对路径。Token 放在客户端配置或进程环境中，勿提交到 Git。</p>`;
    dialog.querySelector('#mcp-config').textContent=JSON.stringify({mcpServers:{'vra-trust':{command:'<项目>/.venv/Scripts/python.exe',args:['<项目绝对路径>/scripts/run_mcp.py'],env:{VRA_BASE_URL:location.origin,VRA_PROJECT_ID:pid,VRA_API_TOKEN:'<本项目 Token>'}}}},null,2);
    dialog.querySelector('#close-token').onclick=()=>dialog.close();
    dialog.onclose=()=>dialog.remove();dialog.showModal();
    async function paint(){
      const tokens=await request(base+'/tokens');if(!dialog.isConnected)return;
      dialog.querySelector('#token-list').innerHTML=tokens.map(t=>`<p><strong>${esc(t.name)}</strong> · ${esc(t.scopes.join('/'))} · ${new Date(t.expires*1000).toLocaleDateString()} ${t.revoked?'已撤销':`<button data-revoke="${t.id}">撤销</button>`}</p>`).join('');
      dialog.querySelectorAll('[data-revoke]').forEach(b=>{b.onclick=()=>action(async()=>{await request(base+'/tokens/'+b.dataset.revoke,{method:'DELETE'});await paint();},b);});
    }
    dialog.querySelector('#token-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{
      const token=await post(base+'/tokens',{name:f.get('name'),days:Number(f.get('days')),scopes:['read','write','compute'].filter(k=>f.has(k))});
      dialog.querySelector('#new-token').innerHTML=`<label>立即复制，关闭后不再显示<input readonly value="${esc(token.token)}" aria-label="新创建的 API Token"></label>`;
      await paint();notice('项目 Token 已创建');
    },e.submitter);};await paint();
  });
}
