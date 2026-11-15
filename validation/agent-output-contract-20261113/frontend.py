exec(open('D:/稀土agent-稀土制暖全流程/outputs/agent-contract-20261113/implement.py',encoding='utf-8').read().split("edit('backend/agent_outputs.py'")[0])
edit('backend/extensions.py', 'from .agent import Agent, Chat, TOOLS', 'from .agent import Agent, Chat, TOOLS\nfrom . import agent_outputs')
edit('backend/extensions.py', "__import__('backend.agent_outputs', fromlist=['public_catalog']).public_catalog()", 'agent_outputs.public_catalog()')
edit('frontend/src/agent-requests.js', 'export function collectReadRequests(host)', '''const topicLabels={meaning:'指标含义',area:'面积分母',period:'期间与年份',scope:'适用范围',status:'来源状态',history:'记录历史边界'};
export function explicitOutputMarkup(entry,purpose) {
 const topics=purpose==='availability'?['history','status']:entry.topics;
 return `<p>只锁定勾选的指标与解释主题；自由问题中的其他要求仍需核对。最多12项指标。</p>${purpose==='results'?`<label>数值指标<select data-output-facts multiple size="6">${entry.facts.map(f=>`<option value="${esc(f.key)}">${esc(f.label)}</option>`).join('')}</select></label>`:''}<fieldset><legend>解释主题</legend>${topics.map(t=>`<label><input type="checkbox" data-output-topic value="${esc(t)}">${esc(topicLabels[t]||t)}</label>`).join('')}</fieldset>`;
}

export function collectReadRequests(host)''')
edit('frontend/src/agent-requests.js', '    keys.add(r.request_key);scopes.add(scope);return r;', '''    if(row.output_contract){
      const c=row.output_contract;
      if(!Array.isArray(c.fact_keys)||!Array.isArray(c.explanation_topics)||c.fact_keys.length>12||c.explanation_topics.length>6||!c.fact_keys.length&&!c.explanation_topics.length||new Set(c.fact_keys).size!==c.fact_keys.length||new Set(c.explanation_topics).size!==c.explanation_topics.length)throw Error('请至少选择一项指标或解释，指标最多12项且不能重复。');
      if(r.purpose==='availability'&&(c.fact_keys.length||c.explanation_topics.some(t=>!['history','status'].includes(t))))throw Error('可用性检查不能要求数值。');
      r.output_contract={fact_keys:[...c.fact_keys],explanation_topics:[...c.explanation_topics]};
    }
    keys.add(r.request_key);scopes.add(scope);return r;''')
edit('frontend/src/agent-requests.js', "    record_id:row.querySelector('[data-read-id]').value}));", """    record_id:row.querySelector('[data-read-id]').value,
    ...(row.querySelector('[data-explicit-output]')?.checked?{output_contract:{
      fact_keys:[...(row.querySelector('[data-output-facts]')?.selectedOptions||[])].map(o=>o.value),
      explanation_topics:[...row.querySelectorAll('[data-output-topic]:checked')].map(o=>o.value)}}:{})}));""")
edit('frontend/src/agent-requests.js', '  let sequence=0;', '  let sequence=0,catalogPromise=null;')
edit('frontend/src/agent-requests.js', '<button type="button" data-remove-read>移除此目标</button>', '<label><input type="checkbox" data-explicit-output>锁定本项指标与解释</label><div data-output-controls hidden></div><button type="button" data-remove-read>移除此目标</button>')
edit('frontend/src/agent-requests.js', '    let generation=0,cursor=null;', """    const explicit=row.querySelector('[data-explicit-output]'),controls=row.querySelector('[data-output-controls]');
    let outputGeneration=0;
    const resetOutput=()=>{outputGeneration++;explicit.checked=false;controls.hidden=true;controls.innerHTML='';};
    explicit.onchange=e=>{
      const stamp=++outputGeneration,selected=kind.value,selectedPurpose=purpose.value;
      controls.innerHTML='';controls.hidden=!explicit.checked;
      if(!explicit.checked)return;
      controls.textContent='正在加载可选指标…';
      action(async()=>{
        catalogPromise ||= request('/agent/status').then(r=>r.output_catalog).catch(error=>{catalogPromise=null;throw error;});
        let catalog;
        try{catalog=await catalogPromise;}
        catch(error){if(row.isConnected&&stamp===outputGeneration){explicit.checked=false;controls.textContent='指标目录加载失败，未启用锁定；请重新勾选。';}throw error;}
        if(!row.isConnected||stamp!==outputGeneration||!explicit.checked)return;
        controls.innerHTML=explicitOutputMarkup(catalog[selected],selectedPurpose);
      },e.currentTarget);
    };
    let generation=0,cursor=null;""")
edit('frontend/src/agent-requests.js', 'kind.onchange=()=>{generation++;', 'kind.onchange=()=>{resetOutput();generation++;')
edit('frontend/src/agent-requests.js', "purpose.onchange=()=>{id.required", "purpose.onchange=()=>{resetOutput();id.required")
edit('frontend/src/agent-requests.js', 'onclick=()=>{generation++;row.remove();', 'onclick=()=>{outputGeneration++;generation++;row.remove();')
edit('frontend/src/agent-requests.js', '<h4>${esc(item.request_key)} · ${esc(states[out?.state]||\'待交付\')}</h4>', '<h4>${esc(item.request_key)} · ${esc(states[out?.state]||\'待交付\')}</h4><p>${item.requirement_origin===\'user_selected\'?\'要求来自用户勾选，模型不能改换；自由问题的其他要求尚未核验。\':\'要求来自模型解析，需核对是否符合原问题。\'}</p>')
print('frontend edits complete')
