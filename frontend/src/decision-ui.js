import {request, post, escape as esc, number as num} from './api.js';
import {createPoller} from './polling.js';
import {runAgent} from './trust-ui.js';

const fieldLabel = {
  conductivity_w_mk:'导热系数', density_kg_m3:'密度', specific_heat_j_kgk:'比热',
  thermal_evidence_id:'热工参数证据', sample_evidence_id:'样品批次证据', control_evidence_id:'对照测试证据',
  aging_evidence_id:'老化测试证据', source_locator:'参数来源定位', test_conditions:'测试条件',
  applicability:'工程适用范围', material_review:'材料参数复核', thermal_evidence_review:'热工证据复核', batch:'样品批次',
};
const metricLabel = {energy_kwh:'年能耗 kWh', cost_cny:'增量初始造价 CNY', cooling_unmet_h:'占用制冷未达设定点 h', carbon_kg:'运行 CO₂ kg'};
const statusLabel = {FEASIBLE:'满足所填约束', EXCLUDED:'未满足约束', INCOMPLETE:'缺少决策指标', FAILED:'计算失败',
  running:'正在计算', succeeded:'计算完成', failed:'研究失败', stale:'证据已失效', CANDIDATES_FOR_REVIEW:'已形成待复核候选', NO_ELIGIBLE_CANDIDATE:'没有满足条件的候选'};
const gapLabel = key => fieldLabel[key] || (key.endsWith('_not_measured') ? (fieldLabel[key.replace('_not_measured','')] || key) + '尚非已复核实测' : key);

export function optionalNumber(value) {
  if (String(value ?? '').trim() === '') return null;
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error('数值必须是有限数字');
  return number;
}

export function paretoPlot(assessment) {
  const rows = assessment.rows.filter(r => r.values.energy_kwh !== null && r.values.cost_cny !== null);
  if (!rows.length) return '<p class="subtle">填入造价后可查看能耗与成本取舍图。</p>';
  const xs=rows.map(r=>r.values.cost_cny), ys=rows.map(r=>r.values.energy_kwh);
  const minX=Math.min(0,...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
  const x=v=>70+(v-minX)/(maxX-minX||1)*470, y=v=>245-(v-minY)/(maxY-minY||1)*170;
  return `<svg class="pareto-plot" viewBox="0 0 620 310" role="img" aria-label="候选方案的成本与年能耗散点图，左下方向表示两项指标更低"><path d="M70 55V245H550" fill="none" stroke="currentColor"/><text x="20" y="30">年能耗 kWh</text><text x="315" y="295">增量初始造价 CNY →</text><text x="7" y="70">${num(maxY,0)}</text><text x="7" y="245">${num(minY,0)}</text><text x="65" y="267">${num(minX,0)}</text><text x="500" y="267">${num(maxX,0)}</text>${rows.map(r=>`<g class="${assessment.pareto_option_ids.includes(r.option_id)?'pareto-candidate':'pareto-other'}"><circle cx="${x(r.values.cost_cny)}" cy="${y(r.values.energy_kwh)}" r="6"><title>${esc(r.name)} · ${num(r.values.cost_cny)} CNY · ${num(r.values.energy_kwh)} kWh · ${esc(statusLabel[r.status])}</title></circle><text x="${x(r.values.cost_cny)+9}" y="${y(r.values.energy_kwh)-9}">${esc(r.option_id)}</text></g>`).join('')}</svg><p class="subtle">绿色为所选全部目标的非支配候选。图中仅显示造价、能耗两轴；完整约束与排除依据见表格。</p>`;
}

export function assessmentMarkup(study) {
  const a=study.assessment;
  if (!a) return `<div class="decision-empty"><strong>${study.assessment_stale?'碳因子已更新，决策评估需刷新':esc(statusLabel[study.status]||study.status)}</strong><p>${esc(study.error||study.stale_reasons?.join('；')||'当前还没有可引用的方案结论。')}</p>${study.assessment_stale?`<button data-reevaluate="${esc(study.study_id)}">仅重新评估 · 无需重新仿真</button>`:''}</div>`;
  return `<div class="decision-summary"><strong>${esc(statusLabel[a.status])}</strong><p>材料候选已完成 ${a.evaluated_options} / ${a.total_options} 个 · 真实引擎调用 ${study.engine_calls} 次 · 未测试 ${a.untested_options.length} 个</p><p>待复核非支配候选：${a.pareto_option_ids.map(esc).join('、')||'无'}</p></div>${paretoPlot(a)}<div class="table-scroll"><table><thead><tr><th>方案 / 来源性质</th><th>年能耗 kWh</th><th>节能率 %</th><th>增量造价 CNY</th><th>制冷未达 h</th><th>运行 CO₂ kg</th><th>判断与原因</th></tr></thead><tbody>${a.rows.map(r=>`<tr><td><strong>${esc(r.name)}</strong><small>${esc(r.option_id)} · 参数 ${esc(r.source_nature||'未提供')}</small><small>费用 ${esc(r.cost_source_nature||'未知')}</small></td><td>${num(r.values.energy_kwh)}</td><td>${num(r.energy_saving_pct)}</td><td>${num(r.values.cost_cny)}</td><td>${num(r.values.cooling_unmet_h)}</td><td>${num(r.values.carbon_kg)}</td><td>${esc(statusLabel[r.status])}${r.dominated_by.length?'<small>在所选目标上被 '+r.dominated_by.map(esc).join('、')+' 支配</small>':''}${r.missing.length?'<small>缺少 '+r.missing.map(k=>esc(metricLabel[k]||k)).join('、')+'</small>':''}${r.violations.map(v=>'<small>'+esc(({max_cost_cny:'造价上限',max_cooling_unmet_h:'制冷未达时长上限',max_heating_unmet_h:'供暖未达时长上限',min_energy_saving_pct:'最低节能率'})[v.constraint])+': '+num(v.actual)+' / '+num(v.limit)+'</small>').join('')}${r.warnings?'<small>'+r.warnings+' 条 Warning 待复核</small>':''}</td></tr>`).join('')}</tbody></table></div><p class="subtle">${esc(a.explanation)} · 碳排采用${a.factor_snapshot.scenario?'声明的情景':'登记的'}因子。舒适性小时数分别核对，不合并成总时长。</p>`;
}

function diagnosisMarkup(value) {
  return `<p class="subtle">${esc(value.priority_basis)}</p><ol class="diagnosis-tasks">${value.tasks.map(t=>`<li><span class="task-priority">${t.priority===1?'计算前完成':t.priority===2?'决策前核对':'实验验证'}</span><div><strong>${esc(t.title)}</strong><p>${esc(t.action)}</p></div><button data-go="${esc(t.target_view)}">去处理</button></li>`).join('')}</ol>`;
}

export async function decisionWorkspace(state, host, action, modal, navigate) {
  const pid=state.project.project_id, base='/projects/'+pid;
  const [diagnosis, runs, evidence]=await Promise.all([request(base+'/diagnosis'),request(base+'/runs'),request(base+'/evidence')]);
  if (!host.isConnected) return;
  let cards=diagnosis.materials, catalog=[], catalogSequence=0;
  const eligibleEvidence=evidence.filter(e=>e.review_state==='confirmed'&&!['MISSING','AI_INFERRED'].includes(e.status));
  const sourceOptions=(selected='')=>'<option value="">尚未提供</option>'+eligibleEvidence.map(e=>`<option value="${e.evidence_id}" ${e.evidence_id===selected?'selected':''}>${esc(e.name)} · v${e.revision} · ${esc(e.status)}</option>`).join('');
  const baselineRuns=runs.filter(r=>r.scheme_id==='baseline'&&r.status==='succeeded');
  host.innerHTML=`<div class="view-heading"><div><span class="eyebrow">资料 → 材料 → 真实仿真 → 方案决策</span><h1>材料与工程决策</h1><p>把检测参数变成可复算的材料方案，按工程目标与约束看清取舍。</p></div><button id="refresh-diagnosis">更新诊断</button></div>
    <details class="decision-section" open><summary>1 · 项目诊断与补证任务</summary><div id="decision-diagnosis">${diagnosisMarkup(diagnosis)}</div></details>
    <section class="decision-section"><div class="section-title"><h2>2 · 候选材料验证</h2><button id="new-material">登记材料</button></div><p class="subtle">参数经来源复核后用于条件仿真；材料批次、对照和老化记录分别追踪。</p><div id="material-cards"></div></section>
    <section class="decision-section"><h2>3 · 创建材料方案研究</h2><p class="subtle">从已核验基准复制新模型，替换一个现有不透明构造层。原始模型及历史运行保留。</p><form id="decision-form">
    <div class="form-grid"><label>基准运行<select name="source_run_id" required><option value="">选择当前有效 baseline</option>${baselineRuns.map(r=>`<option value="${r.run_id}">${esc(r.created_at)} · ${r.run_id.slice(0,16)}</option>`).join('')}</select></label><label>要替换的材料层<select name="target_material" required><option value="">先选择基准运行</option></select></label></div><div id="material-mapping" class="form-note">会列出实际关联的构造、表面和区域，确认此次材料变更范围。</div>
    <div id="option-rows"></div><button type="button" id="add-option">添加材料候选（最多 12 个）</button>
    <fieldset class="decision-objectives"><legend>比较目标（均取较小值，至少一项）</legend>${Object.entries(metricLabel).map(([key,label])=>`<label class="check-option"><input type="checkbox" name="objectives" value="${key}" ${['energy_kwh','cost_cny'].includes(key)?'checked':''}>${label}</label>`).join('')}</fieldset>
    <details><summary>工程约束（留空表示未声明）</summary><div class="form-grid"><label>增量造价上限 CNY<input name="max_cost_cny" type="number" min="0" step="any"></label><label>占用制冷未达时长上限 h<input name="max_cooling_unmet_h" type="number" min="0" max="8784" step="any"></label><label>占用供暖未达时长上限 h<input name="max_heating_unmet_h" type="number" min="0" max="8784" step="any"></label><label>最低节能率 %<input name="min_energy_saving_pct" type="number" min="0" max="100" step="any"></label></div></details>
    <label>此次候选集与工程约束的依据<textarea name="basis" required minlength="5" maxlength="2000" placeholder="说明为何选择这些材料和厚度、造价范围以及舒适性阈值的依据"></textarea></label><label>最多运行候选数<input name="budget" type="number" min="1" max="12" value="3" required></label><p class="form-note">每个材料候选调用一次 EnergyPlus，基准复用已有原始结果。预算不足时按提交顺序测试，报告会列出未测试候选。造价未提供时保持未知。</p><div class="actions"><button class="primary" type="submit">开始真实方案比较</button><button name="agent" type="submit">由助手执行这份计划</button></div><div id="study-submission" role="status"></div></form></section>
    <section class="decision-section"><h2>4 · 决策结果与同源报告</h2><div id="decision-studies"></div></section>`;
  const bindNavigation=()=>host.querySelectorAll('[data-go]').forEach(button=>{button.onclick=()=>{if(button.dataset.go==='decision')host.querySelector('#material-cards').scrollIntoView({block:'start'});else navigate(button.dataset.go);};});
  bindNavigation();
  const renderCards=()=>{
    host.querySelector('#material-cards').innerHTML=cards.length?cards.map(card=>`<article class="material-card"><header><strong>${esc(card.name)}</strong><span class="badge">${card.can_simulate?'可作参数情景':'待补齐/复核'} · ${esc(card.source_nature)}</span></header><p>批次 ${esc(card.batch||'未知')} · λ ${num(card.conductivity_w_mk,4)} W/(m·K) · ρ ${num(card.density_kg_m3)} kg/m³ · c ${num(card.specific_heat_j_kgk)} J/(kg·K)</p><p>${esc(card.test_conditions||'测试条件待补齐')}</p><p>${esc(card.stale_reasons.join('；'))}${card.simulation_gaps.map(g=>esc(gapLabel(g))).join('、')}</p><p class="subtle">验证待办：${card.validation_gaps.map(g=>esc(gapLabel(g))).join('、')||'记录已关联；实验正确性和工程性能仍需专业复核'}</p><button data-edit-material="${card.material_id}">查看 / 修订参数与证据</button><small> v${card.revision} · ${esc(card.responsible_person)}</small></article>`).join(''):'<p class="empty">尚无材料卡。登记已有检测参数，或先保存待补齐材料。</p>';
    host.querySelectorAll('[data-edit-material]').forEach(b=>{b.onclick=()=>editMaterial(cards.find(c=>c.material_id===b.dataset.editMaterial));});
    host.querySelectorAll('[data-material-select]').forEach(select=>{const previous=select.value;select.innerHTML='<option value="">选择已复核材料</option>'+cards.filter(c=>c.can_simulate).map(c=>`<option value="${c.material_id}">${esc(c.name)} · ${esc(c.source_nature)}</option>`).join('');select.value=previous;});
  };
  const refreshDiagnosis=async()=>{const value=await request(base+'/diagnosis');if(!host.isConnected)return;cards=value.materials;host.querySelector('#decision-diagnosis').innerHTML=diagnosisMarkup(value);renderCards();bindNavigation();};
  host.querySelector('#refresh-diagnosis').onclick=e=>action(refreshDiagnosis,e.currentTarget);
  function editMaterial(card) {
    const c=card||{};
    const dialog=modal(card?'修订材料卡':'登记候选材料',`<form id="material-form"><div class="form-grid"><label>材料名称<input name="name" value="${esc(c.name||'')}" required maxlength="160"></label><label>样品批次<input name="batch" value="${esc(c.batch||'')}" maxlength="200"></label></div><label class="check-option"><input name="contains_rare_earth" type="checkbox" ${c.contains_rare_earth?'checked':''}>含稀土功能材料（仅登记，不推断性能）</label><div class="form-grid">${[['conductivity_w_mk','导热系数 W/(m·K)',0.000001,100],['density_kg_m3','密度 kg/m³',0.000001,30000],['specific_heat_j_kgk','比热 J/(kg·K)',100,20000]].map(([key,label,min,max])=>`<label>${label}<input type="number" name="${key}" step="any" min="${min}" max="${max}" value="${c[key]??''}"></label>`).join('')}</div>${['thermal_evidence_id','sample_evidence_id','control_evidence_id','aging_evidence_id'].map(key=>`<label>${fieldLabel[key]}<select name="${key}">${sourceOptions(c[key])}</select></label>`).join('')}<p class="subtle">这里选择已复核证据。没有合适来源时先到“资料”导入并确认；也可保存待补齐材料卡。</p>${[['source_locator','参数所在页码 / 表格 / 测点'],['test_conditions','测试温度、含水率、方法与误差等条件'],['applicability','材料适用构造与工程限制'],['review_note','参数核对依据']].map(([key,label])=>`<label>${label}<textarea name="${key}" maxlength="2000">${esc(c[key]||'')}</textarea></label>`).join('')}<label>复核责任人<input name="responsible_person" value="${esc(c.responsible_person||'')}" required maxlength="100"></label><label class="check-option"><input name="confirmed" type="checkbox" ${c.review_state==='confirmed'?'checked':''}>已核对参数与来源，可用于声明条件下的仿真</label><button class="primary">保存${card?'新版本':'材料卡'}</button></form>`);
    dialog.querySelector('form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{
      const payload=Object.fromEntries([...f.entries()].filter(([k])=>!['confirmed','contains_rare_earth'].includes(k)).map(([k,v])=>[k,v||null]));
      for(const key of ['conductivity_w_mk','density_kg_m3','specific_heat_j_kgk'])payload[key]=optionalNumber(f.get(key));
      payload.contains_rare_earth=f.has('contains_rare_earth');payload.review_state=f.has('confirmed')?'confirmed':'pending';
      if(card)payload.expected_revision=card.revision;
      await request(base+'/materials'+(card?'/'+card.material_id:''),{method:card?'PUT':'POST',body:JSON.stringify(payload)});
      dialog.close();await refreshDiagnosis();
    },e.submitter);};
  }
  host.querySelector('#new-material').onclick=()=>editMaterial();
  const form=host.querySelector('#decision-form');
  const addOption=()=>{
    const rows=host.querySelector('#option-rows');if(rows.children.length>=12)return;
    const row=document.createElement('fieldset');row.className='material-option';
    row.innerHTML=`<legend>候选材料方案</legend><div class="form-grid"><label>方案名称<input name="name" required maxlength="160"></label><label>材料卡<select name="material_id" data-material-select required></select></label><label>替换层厚度 m<input name="thickness_m" type="number" min=".003" max="2" step="any" required placeholder="例如 0.08"></label><label>增量初始造价 CNY<input name="cost_cny" type="number" min="0" max="1000000000" step="any" placeholder="未知则留空"></label></div><label>造价来源<select name="cost_evidence_id">${sourceOptions()}</select></label><label>造价包括哪些工作、对应多少面积<textarea name="cost_scope" maxlength="2000" placeholder="含材料/安装/脚手架等范围与增量口径"></textarea></label><button type="button" data-remove-option>移除此候选</button>`;
    row.querySelector('[data-remove-option]').onclick=()=>row.remove();rows.append(row);renderCards();
  };
  host.querySelector('#add-option').onclick=addOption;addOption();
  const showMapping=()=>{const item=catalog.find(m=>m.name===form.elements.target_material.value);host.querySelector('#material-mapping').innerHTML=item?`<strong>替换 ${esc(item.name)} 将影响 ${item.surfaces.length} 个实际 IDF 表面</strong><p>当前厚度 ${num(item.thickness_m,4)} m · 导热系数 ${num(item.conductivity_w_mk,4)} W/(m·K)</p><details><summary>核对关联的构造、表面与区域</summary><ul>${item.surfaces.map(s=>`<li>${esc(s.name)} / ${esc(s.type)} / ${esc(s.construction)} / ${esc(s.zone)}</li>`).join('')}</ul></details><p>${esc(item.limitation)}</p>`:'请选择材料层。';};
  form.elements.target_material.onchange=showMapping;
  form.elements.source_run_id.onchange=()=>action(async()=>{const token=++catalogSequence,rid=form.elements.source_run_id.value;catalog=[];form.elements.target_material.innerHTML='<option value="">正在读取模型…</option>';if(!rid)return;const result=await request(base+'/material-targets/'+rid);if(!host.isConnected||token!==catalogSequence)return;catalog=result;form.elements.target_material.innerHTML='<option value="">选择实际构造材料层</option>'+catalog.filter(m=>m.supported).map(m=>`<option value="${esc(m.name)}">${esc(m.name)} · ${m.surfaces.length} 个表面</option>`).join('');showMapping();});
  let previous;
  const refreshStudies=async()=>{const studies=await request(base+'/studies');if(!host.isConnected)return;const snapshot=JSON.stringify(studies);if(snapshot===previous)return;previous=snapshot;host.querySelector('#decision-studies').innerHTML=studies.map(study=>`<article class="study-result"><h3>${esc(study.target_material)} · ${esc(statusLabel[study.status]||study.status)}</h3><small class="mono">${esc(study.study_id)}</small>${assessmentMarkup(study)}<div class="actions">${study.status!=='running'?['json','html','pdf'].map(ext=>`<a target="_blank" rel="noopener" href="/api${base}/studies/${study.study_id}/report.${ext}">${ext.toUpperCase()} 报告 ↗</a>`).join('')+`<a target="_blank" rel="noopener" href="/api${base}/studies/${study.study_id}/artifacts">原始证据 ZIP ↗</a>`:''}</div><details><summary>声明条件与来源版本</summary><ul>${study.limitations.map(l=>'<li>'+esc(l)+'</li>').join('')}</ul><pre>${esc(JSON.stringify({basis:study.basis,mapping:study.mapping,material_snapshots:study.material_snapshots,cost_snapshots:study.cost_snapshots},null,2))}</pre></details></article>`).join('')||'<p class="empty">完成上方方案计划后，将生成真实结果和可复核候选。</p>';host.querySelectorAll('[data-reevaluate]').forEach(b=>{b.onclick=()=>action(async()=>{await post(base+'/studies/'+b.dataset.reevaluate+'/reevaluate',{});await refreshStudies();},b);});};
  const poller=createPoller(async()=>{if(!host.isConnected){poller.stop();return;}await refreshStudies();},{interval:5000,onError:()=>{previous=null;if(host.isConnected)host.querySelector('#decision-studies').textContent='连接中断，当前方案结论暂不可核验，正在重连。';}});
  form.onsubmit=e=>{e.preventDefault();const button=e.submitter;action(async()=>{
    const f=new FormData(form), objectives=f.getAll('objectives');
    if(!objectives.length)throw new Error('请至少选择一项比较目标');
    const optionRows=[...host.querySelectorAll('.material-option')];if(!optionRows.length)throw new Error('请至少添加一个材料候选');
    const options=optionRows.map((row,index)=>{const value=k=>row.querySelector('[name="'+k+'"]').value;return {option_id:'C'+String(index+1).padStart(2,'0'),name:value('name'),material_id:value('material_id'),thickness_m:optionalNumber(value('thickness_m')),cost_cny:optionalNumber(value('cost_cny')),cost_evidence_id:value('cost_evidence_id')||null,cost_scope:value('cost_scope')||null};});
    const plan={source_run_id:f.get('source_run_id'),target_material:f.get('target_material'),options,objectives,budget:Number(f.get('budget')),basis:f.get('basis'),constraints:Object.fromEntries(['max_cost_cny','max_cooling_unmet_h','max_heating_unmet_h','min_energy_saving_pct'].map(k=>[k,optionalNumber(f.get(k))]))};
    if(button.name==='agent')await runAgent(state,'按此确认计划执行材料方案研究，并核对约束与候选集。',host.querySelector('#study-submission'),'local',true,plan);
    else await post(base+'/studies',plan);
    if(!host.isConnected)return;if(button.name!=='agent')host.querySelector('#study-submission').textContent='已提交。下方会持续显示真实计算进度与方案判断。';await refreshStudies();poller.start();
  },button);};
  await refreshStudies();if(host.isConnected)poller.start();
}
