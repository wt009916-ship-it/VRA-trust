import {escape as esc,number as num} from './api.js';
const processes={production:['生产','production'],transport:['运输','transport'],installation:['安装','construction'],removal:['旧件移除及处理','end_of_life']};
const field=(name,label,value='',extra='')=>`<label>${label}<input name="${name}" value="${esc(value??'')}" ${extra}></label>`;

export function readReplacementFields(get,readProcesses){
  const nullable=n=>get(n)===''?null:Number(get(n));
  return {component_id:get('component_id'),name:get('component_name'),condition:get('condition'),
    service_life_years:nullable('service_life_years'),remaining_life_years:nullable('remaining_life_years'),
    life_source:get('life_source'),life_evidence_id:get('life_evidence_id')||null,
    endpoint:'strictly_before_horizon',scope:'same_function_replacements_only',overlap_review:get('overlap_review'),processes:readProcesses()};
}

export function replacementResultMarkup(result){
  const ledger=result?.replacement;
  if(!ledger?.components?.length)return '<p>替换周期未单独核算；五阶段有值不证明生命周期完整。</p>';
  return `<h3>替换事件账 · 已计入使用阶段</h3><p>严格早于评估终点，初次安装与终点处置另账。寿命和未来因子是声明情景。</p><table><tr><th>构件</th><th>发生年份</th><th>次数</th><th>kgCO₂e</th><th>过程覆盖</th></tr>${ledger.components.map(c=>`<tr><td>${esc(c.name)}</td><td>${c.years===null?'寿命缺失':c.years.length?c.years.map(y=>esc(String(y))).join('、'):'评估期内无替换'}</td><td>${num(c.count,0)}</td><td>${num(c.kgco2e,6)}</td><td>${c.all_four_processes_included?'四过程纳入':'有明确排除过程'}</td></tr>`).join('')}</table><details><summary>逐次排放及过程明细</summary><pre>${esc(JSON.stringify(ledger,null,2))}</pre></details>`;
}

export function replacementEditor(host,evidence,addActivity,readActivity){
  let sequence=0;
  function add(component){
    const index=++sequence,el=document.createElement('fieldset');el.className='replacement-component';
    el.innerHTML=`<legend>构件替换 ${index}</legend><div class="form-grid">${field('component_id','稳定构件编号（比较方案保持一致）',component?.component_id,'required')}${field('component_name','构件名称',component?.name,'required')}<label>现状<select name="condition"><option value="new">新安装</option><option value="existing">已有构件</option></select></label>${field('service_life_years','新件使用寿命 / 年',component?.service_life_years,'type="number" step="any" min="0.000001" max="1000"')}${field('remaining_life_years','现有构件剩余寿命 / 年（仅已有构件）',component?.remaining_life_years,'type="number" step="any" min="0.000001" max="1000"')}${field('life_source','寿命依据与适用条件',component?.life_source,'required minlength="5"')}<label>寿命来源证据<select name="life_evidence_id"><option value="">仅用户声明</option>${evidence.map(e=>`<option value="${esc(e.evidence_id)}" ${component?.life_evidence_id===e.evidence_id?'selected':''}>${esc(e.name)} · v${e.revision}</option>`).join('')}</select></label></div>${field('overlap_review','人工复核：本账不含初次安装、终点处置，且未在基础活动重复计入的依据',component?.overlap_review,'required minlength="20"')}<p>同功能替换情景；不自动建模功能提升改造。空寿命保留缺口；不在评估终点新增无使用期的构件。</p><div class="replacement-processes"></div><button type="button" class="remove-component">移除构件替换</button>`;
    el.querySelector('[name=condition]').value=component?.condition||'new';
    for(const [key,[label,stage]] of Object.entries(processes)){
      const old=component?.processes.find(p=>p.process===key),box=document.createElement('fieldset');box.dataset.process=key;
      box.innerHTML=`<legend>每次替换 · ${label}</legend><label><input type="checkbox" name="process_included" ${old?.included===false?'':'checked'}>纳入此过程（排除不等于零）</label>${field('process_reason','范围或排除理由',old?.reason,'required minlength="5"')}<div class="process-activity"></div>`;
      const activityHost=box.querySelector('.process-activity');
      const row=addActivity(old?.activity||{activity_id:`replacement-${index}-${key}`,stage,period:'whole_period'},activityHost);
      row.querySelector('.remove-activity').remove();
      const stageSelect=row.querySelector('[name=stage]'),periodSelect=row.querySelector('[name=period]');
      stageSelect.value=stage;periodSelect.value='whole_period';
      const toggle=()=>{const included=box.querySelector('[name=process_included]').checked;activityHost.hidden=!included;activityHost.querySelectorAll('input,select').forEach(x=>x.disabled=!included);stageSelect.disabled=true;periodSelect.disabled=true;};
      box.querySelector('[name=process_included]').onchange=toggle;toggle();el.querySelector('.replacement-processes').append(box);
    }
    el.querySelector('.remove-component').onclick=()=>el.remove();host.append(el);
  }
  function read(){return [...host.children].map(el=>readReplacementFields(n=>el.querySelector(`[name=${n}]`).value,()=>[...el.querySelector('.replacement-processes').children].map(box=>({process:box.dataset.process,included:box.querySelector('[name=process_included]').checked,reason:box.querySelector('[name=process_reason]').value,activity:box.querySelector('[name=process_included]').checked?readActivity(box.querySelector('.lifecycle-activity')):null}))));}
  return {add,read,populate:items=>{host.innerHTML='';sequence=0;(items||[]).forEach(add);}};
}
