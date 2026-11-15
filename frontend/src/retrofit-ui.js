import {request,post,escape as esc,number as num} from './api.js';
import {createScenarioSourceGuard} from './scenario-source.js';

const roughness=['VeryRough','Rough','MediumRough','MediumSmooth','Smooth','VerySmooth'];
const labels=['很粗糙','粗糙','中等粗糙','中等光滑','光滑','很光滑'];
const ninput=(name,label,min,max)=>`<label>${label}<input name="${name}" type="number" min="${min}" max="${max}" step="any" required></label>`;

export function propertyEditors(record){
 if(record?.status!=='calculated'||!record.result?.layers?.length)return '<p>请选择当前、完整的热工记录。</p>';
 if(record.result.layers.length>10)return '<p>当前改模最多支持10层；此记录不能生成模型。</p>';
 return record.result.layers.map((l,i)=>`<fieldset data-material-properties><legend>热工记录第${i+1}层 · ${esc(l.name)}</legend><p>厚度 ${num(l.thickness_m,6)} m · 有效导热系数 ${num(l.effective_conductivity_w_mk,6)} W/(m·K)</p><div class="form-grid">${ninput('density_kg_m3','密度 kg/m³',.000001,30000)}${ninput('specific_heat_j_kg_k','比热 J/(kg·K)',100,100000)}<label>表面粗糙度<select name="roughness" required><option value="">明确选择</option>${roughness.map((v,j)=>`<option value="${v}">${labels[j]} · ${v}</option>`).join('')}</select></label>${ninput('thermal_absorptance','长波热吸收率',.000001,.99999)}${ninput('solar_absorptance','太阳吸收率',0,1)}${ninput('visible_absorptance','可见光吸收率',0,1)}</div><label>上述材性来源、版本及适用条件<input name="property_source" required minlength="10" maxlength="2000"></label></fieldset>`).join('');
}

export function previewMarkup(preview){
 if(!preview?.changes)return '';
 return `<h3>检查变更后再生成</h3><p>仅修改 ${num(preview.changes.changed_reference_count,0)} 个表面的构造引用，新增 ${num(preview.changes.added_object_count,0)} 个材料／构造对象。原文件保留；尚未运行能耗仿真。</p><div class="table-scroll"><table><tr><th>表面</th><th>原构造</th><th>派生构造</th></tr>${preview.changes.changes.map(c=>`<tr><td>${esc(c.surface_name)}</td><td>${esc(c.old_construction)}</td><td>${esc(c.new_construction)}</td></tr>`).join('')}</table></div>${preview.changes.assignments.map(a=>`<p>写入层序（外→内）：${a.layers_outside_to_inside.map(l=>esc(l.thermal_layer_name)).join(' → ')}；不写入 Rsi/Rse 材料层。</p>`).join('')}<ul>${preview.limitations.map(l=>`<li>${esc(l)}</li>`).join('')}</ul><label class="check-option"><input type="checkbox" data-acknowledge>我已复核选定表面、完整替换的构造层序及材性；这是用户声明情景，仍需复核并运行仿真。</label><button type="button" data-generate disabled>生成派生模型</button>`;
}

export function retrofitResultMarkup(record,base){
 if(record?.status!=='generated'||!record.changes)return '<p>来源失效、被拒绝或尚未核验；模型变更结果与下载暂不可用。</p>';
 return `<h3>${esc(record.input.name)}</h3><p>用户声明改造情景 · 复核状态 ${esc(record.evidence_review?.review_state)} · ${num(record.changes.changed_reference_count,0)} 个表面</p><p>生成文件不代表仿真成功，也不证明工程适用性。</p><a href="/api${esc(base)}/retrofits/${esc(record.retrofit_id)}/model.idf" target="_blank" rel="noopener">下载派生 IDF</a> · <a href="/api${esc(base)}/retrofits/${esc(record.retrofit_id)}/report.html" target="_blank" rel="noopener">变更、来源与材性报告</a>`;
}

export function matchingRuns(runs,record,scheme){
 const hash=scheme==='baseline'?record.dependencies.source_file.hash:record.derived_file.hash;
 return runs.filter(r=>r.project_id===record.project_id&&r.scheme_id===scheme&&r.status==='succeeded'&&r.provenance?.model_hash===hash);
}

export function annualComparisonMarkup(response){
 const rows=response?.comparison?.results;
 if(!rows?.length||rows.some(r=>r.status!=='succeeded'))return '<p>当前比较不可用。</p>';
 return `<p>同天气、引擎和面积条件下的原生年度能耗比较；U值降幅不替代全年节能率。</p><table><tr><th>方案</th><th>年度能耗 kWh</th><th>相对基准节能率</th></tr>${rows.map(r=>`<tr><td>${esc(r.scheme_id)}</td><td>${num(r.metrics?.annual_energy_kwh,2)}</td><td>${num(r.saving_rate_pct,3)}%</td></tr>`).join('')}</table><p>${esc(response.comparison.note)}</p>`;
}

export async function retrofitWorkspace(state,host){
 const base='/projects/'+state.project.project_id;
 host.innerHTML='<h2>材料方案接入能耗模型</h2><p>选择完整热工构造和明确的室外围护表面，生成新的 IDF，再比较真实年度能耗。窗、地接触及特殊构造暂不支持。</p><button type="button" data-load-bridge>新建材料改造模型</button><div data-bridge-editor></div><h3>派生模型记录</h3><button type="button" data-refresh-history>刷新记录</button><div data-bridge-history></div><div data-bridge-detail></div><p data-bridge-message role="status"></p>';
 const q=s=>host.querySelector(s),editor=q('[data-bridge-editor]'),detail=q('[data-bridge-detail]'),message=q('[data-bridge-message]');
 let openTicket=0,guard=null,timer=null,selectedId=null,busy=false,detailTicket=0,removeVisibility=()=>{};
 const alive=()=>host.isConnected,visible=()=>alive()&&!document.hidden;
 function closeDetail(){removeVisibility();removeVisibility=()=>{};guard?.stop();guard=null;clearInterval(timer);timer=null;selectedId=null;detailTicket++;detail.replaceChildren();}
 async function history(){
  const records=await request(base+'/retrofits');if(!alive())return;
  q('[data-bridge-history]').innerHTML=records.map(r=>`<p><button type="button" data-retrofit="${esc(r.retrofit_id)}">${esc(r.input.name)} · ${esc(r.status)}</button></p>`).join('')||'<p>尚无派生模型。</p>';
  q('[data-bridge-history]').querySelectorAll('[data-retrofit]').forEach(b=>b.onclick=()=>safe(()=>openRecord(b.dataset.retrofit)));
 }
 async function safe(fn){try{await fn();}catch(e){if(alive())message.textContent=e.message;}}
 async function openRecord(id){
  closeDetail();selectedId=id;const ticket=detailTicket;
  const live=()=>alive()&&selectedId===id&&ticket===detailTicket;
  const route=base+'/retrofits/'+id;
  detail.innerHTML='<p data-current-state role="status">核验中…</p><button type="button" data-refresh-detail>重新核验</button><div data-current-result></div><div data-run-actions></div><div data-annual-result></div>';
  const dq=s=>detail.querySelector(s);let current=null,lastComparison=null,draft={};
  guard=createScenarioSourceGuard({timeoutMs:12000,read:async signal=>{
   const [record,runs]=await Promise.all([request(route,{signal}),request(base+'/runs',{signal})]);
   let compared=null,comparisonError=null;
   if(lastComparison&&record.status==='generated'){
    try{compared=await request(route+'/comparison',{method:'POST',body:JSON.stringify({run_ids:lastComparison}),signal});}
    catch(e){if(e.status!==409)throw e;lastComparison=null;comparisonError=e.message;}
   }
   return {record,runs,compared,comparisonError};
  },validate:r=>r.record.status==='generated',onState:status=>{
   if(!live())return;
   dq('[data-current-state]').textContent={checking:'正在核验来源与运行…',current:'来源当前有效；运行结果仍按各自状态核验',stale:'来源已失效或被拒绝',timeout:'核验超时；暂不显示旧结果',unavailable:'无法核验；暂不显示旧结果',hidden:'页面隐藏；返回时重新核验'}[status]||status;
   if(status!=='current'){
    const inputs=dq('[data-run-actions]').querySelectorAll('input,select');
    if(inputs.length)draft=Object.fromEntries([...inputs].map(el=>[el.name,el.value]));
    current=null;dq('[data-current-result]').replaceChildren();dq('[data-run-actions]').replaceChildren();dq('[data-annual-result]').replaceChildren();}
  }});
  const ownGuard=guard;
  async function refresh(){
   if(!live()||!visible()||busy)return;
   const data=await ownGuard.refresh();if(!data||!live()||!ownGuard.current())return;
   current=data.record;dq('[data-current-result]').innerHTML=retrofitResultMarkup(current,base);
   const review=current.evidence_review;
   if(review.review_state!=='confirmed'){
    dq('[data-run-actions]').innerHTML='<h4>复核派生模型</h4><form data-review-model><label>复核人<input name="person" required maxlength="100"></label><label>复核依据（表面、层序、材性及情景范围）<input name="basis" required minlength="5" maxlength="2000"></label><button type="submit">记录人工复核</button></form>';
    dq('[data-review-model]').onsubmit=async e=>{e.preventDefault();if(!current||!ownGuard.current()||busy)return;const f=new FormData(e.currentTarget);await operate(()=>request(base+'/evidence/'+review.evidence_id,{method:'PATCH',body:JSON.stringify({expected_revision:review.revision,review_state:'confirmed',responsible_person:f.get('person'),review_note:f.get('basis')})}));};
   }else{
    const a=matchingRuns(data.runs,current,'baseline'),b=matchingRuns(data.runs,current,current.input.scheme_id);
    const options=rs=>'<option value="">选择有效运行</option>'+rs.map(r=>`<option value="${esc(r.run_id)}">${esc(r.run_id)} · ${num(r.metrics?.annual_energy_kwh)} kWh</option>`).join('');
    const active=data.runs.filter(r=>['queued','running'].includes(r.status));
    dq('[data-run-actions]').innerHTML=`<p>新运行使用项目当前已复核的天气和匹配引擎。未设置碳因子，本流程只比较能耗。</p><button type="button" data-run-scheme="baseline" ${active.some(r=>r.scheme_id==='baseline')?'disabled':''}>运行基准模型</button> <button type="button" data-run-scheme="${esc(current.input.scheme_id)}" ${active.some(r=>r.scheme_id===current.input.scheme_id)?'disabled':''}>运行派生模型</button><p>${active.map(r=>esc(r.scheme_id)+' · '+esc(r.status)).join('；')}</p><form data-compare-runs><div class="form-grid"><label>基准运行<select name="baseline" required>${options(a)}</select></label><label>派生运行<select name="derived" required>${options(b)}</select></label></div><button type="submit" ${!a.length||!b.length?'disabled':''}>核验并比较年度能耗</button></form>`;
    dq('[data-run-actions]').querySelectorAll('[data-run-scheme]').forEach(b=>b.onclick=()=>operate(()=>post('/runs',{project_id:state.project.project_id,scheme_id:b.dataset.runScheme,factor_profile_id:'none'})));
    dq('[data-compare-runs]').onsubmit=async e=>{e.preventDefault();if(!current||!ownGuard.current()||busy)return;const f=new FormData(e.currentTarget);lastComparison=[f.get('baseline'),f.get('derived')];await refresh();};
   }
   dq('[data-run-actions]').querySelectorAll('input,select').forEach(el=>{if(Object.hasOwn(draft,el.name))el.value=draft[el.name];});
   if(data.compared)dq('[data-annual-result]').innerHTML=annualComparisonMarkup(data.compared);
   else if(data.comparisonError)dq('[data-annual-result]').textContent='旧运行已不可比较，请重新选择有效运行：'+data.comparisonError;
  }
  async function operate(fn){
   if(!live()||!visible()||!ownGuard.current()||busy)return;
   busy=true;ownGuard.invalidate('checking');
   try{await fn();if(live())message.textContent='操作已提交；正在核验当前状态。';}
   catch(e){if(live())message.textContent=e.message;}
   finally{busy=false;if(live())await refresh();}
  }
  dq('[data-refresh-detail]').onclick=()=>safe(refresh);
  timer=setInterval(()=>{if(!alive()){closeDetail();document.removeEventListener('visibilitychange',visibility);}else if(visible()&&!detail.querySelector('input:focus,select:focus'))void refresh();},5000);
  function visibility(){if(!live()){document.removeEventListener('visibilitychange',visibility);return;}if(document.hidden)ownGuard.invalidate('hidden');else void refresh();}
  document.addEventListener('visibilitychange',visibility);removeVisibility=()=>document.removeEventListener('visibilitychange',visibility);
  await refresh();
 }
 q('[data-refresh-history]').onclick=()=>safe(history);
 q('[data-load-bridge]').onclick=()=>safe(async()=>{
  const ticket=++openTicket;editor.textContent='正在读取基准模型与热工记录…';
  const [sources,records]=await Promise.all([request(base+'/retrofit-models'),request(base+'/thermal')]);
  if(!alive()||ticket!==openTicket)return;
  const thermals=records.filter(r=>r.status==='calculated'&&r.result?.layers?.length<=10);
  editor.innerHTML=`<form data-model-plan><h3>1 · 选择来源与表面</h3><div class="form-grid"><label>已确认基准 IDF<select name="source_evidence_id" required><option value="">明确选择</option>${sources.map(s=>`<option value="${esc(s.evidence_id)}">${esc(s.name)}</option>`).join('')}</select></label><label>完整替换构造的热工记录<select name="thermal_id" required><option value="">明确选择</option>${thermals.map(t=>`<option value="${esc(t.thermal_id)}">${esc(t.input.name)}</option>`).join('')}</select></label></div><p>原构造的全部材料层将被所选热工构造替换；仅添加保温时，热工记录必须同时包含保留的原有各层。</p><div data-surface-list></div><h3>2 · 声明层序与缺失材性</h3><label>热工记录中的层序<select name="layer_order" required><option value="">明确选择</option><option value="outside_to_inside">记录顺序为外侧→内侧</option><option value="inside_to_outside">记录顺序为内侧→外侧</option></select></label><div data-layer-properties></div><div class="form-grid"><label>派生方案名称<input name="name" required maxlength="160"></label><label>目标方案槽<select name="scheme_id" required><option value="">明确选择</option><option>R1</option><option>R2</option></select></label><label>责任人<input name="responsible_person" required maxlength="100"></label></div><label>映射及功能适用性依据<input name="basis" required minlength="10" maxlength="2000"></label><p>目标槽已有有效模型时，须先在证据页明确拒绝被替代的模型；不会自动覆盖。</p><button type="submit">3 · 预览精确变更</button><div data-model-preview></div></form>`;
  const form=editor.querySelector('form'),fq=s=>form.querySelector(s);let selection=0,preview=null,planSnapshot=null,submitting=false,revision=0;
  const live=()=>alive()&&editor.contains(form)&&ticket===openTicket;
  function invalidate(){revision++;preview=null;planSnapshot=null;fq('[data-model-preview]').replaceChildren();}
  form.addEventListener('input',e=>{if(!e.target.closest('[data-model-preview]'))invalidate();});
  form.addEventListener('change',e=>{if(!e.target.closest('[data-model-preview]'))invalidate();});
  fq('[name=source_evidence_id]').onchange=async()=>{
   const turn=++selection;fq('[data-surface-list]').textContent='正在核验表面…';
   try{
    const eid=fq('[name=source_evidence_id]').value;
    if(!eid){fq('[data-surface-list]').replaceChildren();return;}
    const data=await request(base+'/retrofit-models/'+eid);
    if(!live()||turn!==selection)return;
    fq('[data-surface-list]').innerHTML=data.surfaces.map((s,i)=>`<label class="check-option"><input type="checkbox" name="surface" value="${esc(s.name)}" ${s.eligible?'':'disabled'}>${esc(s.name)} · ${esc(s.surface_type)} · ${esc(s.construction)}${s.eligible?'':' · 不支持：'+s.reasons.map(esc).join('、')}</label>`).join('')||'<p>没有可识别表面。</p>';
   }catch(e){if(live()&&turn===selection){fq('[data-surface-list]').textContent=e.message;invalidate();}}
  };
  fq('[name=thermal_id]').onchange=()=>{fq('[data-layer-properties]').innerHTML=propertyEditors(thermals.find(t=>t.thermal_id===fq('[name=thermal_id]').value));};
  form.onsubmit=async e=>{
   e.preventDefault();if(submitting||!live()||!form.reportValidity())return;
   invalidate();const turn=revision,f=new FormData(form);
   const chosen=thermals.find(t=>t.thermal_id===f.get('thermal_id'));
   const props=[...form.querySelectorAll('[data-material-properties]')].map(el=>Object.fromEntries([...el.querySelectorAll('input,select')].map(input=>[input.name,input.type==='number'?Number(input.value):input.value])));
   if(!f.getAll('surface').length||!chosen||props.length!==chosen.result.layers.length){message.textContent='请选择至少一个受支持表面，并填写每层材性。';return;}
   const plan={name:f.get('name'),source_evidence_id:f.get('source_evidence_id'),scheme_id:f.get('scheme_id'),responsible_person:f.get('responsible_person'),basis:f.get('basis'),assignments:[{thermal_id:f.get('thermal_id'),surface_names:f.getAll('surface'),layer_order:f.get('layer_order'),properties:props}]};
   submitting=true;e.submitter.disabled=true;
   try{
    const result=await post(base+'/retrofit-previews',plan);
    if(!live()||turn!==revision)return;
    preview=result;planSnapshot=plan;fq('[data-model-preview]').innerHTML=previewMarkup(preview);
    fq('[data-acknowledge]').onchange=e=>{fq('[data-generate]').disabled=!e.target.checked;};
    fq('[data-generate]').onclick=async()=>{
     if(submitting||!live()||!preview||!fq('[data-acknowledge]').checked)return;
     const body={...planSnapshot,expected_preview_hash:preview.preview_hash,acknowledge_scope:true};submitting=true;fq('[data-generate]').disabled=true;
     try{const saved=await post(base+'/retrofits',body);if(!live())return;invalidate();message.textContent='派生文件已保存，需人工复核后运行。';await history();await openRecord(saved.retrofit_id);}
     catch(err){if(live()){invalidate();message.textContent=err.message+'；请重新预览后再提交。';}}
     finally{submitting=false;}
    };
   }catch(err){if(live()){invalidate();message.textContent=err.message;}}
   finally{submitting=false;if(live())e.submitter.disabled=false;}
  };
 });
 await history();
}
