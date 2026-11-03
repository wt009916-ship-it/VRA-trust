import { request, post, escape as esc, number as num } from './api.js';

export function engineeringInputs(host, { base, model, action, markDirty, notice }) {
  let equipment=structuredClone(model?.equipment||[]), exclusions={...(model?.scope_exclusions||{})};
  let coverage=model?.sources?.flatMap(s=>s.reconstruction_coverage?.storeys||[])||[];
  const panel=document.createElement('details');panel.className='model-card';
  panel.innerHTML='<summary>源窗、全楼范围与设备清单</summary><label>开窗几何<select data-engineering="window_geometry"><option value="ratio">显式窗墙比情景</option><option value="source">使用IFC源窗/窗洞几何（逐项核对）</option></select></label><label>源窗缺少内外分类时<select data-engineering="source_window_exterior_policy"><option value="reject">阻止计算，等待分类</option><option value="outdoor_scenario">假设：源窗所在空间墙面与室外相接</option></select></label><label>墙板重建的外包络<select data-engineering="reconstructed_exterior_policy"><option value="reject">阻止计算，等待外立面依据</option><option value="outline_scenario">假设：楼板外缘、最低底板和最高屋面为外包络</option></select></label><p class="subtle">窗洞不等于净玻璃；窗U/SHGC仍需有依据。外窗墙及外包络假设只能用于 assumed_scenario。楼层显示筛选不改变计算范围。</p><div data-coverage></div><hr><h3>逐空间设备 · 独立PTHP</h3><p>使用绝对额定制冷/制热功率W、送风m³/s及明确来源，按空间ID一一匹配。不会把冷水机组或VRF替换成PTHP。缺厂家曲线时须显式选择原生参考曲线。</p><a data-equipment-template download>下载空白设备CSV模板</a><label>导入有来源的UTF-8 CSV<input data-equipment-file type="file" accept=".csv"></label><button type="button" data-import-equipment>解析清单，待复核</button><button type="button" data-clear-equipment>移除此草稿设备清单</button><div data-equipment-result></div>';
  host.querySelector('#adjacency-gap').closest('label').after(panel);
  const mass=document.createElement('fieldset');mass.innerHTML='<legend>内部柱体热模型简化</legend><label>计算表示<select data-engineering="column_mass_policy"><option value="detailed">保留逐面柱体（可能计算较慢）</option><option value="lumped_scenario">明确情景：来源确认的内部柱体转为等效热容</option></select></label><p class="subtle">仅处理重建时确认来自IfcColumn的独立内孔，不处理竖井。保留原3D、净面积和空气体积；柱—板导热及辐射形态属于近似，须填写均质材料依据。</p><label>材料名称 · 启用时必填<input data-column="name"></label><div class="form-grid">'+[['conductivity_w_mk','导热 W/(m·K)'],['density_kg_m3','密度 kg/m³'],['specific_heat_j_kgk','比热 J/(kg·K)']].map(([key,label])=>`<label>${label}<input data-column="${key}" type="number" step="any"></label>`).join('')+'</div><label>材料及简化依据 · 启用时至少10字符<textarea data-column="source_note" minlength="10" maxlength="2000"></textarea></label>';panel.querySelector('[data-coverage]').before(mass);
  mass.querySelectorAll('[data-column]').forEach(el=>{el.value=model?.thermal?.column_mass_material?.[el.dataset.column]??'';el.oninput=markDirty;});
  panel.querySelector('[data-equipment-template]').href='/api'+base+'/model/equipment-template.csv';
  const numerical=document.createElement('fieldset');
  numerical.innerHTML='<legend>复杂边界与开窗情景</legend><label>几何归并失败时<select data-normalization-policy><option value="strict">严格拒绝，等待修订</option><option value="bounded_retry">在上限内逐步收紧，保留拒绝与实际公差记录</option></select></label><label>窗墙比如何作用于细碎热面<select data-ratio-policy><option value="per_fragment">逐个热面按比例开窗</option><option value="coplanar_budget">明确情景：同空间同平面外墙保留总窗面积，在可表达面内分配</option></select></label><p class="subtle">有界重试不删除空间；窗面积预算不改变源窗。选择源窗时不执行比例再分配。排除细碎面及总窗面积守恒明细保存在独立校验中。</p>';
  panel.prepend(numerical);
  numerical.querySelector('[data-normalization-policy]').value=model?.thermal?.geometry_tolerance_policy||'strict';
  numerical.querySelector('[data-ratio-policy]').value=model?.thermal?.ratio_glazing_policy||'per_fragment';
  numerical.querySelectorAll('select').forEach(el=>el.onchange=markDirty);
  panel.querySelectorAll('[data-engineering]').forEach(el=>{el.value=model?.thermal?.[el.dataset.engineering]||(el.dataset.engineering==='window_geometry'?'ratio':el.dataset.engineering==='column_mass_policy'?'detailed':'reject');el.onchange=()=>{syncMassFields();markDirty();};});
  function syncMassFields(){const enabled=panel.querySelector('[data-engineering="column_mass_policy"]').value==='lumped_scenario';mass.querySelectorAll('[data-column]').forEach(el=>{el.disabled=!enabled;el.required=enabled;});}
  syncMassFields();
  function paintCoverage(){
    const unique=[...new Map(coverage.map(c=>[c.storey,c])).values()];
    const issues=coverage.filter(c=>c.status!=='candidate'||c.excluded_subminimum_area_m2>.01);
    const ids=new Set(issues.map(c=>c.storey));
    panel.querySelector('[data-coverage]').innerHTML=coverage.length?`<h3>全楼重建范围</h3><p>${unique.length}个源楼层 · ${unique.reduce((s,c)=>s+(c.rooms||0),0)}个候选；${ids.size}个楼层含未恢复/小型区域。处置说明会保留为排除范围，不会把缺失几何变成已恢复。</p>${[...ids].map(id=>{const c=coverage.find(c=>c.storey===id);return `<label>${esc(c.name||id)} · ${esc(issues.filter(c=>c.storey===id).map(c=>c.status).join(' / '))}<textarea data-scope-id="${esc(id)}" minlength="10" maxlength="1000" placeholder="依据原图说明非空调平台/未恢复区域如何处理，至少10字符">${esc(exclusions[id]||'')}</textarea></label>`;}).join('')}<details><summary>逐层来源与覆盖</summary><div class="table-wrap"><table><thead><tr><th>源楼层</th><th>候选</th><th>楼板/空域面积m²</th><th>状态</th></tr></thead><tbody>${unique.map(c=>`<tr><td>${esc((c.building_name?c.building_name+' / ':'')+(c.name||c.storey))}</td><td>${c.rooms||0}</td><td>${num(c.source_floor_area_m2)} / ${num(c.air_area_m2)}</td><td>${esc(c.status)}</td></tr>`).join('')}</tbody></table></div></details>`:'<p class="subtle">导入墙板重建后，在此核对逐层覆盖与排除范围。</p>';
    panel.querySelectorAll('[data-scope-id]').forEach(el=>{el.oninput=()=>{if(el.value.trim())exclusions[el.dataset.scopeId]=el.value;else delete exclusions[el.dataset.scopeId];markDirty();};});
  }
  function paintEquipment(){
    panel.querySelector('[data-equipment-result]').innerHTML=equipment.length?`<p>${equipment.length}条待核对设备；修改参数请修订源CSV并重新导入，原件和旧模型版本保留。</p><div class="table-wrap"><table><thead><tr><th>空间</th><th>厂家/型号</th><th>制冷/制热 W</th><th>送风m³/s</th><th>曲线/来源</th></tr></thead><tbody>${equipment.map(e=>`<tr><td>${esc(e.zone_id)}</td><td>${esc(e.manufacturer)} / ${esc(e.model)}</td><td>${num(e.cooling_capacity_w)} / ${num(e.heating_capacity_w)}</td><td>${num(e.airflow_m3_s,3)}</td><td>${e.curve_basis==='source_curves'?'10项源曲线':'原生参考曲线（非厂家变工况）'}<small>${esc(e.source_locator)} · ${esc(e.source_file_hash.slice(0,10))}</small></td></tr>`).join('')}</tbody></table></div>`:'<p class="subtle">未配置逐空间设备；理想负荷与统一按面积热泵保留各自口径。</p>';
  }
  panel.querySelector('[data-import-equipment]').onclick=e=>action(async()=>{
    const file=panel.querySelector('[data-equipment-file]').files[0];if(!file)throw Error('先选择设备CSV');
    const data=new FormData();data.append('file',file);const saved=await request(base+'/files',{method:'POST',body:data});
    const candidate=await post(base+'/model/equipment-import',{file_id:saved.file_id});equipment=candidate.equipment;
    host.querySelector('#pump-enabled').checked=false;paintEquipment();markDirty();notice('设备清单已加入草稿；请核对空间ID、运行档案和来源后保存。');
  },e.currentTarget);
  panel.querySelector('[data-clear-equipment]').onclick=()=>{equipment=[];paintEquipment();markDirty();};
  paintCoverage();paintEquipment();
  return {
    thermal(){if(panel.querySelector('[data-engineering="column_mass_policy"]').value==='lumped_scenario'){const fields=[...mass.querySelectorAll('[data-column]')];if(fields.some(el=>!el.value.trim()||(el.type==='number'&&(!Number.isFinite(Number(el.value))||Number(el.value)<=0)))||mass.querySelector('[data-column="source_note"]').value.trim().length<10)throw Error('柱体等效热容情景须填齐材料名称、正值导热/密度/比热，以及至少10字符的材料和简化依据。');}const values=Object.fromEntries([...panel.querySelectorAll('[data-engineering]')].map(el=>[el.dataset.engineering,el.value]));values.column_mass_material=values.column_mass_policy==='lumped_scenario'?Object.fromEntries([...mass.querySelectorAll('[data-column]')].map(el=>[el.dataset.column,el.type==='number'?Number(el.value):el.value])):null;values.geometry_tolerance_policy=numerical.querySelector('[data-normalization-policy]').value;values.ratio_glazing_policy=values.window_geometry==='source'?'per_fragment':numerical.querySelector('[data-ratio-policy]').value;return values;},
    body(){return {equipment,scope_exclusions:exclusions};},
    imported(candidate){coverage=[...coverage,...(candidate.diagnostics?.storeys||[])];paintCoverage();},
  };
}
