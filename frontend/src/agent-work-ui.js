import {escape as esc,number as num} from './api.js';

export function modelMarkup(value){
  const inline=text=>esc(text).replace(/\*\*([^*]{1,300})\*\*/g,'<strong>$1</strong>').replace(/`([^`]{1,300})`/g,'<code>$1</code>');
  const lines=String(value||'').slice(0,30000).split(/\r?\n/),out=[];
  const cells=line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(v=>v.trim());
  for(let i=0;i<lines.length;i++){
    const line=lines[i].trim();if(!line)continue;
    if(line.includes('|')&&/^\|?\s*:?-{2,}/.test(lines[i+1]?.trim()||'')){
      const head=cells(line),rows=[];i++;
      while(i+1<lines.length&&lines[i+1].includes('|'))rows.push(cells(lines[++i]));
      out.push(`<div class="table-scroll"><table><thead><tr>${head.map(v=>`<th>${inline(v)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${inline(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
    }else if(/^#{1,4}\s/.test(line))out.push(`<h4>${inline(line.replace(/^#{1,4}\s+/,''))}</h4>`);
    else if(/^[-*]\s/.test(line)){
      const items=[line.replace(/^[-*]\s+/, '')];while(/^[-*]\s/.test(lines[i+1]?.trim()||''))items.push(lines[++i].trim().replace(/^[-*]\s+/,''));
      out.push(`<ul>${items.map(v=>`<li>${inline(v)}</li>`).join('')}</ul>`);
    }else out.push(`<p>${inline(line)}</p>`);
  }
  if(String(value||'').length>30000)out.push('<p>说明较长，界面显示前30000字符，完整内容保留在任务记录。</p>');
  return out.join('');
}

export function agentWorkMarkup(task){
  const plans=task.work_plans||[],products=task.work_products||[],questions=task.input_questions||[];
  return `${task.mode==='provider'?`<p class="form-note">模型自主工程调用 ${num(task.model_tool_calls??task.events?.filter(e=>['model','model_plan'].includes(e.origin)&&e.status==='succeeded').length,0)} 次 · 已保存提议 ${products.length} 份${task.parent_task_id?' · 接续已有任务':''}。读取或提议完成不表示工程合格。</p>`:''}
  ${task.llm_commentary?`<section class="agent-synthesis"><h3>AI工程分析</h3><div class="model-prose">${modelMarkup(task.llm_commentary)}</div><small>说明及取舍需复核；正式数值以实际工程工具和来源为准。</small></section>`:''}
  ${plans.map(p=>`<section class="decision-section"><h3>模型编排的工作计划</h3><p>${esc(p.goal)}</p><ol>${p.steps.map(s=>`<li><strong>${esc(s.purpose)}</strong> · ${esc(({succeeded:'工具已执行',failed:'执行失败',skipped:'依赖未满足，未执行',running:'执行中'})[s.status]||'待执行')}<small>${esc(s.tool)}${s.depends_on.length?' · 前序 '+s.depends_on.map(esc).join('、'):''}</small>${s.error?`<p class="error-text">${esc(s.error)}</p>`:''}</li>`).join('')}</ol></section>`).join('')}
  ${products.map(p=>`<section class="decision-section"><header><h3>材料方向提议 · 待复核</h3><span class="badge">${p.current===false?'来源版本已变化':'未批准工程使用'}</span></header><p>${esc(p.goal)}</p><ul>${p.requirements.map(r=>`<li>${esc(r)}</li>`).join('')}</ul><div class="form-grid">${p.directions.map(d=>`<article class="material-card"><strong>${esc(d.source.name)}</strong><p>${esc(d.reason)}</p><p>取舍与未知：${esc(d.tradeoff)}</p><small>${esc(({research_only:'跨域/研究用途，不作采购候选',rare_earth_direction:'稀土研究方向',conventional_direction:'常规对照方向'})[d.role])}</small><a href="${esc(d.source.url)}" target="_blank" rel="noopener">原始出处 ↗</a></article>`).join('')}</div><p class="subtle">工程量、产品价格、节能率和可售碳信用尚未由本提议确定。</p><button type="button" data-review-shortlist="${esc(p.product_id)}" ${p.current===false?'disabled':''}>带入材料工作区复核</button></section>`).join('')}
  ${questions.length?`<section class="decision-section"><h3>需要补充后继续</h3><ol>${questions.map(q=>`<li><strong>${esc(q.question)}</strong><p>${esc(q.why_needed)}</p></li>`).join('')}</ol></section>`:''}
  ${task.status!=='running'?`<form data-agent-follow-up><label>补充资料或继续本次任务<textarea name="follow_up" required minlength="2" maxlength="4000" placeholder="例如：仅比较窗改造，预算20万元，工程量还没有确认。"></textarea></label><label class="check-option"><input type="checkbox" name="document_text">本次允许AI读取有来源的有限资料摘录</label><label class="check-option"><input type="checkbox" name="compute">本次允许计算（仍须满足工程输入与计划要求）</label><button class="primary" type="submit">根据补充继续任务</button><p class="subtle">保存为关联的新任务，重新读取当前依据；历史任务和失败保留。</p><p data-follow-up-error role="alert"></p></form>`:''}`;
}
