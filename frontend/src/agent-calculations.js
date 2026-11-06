import {escape as esc} from './api.js';

export function parseCalculationPlans(text, {mode, allowCompute, objective}) {
  if (!text.trim()) return [];
  const plans = JSON.parse(text);
  if (!Array.isArray(plans) || plans.length < 1 || plans.length > 2) throw new Error('计算计划须为含 1～2 项的 JSON 数组。');
  if (!allowCompute || objective !== 'open_ended' || mode === 'local') throw new Error('请选自由提问、AI 模式，并勾选允许计算后提交参数。');
  const keys = new Set();
  for (const plan of plans) {
    if (!plan || !/^[A-Za-z0-9_-]{1,40}$/.test(plan.plan_key) || keys.has(plan.plan_key)) throw new Error('每项需填写唯一 plan_key（字母、数字、下划线或短横线，最多40字符）。');
    if (!['thermal','lifecycle','cost'].includes(plan.kind) || !plan.input || typeof plan.input !== 'object' || Array.isArray(plan.input)) throw new Error('每项需包含 kind（thermal/lifecycle/cost）和完整 input 参数对象。');
    keys.add(plan.plan_key);
  }
  return plans;
}

export function calculationPlanMarkup() {
  return `<details class="agent-calculation-input"><summary>本次计算参数 · 可选</summary><p class="subtle">仅执行你明确提供的参数，最多两份；模型不能修改。本次只处理这些计划及其新记录，其他任务请另行提问。选择自由提问与 AI 模式，勾选允许计算。提交后会新建记录，不覆盖原记录；再次提交会再次新建。</p><label for="agent-calculation-plans">计算计划 JSON 数组</label><textarea id="agent-calculation-plans" rows="6" spellcheck="false" placeholder='[{"plan_key":"wall_a","kind":"thermal","input":{…完整计算参数…}}]'></textarea><p class="subtle">kind：thermal 热工、lifecycle 阶段碳、cost 材料成本。input 与对应工作台的参数一致；阶段碳和材料成本可使用工作台导出的草稿内容。缺参会保留为未完成，未经核验不交付确定数值。使用外部 AI 时，计划名称和后续读取的工程结果会发给所选服务商。</p></details>`;
}

export function calculationProgressMarkup(rows = []) {
  if (!rows.length) return '';
  const labels = {verified:'当前结果已核验', saved_unverified:'已创建记录 · 尚未形成有效交付', not_executed:'未执行'};
  return `<section aria-label="本次计算计划"><h4>本次计算计划</h4><ul>${rows.map(row => `<li><strong>${esc(row.name)}</strong> · ${esc(labels[row.state] || row.state)}<small> ${esc(row.plan_key)}${row.record_id ? ' · ' + esc(row.record_id) : ''}</small></li>`).join('')}</ul><p class="subtle">已保存的记录可在对应专业工作台查看；部分执行或失败不会自动回滚已生成记录。</p></section>`;
}
