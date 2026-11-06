import {escape as esc} from './api.js';

export function capabilityMarkup(answer) {
  const rows=answer?.capability_assessments || [];
  if(!rows.length)return '';
  return `<section class="agent-artifact" aria-label="当前应用能力说明"><h3>应用能做什么</h3><p class="subtle">以下是当前版本的功能范围，不代表本项目输入充分、依赖就绪或工程任务已完成。</p>${rows.map(row=>`<article><h4>${esc(row.title)} · ${row.assessment==='not_supported'?'应用不支持':'支持有限辅助'}</h4><p>${esc(row.scope)}</p><p>${esc(row.next_step)}</p><details><summary>查看版本依据</summary><p>${esc(row.source_module)}</p><small class="mono">${esc(row.source_hash)}</small><p class="subtle">源码摘要用于追溯版本，不是功能运行成功或专业认证的证明。</p></details></article>`).join('')}</section>`;
}
