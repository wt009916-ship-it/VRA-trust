import {escape as esc} from './api.js';

export const stageLabels={production:'材料生产',transport:'材料运输',construction:'施工',operation:'建筑运行',end_of_life:'寿命末期'};
const units=['kg','t','tkm','kWh','m3','m2','item'];
const input=(name,label,type='text',extra='',value='')=>`<label>${esc(label)}<input name="${esc(name)}" type="${type}" ${extra} value="${esc(value)}"></label>`;
const select=(name,label,items)=>`<label>${esc(label)}<select name="${esc(name)}">${items.map(([v,l])=>`<option value="${esc(v)}">${esc(l)}</option>`).join('')}</select></label>`;
export const evidenceSelect=(name,label,records,multiple=false)=>`<label>${esc(label)}<select name="${esc(name)}" ${multiple?'multiple':''}>${multiple?'':'<option value="">仅用户声明</option>'}${records.map(e=>`<option value="${esc(e.evidence_id)}">${esc(e.name)} · v${e.revision}</option>`).join('')}</select></label>`;
const number=(data,key)=>{const value=String(data.get(key)??'').trim();return value===''?null:Number(value);};
const value=(data,key)=>String(data.get(key)??'').trim();

export function carbonBoundaryMarkup(){
 return `<h3>共同碳核算边界</h3><p>纳入的阶段缺少活动或因子时保持不完整；排除不等于零排放。两个方案使用同一评估期和边界。</p><div class="scenario-fields">${Object.entries(stageLabels).map(([stage,label])=>`<fieldset data-carbon-boundary="${stage}"><legend>${label}</legend><label><input type="checkbox" name="boundary_${stage}" ${stage==='production'?'checked disabled':''}>纳入两个方案</label>${input('boundary_reason_'+stage,'纳入范围或排除理由','text','required minlength="5"',stage==='production'?'按含损耗采购材料量核算生产阶段':'本次明确未纳入该阶段')}</fieldset>`).join('')}</div>`;
}

export function carbonEditorsMarkup(){
 return `<h3>其他阶段活动与运输</h3><p>运输可从已选材料采购量派生；其他活动须有明确来源。运行年量仅按评估年限线性累计，不是材料替换自动产生的节能预测。</p>${[0,1].map(i=>`<section data-carbon-alternative="${i}"><h4>方案${i+1} · 阶段活动</h4><div data-transport-rows></div><button type="button" data-add-transport>添加材料运段</button><div data-activity-rows></div><button type="button" data-add-carbon-activity>添加其他阶段活动</button></section>`).join('')}`;
}

function factorMarkup(prefix,stage,evidence){
 return `<details><summary>排放因子来源与适用范围（必填）</summary><div class="scenario-fields">${input(prefix+'factor_id','因子唯一编号','text','required')}${input(prefix+'factor_value','因子数值 kgCO₂e/单位（未知留空）','number','min="0" step="any"')}${stage==='transport'?'<p>因子分母固定为 tkm（吨公里）。</p>':select(prefix+'denominator','因子分母单位',units.map(x=>[x,x]))}${input(prefix+'factor_source','因子来源与位置','text','required minlength="5"')}${input(prefix+'publisher','发布方','text','required minlength="2"')}${input(prefix+'version','因子版本','text','required')}${input(prefix+'year','因子年份','number','required min="1900" max="2100"')}${input(prefix+'factor_region','因子适用地区（通用填*）','text','required')}${input(prefix+'factor_method','因子方法及版本（须与方案一致）','text','required minlength="3"')}${evidenceSelect(prefix+'factor_evidence','绑定因子来源证据',evidence)}</div></details>`;
}

function readFactor(data,prefix,stage,transport=false){
 return {factor_id:value(data,prefix+'factor_id'),value:number(data,prefix+'factor_value'),denominator:transport?'tkm':value(data,prefix+'denominator'),
  stage,numerator:'kgCO2e',source:value(data,prefix+'factor_source'),publisher:value(data,prefix+'publisher'),version:value(data,prefix+'version'),year:number(data,prefix+'year'),
  region:value(data,prefix+'factor_region'),method:value(data,prefix+'factor_method'),evidence_id:value(data,prefix+'factor_evidence')||null};
}

export function readCarbonEditors(data){
 const boundaries=Object.keys(stageLabels).map(stage=>({stage,included:stage==='production'||data.has('boundary_'+stage),reason:value(data,'boundary_reason_'+stage)}));
 const alternatives=[0,1].map(i=>({transport_legs:[],other_activities:[]}));
 for(const [name,id] of data.entries()){
  const match=/^carbon_(transport|activity)_([01])_(\d+)_id$/.exec(name);if(!match)continue;
  const [,kind,index,sequence]=match,prefix=`carbon_${kind}_${index}_${sequence}_`;
  if(kind==='transport')alternatives[Number(index)].transport_legs.push({leg_id:id,name:value(data,prefix+'name'),layer_ids:data.getAll(prefix+'layers').map(Number),
   purchase_fraction:number(data,prefix+'purchase_fraction'),fraction_source:value(data,prefix+'fraction_source'),distance_km:number(data,prefix+'distance'),distance_source:value(data,prefix+'distance_source'),
   additional_mass_kg:number(data,prefix+'additional_mass'),additional_mass_source:value(data,prefix+'additional_mass_source'),factor:readFactor(data,prefix,'transport',true),evidence_ids:data.getAll(prefix+'source_evidence')});
  else{const stage=value(data,prefix+'stage');alternatives[Number(index)].other_activities.push({activity_id:id,name:value(data,prefix+'name'),stage,
   quantity:number(data,prefix+'quantity'),unit:value(data,prefix+'unit'),period:value(data,prefix+'period'),source:value(data,prefix+'source'),
   source_evidence_ids:data.getAll(prefix+'source_evidence'),factor:readFactor(data,prefix,stage)});}
 }
 return {boundaries,alternatives};
}

export function bindCarbonEditors(form,takeoff,evidence){
 let sequence=0;
 for(const boundary of form.querySelectorAll('[data-carbon-boundary]')){
  const check=boundary.querySelector('[type=checkbox]'),reason=boundary.querySelector('[type=text]');
  check.onchange=()=>{if(reason.value==='本次明确未纳入该阶段')reason.value='';};
 }
 function add(section,kind){
  sequence++;const index=section.dataset.carbonAlternative,prefix=`carbon_${kind}_${index}_${sequence}_`;
  const row=document.createElement('fieldset');row.dataset.carbonRow=kind;
  row.innerHTML=`<legend>${kind==='transport'?'材料运段':'阶段活动'} ${sequence}</legend>${input(prefix+'id','唯一编号','text','required',kind+'_'+sequence)}${input(prefix+'name',kind==='transport'?'运段名称与运输方式':'活动名称','text','required minlength="2"')}`;
  if(kind==='transport')row.innerHTML+=`<p>只选该运段承运的材料层，不能包含方案已排除的层。分批比例针对采购材料；包装/托盘附加质量单列。</p><div class="scenario-fields">${takeoff.result.layers.map(r=>`<label><input type="checkbox" name="${prefix}layers" value="${r.layer_id}" checked>#${r.layer_id} ${esc(r.material_name||'未命名')}</label>`).join('')}${input(prefix+'purchase_fraction','该运段承运的采购材料比例（未知留空）','number','min="0.000001" max="1" step="any"')}${input(prefix+'fraction_source','分批比例依据','text','required minlength="5"')}${input(prefix+'distance','本运段距离 km（未知留空）','number','min="0" max="1000000" step="any"')}${input(prefix+'distance_source','距离及路径依据','text','required minlength="5"')}${input(prefix+'additional_mass','本运段附加包装/托盘质量 kg（无则明确填0）','number','min="0" step="any"')}${input(prefix+'additional_mass_source','附加质量依据','text','required minlength="5"')}</div>${evidenceSelect(prefix+'source_evidence','绑定运段来源证据（可多选）',evidence,true)}${factorMarkup(prefix,'transport',evidence)}`;
  else row.innerHTML+=`<div class="scenario-fields">${select(prefix+'stage','阶段',Object.entries(stageLabels).filter(([s])=>s!=='production'))}${input(prefix+'quantity','活动量（未知留空）','number','min="0" step="any"')}${select(prefix+'unit','活动量单位',units.map(x=>[x,x]))}${select(prefix+'period','数量口径',[['whole_period','整个评估期合计'],['annual','每年（仅运行阶段）']])}${input(prefix+'source','活动量来源与定位','text','required minlength="5"')}${evidenceSelect(prefix+'source_evidence','绑定活动来源证据（可多选）',evidence,true)}</div>${factorMarkup(prefix,'activity',evidence)}`;
  row.insertAdjacentHTML('beforeend','<button type="button" data-remove-carbon-row>移除此条</button>');
  row.querySelector('[data-remove-carbon-row]').onclick=()=>row.remove();
  section.querySelector(kind==='transport'?'[data-transport-rows]':'[data-activity-rows]').append(row);
 }
 for(const section of form.querySelectorAll('[data-carbon-alternative]')){
  section.querySelector('[data-add-transport]').onclick=()=>add(section,'transport');
  section.querySelector('[data-add-carbon-activity]').onclick=()=>add(section,'activity');
 }
}
