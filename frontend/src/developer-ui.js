import { request, post, escape as esc } from './api.js';

export function developerSettings(modal, action, notice) {
  action(async()=>{
    const [config,runtime]=await Promise.all([request('/developer/provider'),request('/developer/runtime')]);
    modal('开发者控制台', `<div class="developer-runtime"><span class="badge">${runtime.engine.available?esc(runtime.engine.version):'EnergyPlus 未配置'}</span><span class="badge">仿真并发 ${runtime.engine_parallelism}</span><span class="badge">${runtime.worker_alive?'计算队列运行中':'计算队列未启动'}</span></div>
    <form id="provider-form"><p>兼容 Chat Completions 的服务可接入同一套工程工具。填写完整接口地址；Key 仅在后端保存，Windows 使用系统账户加密。视觉识别另外指定支持图片的模型。</p>
    <label>API Endpoint<input name="endpoint" required type="url" value="${esc(config.endpoint)}" placeholder="https://your-provider/v1/chat/completions"></label>
    <div class="form-grid"><label>对话 / 工具模型<input name="model" required maxlength="100" value="${esc(config.model)}"></label><label>视觉模型（可选）<input name="vision_model" maxlength="100" value="${esc(config.vision_model||'')}" placeholder="填写服务商支持图片的模型 ID"></label></div>
    <label>API Key<input name="api_key" type="password" autocomplete="off" placeholder="${config.key_configured?'已配置，留空保留':'输入服务商 Key'}"></label>
    <label class="check-option"><input name="enabled" type="checkbox" ${config.enabled?'checked':''}>启用外部服务</label><label class="check-option"><input name="clear_key" type="checkbox">清除保存的 Key</label>
    <p class="subtle">${esc(config.data_scope)}</p><div class="actions"><button class="primary">保存配置</button><button type="button" id="test-provider">测试对话与工具调用</button></div><p id="provider-result" role="status"></p></form>
    <details><summary>已安装的组件和版本</summary><dl class="metadata">${Object.entries(runtime.packages).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl><p>${esc(runtime.workflow)}</p></details>
    <details><summary>工程工具 ${runtime.tools.length} 项</summary><ul>${runtime.tools.map(t=>`<li><code>${esc(t.function.name)}</code> · ${esc(t.function.description)}</li>`).join('')}</ul></details>
    <details><summary>对外 API 和 MCP</summary><p>进入项目的「建模工作区 → 项目 API / MCP」创建限制项目范围、权限与有效期的 Token。外部 Agent 通过 MCP 调用相同的准入和计算链。</p><p><a href="/openapi.json" target="_blank" rel="noopener">下载 OpenAPI 契约 ↗</a></p><code>python -m backend.mcp_server</code></details>`);
    document.querySelector('#provider-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{
      const body={endpoint:f.get('endpoint'),model:f.get('model'),vision_model:f.get('vision_model')||null,enabled:f.has('enabled'),clear_key:f.has('clear_key')};
      if(f.get('api_key'))body.api_key=f.get('api_key');
      await request('/developer/provider',{method:'PUT',body:JSON.stringify(body)});
      document.querySelector('[name=api_key]').value='';document.querySelector('#provider-result').textContent='配置已保存；请测试真实连接。';notice('Provider 配置已保存');
    },e.submitter);};
    document.querySelector('#test-provider').onclick=e=>action(async()=>{
      const output=document.querySelector('#provider-result');output.textContent='正在请求已保存的服务配置…';
      try{const result=await post('/developer/provider/test',{});output.textContent=result.tool_calling_observed?'连接成功，已观察到真实工具调用；测试未执行工程工具。':'服务已响应，本次未返回工具调用，请核对模型能力。';}
      catch(error){output.textContent=error.message;throw error;}
    },e.currentTarget);
  });
}

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
