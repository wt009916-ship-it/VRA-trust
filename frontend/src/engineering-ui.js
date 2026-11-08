import {bindIfcBeamProfile} from './ifc-beam-ui.js';
import {request,post,escape as esc,number as num} from './api.js';

const input=(name,label,extra='')=>`<label>${label}<input name="${name}" ${extra}></label>`;
const select=(name,label,values)=>`<label>${label}<select name="${name}">${Object.entries(values).map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></label>`;
const lengths={m:'m',cm:'cm',mm:'mm'};
const numeric='type="number" min="0" step="any"';
const statuses={calculated:'已完成线弹性计算',incomplete:'输入不完整',outside_model_screen:'超出模型筛查范围',stale:'来源或计算器已变更'};

function curve(result,key,label,unit,factor=1){
  const points=result.samples.flatMap(row=>key==='shear'?[row.shear_left_n,row.shear_right_n].filter(v=>v!==null).map(v=>[row.x_m,v*factor]):[[row.x_m,row[key]*factor]]);
  const low=Math.min(0,...points.map(p=>p[1])),high=Math.max(0,...points.map(p=>p[1])),range=high-low||1,span=result.normalized.span_m;
  const down=key==='deflection_down_m'; const y=v=>35+(down?v-low:high-v)/range*110;
  return `<figure><figcaption>${label} · ${unit}（纵向放大，仅示意变化）</figcaption><svg viewBox="0 0 720 180" role="img" aria-label="${label}沿梁长的变化曲线" style="display:block;width:100%;height:auto;max-height:220px"><path d="M50 ${y(0)} H690" stroke="currentColor" opacity=".3"/><polyline fill="none" stroke="currentColor" stroke-width="2" points="${points.map(([x,v])=>`${50+640*x/span},${y(v)}`).join(' ')}"/><text x="4" y="28" fill="currentColor" font-size="13">${num(down?low:high,5)}</text><text x="4" y="150" fill="currentColor" font-size="13">${num(down?high:low,5)}</text><text x="50" y="174" fill="currentColor" font-size="13">0 m</text><text x="620" y="174" fill="currentColor" font-size="13">${num(span,4)} m</text></svg></figure>`;
}

function loadSketch(result,support){
  const span=result.normalized.span_m,x=v=>50+640*v/span;
  const loads=result.normalized.loads.slice(0,8).map((l,i)=>{
    const a=l.type==='point'?l.position_m:l.start_m,b=l.type==='point'?l.position_m:l.end_m;
    const positions=l.type==='point'?[a]:[a,(2*a+b)/3,(a+2*b)/3,b];
    return `<g><text x="${x(a)}" y="${20+(i%2)*17}" fill="currentColor" font-size="12">${esc(l.name)} · ${num(l.type==='point'?l.force_n/1000:l.q_n_m/1000,3)} ${l.type==='point'?'kN':'kN/m'}</text>${positions.map(p=>`<path d="M${x(p)} 55 V95 m-4 -7 l4 7 l4 -7" stroke="currentColor" fill="none"/>`).join('')}${l.type==='uniform'?`<path d="M${x(a)} 55 H${x(b)}" stroke="currentColor"/>`:''}</g>`;
  }).join('');
  return `<figure><figcaption>${support==='simply_supported'?'简支梁 · 左铰右滚支':'悬臂梁 · 左端固定'}；荷载向下为正，自重不自动加入。</figcaption><svg viewBox="0 0 720 145" role="img" aria-label="支承与荷载位置示意" style="display:block;width:100%;height:auto;max-height:220px"><path d="M50 100 H690" stroke="currentColor" stroke-width="5"/>${support==='simply_supported'?'<path d="M50 102 l-10 20 h20 Z M690 102 l-10 20 h20 Z" fill="none" stroke="currentColor"/><circle cx="685" cy="126" r="3" fill="none" stroke="currentColor"/><circle cx="695" cy="126" r="3" fill="none" stroke="currentColor"/>':'<path d="M50 70 V130 M40 80 l10 -10 M40 95 l10 -10 M40 110 l10 -10 M40 125 l10 -10" stroke="currentColor"/>'}${loads}</svg>${result.normalized.loads.length>8?'<p>图示只显示前8项，计算包含下列全部荷载。</p>':''}</figure>`;
}

export async function engineeringWorkspace(state,host,action,resumedInput=null){
  const base='/projects/'+state.project.project_id;
  host.innerHTML=`<div class="view-heading"><div><h1>梁分析辅助</h1><p>输入明确的支承、截面、材料和荷载，查看支反力与变形过程。结果不包含结构安全或规范合格判断。</p></div></div><section id="ifc-beam-handoff"></section><form id="beam-form"><h2>几何与材料</h2><div id="beam-copied-profile"></div><div class="form-grid">${input('name','分析名称','required')}${select('support','理想化支承',{simply_supported:'简支梁（左铰右滚支）',cantilever:'悬臂梁（左端固定）'})}${input('span','跨度',numeric)}${select('span_unit','跨度单位',lengths)}${input('width','矩形截面宽度 b',numeric)}${input('depth','矩形截面高度 h（弯曲方向）',numeric)}${select('section_unit','截面尺寸单位',lengths)}${input('elastic_modulus','弹性模量 E',numeric)}${select('modulus_unit','模量单位',{Pa:'Pa',MPa:'MPa',GPa:'GPa'})}</div><p>手工输入支持矩形；IFC可交付明确对称等截面。计算仍限定恒定EI和向下荷载。未知数值留空；不要把缺失值填为零。</p><div class="form-grid">${input('geometry_source','几何参数来源','required minlength="5"')}${input('material_source','材料模量来源','required minlength="5"')}${input('support_basis','支承理想化依据','required minlength="5"')}</div><label>模型假设和适用依据<textarea name="analysis_basis" required minlength="10" placeholder="说明等截面、线弹性、小变形假设；实际材料强度、屈曲、荷载组合等需另行验算。"></textarea></label>
    <details><summary>绑定项目来源证据（可选）</summary>${state.evidence.map(e=>`<label class="check-option"><input type="checkbox" name="evidence_ids" value="${esc(e.evidence_id)}">${esc(e.name)} · v${e.revision}</label>`).join('')||'<p>尚无登记证据，本次输入只能按用户声明保留。</p>'}</details><h2>荷载清单</h2><div id="beam-loads"></div><div class="actions"><button type="button" id="beam-point">添加集中力</button><button type="button" id="beam-uniform">添加均布荷载</button><button type="submit" class="primary">计算并保存新记录</button></div></form><div id="beam-result" aria-live="polite"></div><h2>历史记录</h2><div id="beam-history"></div>`;
  const form=host.querySelector('#beam-form'),rows=host.querySelector('#beam-loads');
  let manualProfile=null;
  const ifc=bindIfcBeamProfile(host.querySelector('#ifc-beam-handoff'),base,action,(record,locked)=>{
    manualProfile=null;host.querySelector('#beam-copied-profile').innerHTML='';
    for(const k of ['width','depth','section_unit'])form.elements[k].disabled=locked||Boolean(manualProfile);
    if(locked){manualProfile=null;form.elements.width.value='';form.elements.depth.value='';if(!record||record.status!=='extracted')host.querySelector('#beam-result').textContent='IFC来源未通过当前核验，当前结果已撤下。';}
  });

  function add(type,load){
    const row=document.createElement('fieldset');row.dataset.type=type;
    row.innerHTML=`<legend>${type==='point'?'集中力':'分段均布荷载'}</legend><div class="form-grid">${input('load_name','荷载名称','required')}${input('magnitude',type==='point'?'集中力大小':'均布强度',numeric)}${select('unit','荷载单位',type==='point'?{N:'N',kN:'kN'}:{'N/m':'N/m','kN/m':'kN/m','N/mm':'N/mm'})}${type==='point'?input('position','作用位置（距左端）',numeric):input('start','起点（距左端）',numeric)+input('end','终点（距左端）',numeric)}${select('position_unit','位置单位',lengths)}</div>${input('source','荷载来源与组合口径','required minlength="5"')}<button type="button">移除此项</button>`;
    row.querySelector('button').onclick=()=>row.remove();rows.append(row);
    if(load)for(const [k,v] of Object.entries(load)){const el=row.querySelector(`[name="${k==='name'?'load_name':k}"]`);if(el)el.value=v??'';}
  }
  host.querySelector('#beam-point').onclick=()=>add('point');host.querySelector('#beam-uniform').onclick=()=>add('uniform');
  function draft(){
    const values=Object.fromEntries(new FormData(form));const numericFields=['span','width','depth','elastic_modulus'];
    const keys=['name','support',...numericFields,'span_unit','section_unit','modulus_unit','geometry_source','material_source','support_basis','analysis_basis'];
    const b=Object.fromEntries(keys.map(k=>[k,numericFields.includes(k)?((values[k]??'')===''?null:Number(values[k])):values[k]]));
    b.evidence_ids=[...form.querySelectorAll('[name=evidence_ids]:checked')].map(x=>x.value);
    b.loads=[...rows.children].map(row=>{const type=row.dataset.type,keys=['magnitude','unit','position_unit','source',...(type==='point'?['position']:['start','end'])];return {type,name:row.querySelector('[name=load_name]').value,...Object.fromEntries(keys.map(k=>{const v=row.querySelector('[name="'+k+'"]').value;return [k,['magnitude','position','start','end'].includes(k)?(v===''?null:Number(v)):v];}))};});b.section_unit=b.section_unit||'m';if(manualProfile)b.section_profile=structuredClone(manualProfile);const selection=ifc.capture();if(selection)b._ifc_selection=selection;return b;
  }
  host.captureDraft=draft;
  async function fill(input,snapshot=null){
    ifc.clear();manualProfile=input.section_profile||null;
    for(const [k,v] of Object.entries(input)){if(['loads','evidence_ids'].includes(k)||!form.elements[k])continue;form.elements[k].value=v??'';}
    form.querySelectorAll('[name=evidence_ids]').forEach(el=>el.checked=input.evidence_ids.includes(el.value));
    rows.innerHTML='';input.loads.forEach(l=>add(l.type,l));
    for(const k of ['width','depth','section_unit'])form.elements[k].disabled=Boolean(manualProfile);
    if(snapshot||input._ifc_selection)await ifc.restore(snapshot||input._ifc_selection);
    else if(manualProfile)host.querySelector('#beam-copied-profile').innerHTML='<p>复制的显式截面，按原声明保留；未声称完成IFC来源复核。可切回手工截面重新输入。</p><pre>'+esc(JSON.stringify(manualProfile,null,2))+'</pre>';
  }
  if(resumedInput){
    await fill(resumedInput);
    const message=document.createElement('p');message.className='form-note';message.setAttribute('role','status');
    message.textContent='已恢复同一账号的临时输入。尚未重新提交计算，请检查后再保存。';form.prepend(message);
  }
  function render(r){
    if(!host.isConnected)return;const result=r.result,m=result?.metrics;
    host.querySelector('#beam-result').innerHTML=`<h2>${esc(r.input.name)} · ${statuses[r.status]}</h2><p><strong>结构安全与规范符合性：未评估。</strong> ${r.status==='outside_model_screen'?'以下数值仅供排查输入及模型假设，不能作为设计结果使用。':''}</p>${m?`${result.model_screening.length?'<ul>'+result.model_screening.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':''}<div class="form-grid"><p>最大挠度<br><strong>${num(m.max_deflection_m*1000,6)} mm</strong> · x=${num(m.max_deflection_at_m,6)} m</p><p>最大绝对弯矩<br><strong>${num(m.max_abs_moment_nm/1000,6)} kN·m</strong></p><p>最大绝对剪力<br><strong>${num(m.max_abs_shear_n/1000,6)} kN</strong></p><p>线弹性最大弯曲应力<br><strong>${num(m.max_elastic_bending_stress_pa/1e6,6)} MPa</strong>（不是强度验算）</p></div><p>左支反力 ${num(m.left_reaction_n/1000,6)} kN；右支反力 ${num(m.right_reaction_n/1000,6)} kN；左端支承反力矩 ${num(m.left_reaction_moment_nm/1000,6)} kN·m。</p>${loadSketch(result,r.input.support)}${curve(result,'deflection_down_m','向下挠度','mm',1000)}<details><summary>查看剪力、弯矩与计算过程</summary>${curve(result,'shear','剪力','kN',.001)}${curve(result,'moment_nm','弯矩','kN·m',.001)}<p>I=${num(m.inertia_m4,12)} m⁴；EI=${num(m.ei_nm2,4)} N·m²</p><pre>${esc(JSON.stringify({formulas:result.formulas,equilibrium_residual:result.equilibrium_residual,normalized:result.normalized},null,2))}</pre></details>`:`<p>${result?'缺失参数：'+result.missing.map(esc).join('、'):'来源或项目声明发生变化，请复核后创建新记录。'}</p>`}${result?'<ul>'+result.limitations.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':''}<p><a href="/api${base}/beam-analyses/${r.engineering_id}" target="_blank" rel="noopener">完整计算JSON</a> · <a href="/api${base}/beam-analyses/${r.engineering_id}/report.html" target="_blank" rel="noopener">打印计算报告</a></p>`;
  }
  async function history(){
    const records=await request(base+'/beam-analyses');if(!host.isConnected)return;
    host.querySelector('#beam-history').innerHTML=records.map(r=>`<p>${esc(r.input.name)} · ${statuses[r.status]} <button data-view-beam="${r.engineering_id}">查看</button><button data-copy-beam="${r.engineering_id}">复制输入</button></p>`).join('')||'<p>尚无计算记录。</p>';
    host.querySelectorAll('[data-view-beam]').forEach(btn=>btn.onclick=()=>action(async()=>{render(await request(base+'/beam-analyses/'+btn.dataset.viewBeam));host.querySelector('#beam-result').scrollIntoView({block:'start'});}));
    host.querySelectorAll('[data-copy-beam]').forEach(btn=>btn.onclick=()=>action(async()=>{const r=await request(base+'/beam-analyses/'+btn.dataset.copyBeam);if(!host.isConnected)return;await fill(r.input,r.ifc_profile_snapshot);form.elements.name.value+=' · 副本';form.scrollIntoView({block:'start'});}));
  }
  form.onsubmit=e=>{e.preventDefault();action(async()=>{const body=draft();delete body._ifc_selection;const source=await ifc.review();let result;if(source){const {profile_id,...review}=source;body.width=null;body.depth=null;delete body.section_profile;result=await post(base+'/ifc-beam-profiles/'+profile_id+'/analyses',{...review,analysis:body});}else{result=await post(base+'/beam-analyses',body);}render(result);await history();host.querySelector('#beam-result').scrollIntoView({block:'start'});},e.submitter);};
  await history();
}
