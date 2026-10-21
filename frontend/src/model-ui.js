import { importDiagnostics } from './assurance-ui.js';
import { request, post, escape as esc, number as num, uploadLimitMB } from './api.js';
import { projectTokens } from './developer-ui.js';

const thermalFields = [
  ['wall_u','外墙 U · W/(m²·K)'],['roof_u','屋面 U · W/(m²·K)'],['floor_u','底板 U · W/(m²·K)'],
  ['window_u','窗 U · W/(m²·K)'],['window_shgc','窗太阳得热系数'],['window_wall_ratio','外墙窗墙比'],
  ['heating_c','供暖设定点 °C'],['cooling_c','制冷设定点 °C'],['infiltration_ach','渗透换气次数 /h'],
  ['ground_temperature_c','全年固定土温 °C'],['lights_w_m2','照明 W/m²'],['equipment_w_m2','设备 W/m²'],['people_m2_person','人均面积 m²'],
  ['active_start','每日开始 · 时'],['active_end','每日结束 · 时'],['north_deg','北向角度 °'],
];
const teachingThermal = {wall_u:.8,roof_u:.5,floor_u:.6,window_u:2.5,window_shgc:.5,window_wall_ratio:.2,
  heating_c:20,cooling_c:26,infiltration_ach:.3,ground_temperature_c:18,lights_w_m2:6,equipment_w_m2:8,people_m2_person:12,
  active_start:8,active_end:18,north_deg:0,basis:'assumed_scenario',
  source_note:'教学假设参数，仅用于验证模型及情景计算，不代表本项目实测或设计参数。'};

export function polygonArea(points) {
  return Math.abs(points.reduce((sum,p,i)=>{const q=points[(i+1)%points.length];return sum+p[0]*q[1]-q[0]*p[1];},0))/2;
}

export function roomSegments(room) {
  return room.segments?.length ? room.segments : [room];
}

export function roomArea(room) {
  const segments=roomSegments(room), low=Math.min(...segments.map(s=>s.elevation_m));
  return segments.filter(s=>Math.abs(s.elevation_m-low)<1e-7).reduce((a,s)=>a+polygonArea(s.polygon),0);
}

export function duplicateRoom(room) {
  const r=structuredClone(room),dz=r.height_m;
  r.name+=' 上层';r.elevation_m+=dz;
  r.segments?.forEach(s=>{s.elevation_m+=dz;});
  r.boundary_hints?.forEach(h=>h.points.forEach(p=>{p[2]+=dz;}));
  r.source_locator+=`；人工复制并上移 ${dz} m，须重新复核`;
  return r;
}

export function mergeRooms(existing, candidates) {
  const rooms=structuredClone([...existing,...candidates]);
  rooms.forEach((r,i)=>{r.id='R'+(i+1);});
  return rooms;
}

export async function spatialWorkspace(state, host, action, notice, onChange=()=>{}) {
  const pid=state.project.project_id, base='/projects/'+pid;
  let model=await request(base+'/model'), imports=await request(base+'/imports');
  if(!host.isConnected)return;
  let rooms=structuredClone(model?.rooms||[]), pending=null, selected=0, dispose=()=>{}, dirty=false;
  const constructions=structuredClone(model?.thermal?.constructions||{});
  host.innerHTML=`<div class="view-heading"><div><span class="eyebrow">BUILDING WORKBENCH</span><h1>资料进入，空间成形。</h1><p>DXF · 矢量 PDF · IFC · 图片识别 → 几何复核 → 三维模型 → EnergyPlus</p></div><button id="model-api">项目 API / MCP</button></div>
  <div class="model-workbench"><div class="model-inputs">
  <details class="model-card" open><summary>01 / 导入与识别</summary><form id="model-import">
  <label>选择资料 · 最大 ${uploadLimitMB()} MB<input name="file" type="file" accept=".dxf,.dwg,.pdf,.ifc,.png,.jpg,.jpeg" required></label>
  <label>识别方式<select name="mode"><option value="geometry">本地几何解析 · DXF / PDF / IFC</option><option value="vision">视觉模型 · 扫描 PDF / 图片</option></select></label>
  <div class="form-grid"><label>长度换算系数<input name="scale_to_m" type="number" step="any" min=".0000001" placeholder="DXF 可自动读取单位"></label><label>页码<input name="page" type="number" value="1" min="1" max="500"></label><label>候选层高 m<input name="height_m" type="number" value="3" step=".1" min=".6" max="30"></label><label>候选标高 m<input name="elevation_m" type="number" value="0" step=".1"></label></div>
  <label>DXF 图层（可选）<input name="layer" placeholder="建议先选择房间边界图层"></label>
  <p class="subtle">换算系数 = 米 / 图纸单位；PDF 为米 / point，图片为米 / 原图像素。PDF 视觉识别按 72 dpi 渲染。DWG 请先导出 DXF。</p>
  <label class="check-option"><input name="send_to_provider" type="checkbox">允许把本次选中的图页发送给开发者设置中的视觉服务</label>
  <button class="primary">识别空间候选</button><p id="import-progress" role="status"></p></form>
  <div id="model-imports"></div></details>
  <section class="model-card"><h2>02 / 空间与尺寸</h2><div class="actions"><button id="add-room">＋ 矩形房间</button><button id="duplicate-floor">复制到上一层</button></div>
  <label>当前房间<select id="room-select"></select></label><div id="room-editor"></div></section>
  </div><div class="model-main">
  <section class="model-card model-preview"><div class="model-preview-top"><span id="model-summary"></span><label class="check-option"><input id="model-xray" type="checkbox">透视</label></div><div id="building-canvas" aria-label="建筑空间三维预览"></div><div id="model-plan" aria-label="二维空间轮廓"></div><p class="subtle">蓝色空间为当前编辑内容；三维预览用于检查空间关系，未保存的修改不会进入仿真。</p></section>
  <details class="model-card"><summary>03 / 热工与运行参数</summary><p>所有参数须注明来源。理想负荷模型计算供热/供冷需求，尚未表示真实设备耗电。</p><button id="teaching-thermal">填入教学假设供试运行</button><div class="form-grid" id="thermal-fields">${thermalFields.map(([k,l])=>`<label>${l}<input data-thermal="${k}" type="number" step="any" value="${esc(model?.thermal?.[k]??'')}"></label>`).join('')}</div><label>参数性质<select id="thermal-basis"><option value="assumed_scenario">明确假设的工程情景</option value="documented">有设计 / 检测文件依据</option></select></label><label>参数来源与适用条件<textarea id="thermal-source" minlength="10">${esc(model?.thermal?.source_note||'')}</textarea></label></details>
  <section class="model-card"><h2>04 / 复核、保存与计算</h2><label>模型名称<input id="model-name" value="${esc(model?.name||state.project.name)}"></label><label>比例、空间及来源复核说明<textarea id="model-review" minlength="5" placeholder="说明比例依据、核对的房间和仍存在的假设">${esc(model?.review_note||'')}</textarea></label>
  <div class="actions"><button id="save-model">保存草稿</button><button class="primary" id="review-model">确认空间并保存</button><button id="sync-model-area">同步项目面积</button></div>
  <p id="model-status" role="status"></p><div id="model-gate"></div>
  <div class="form-grid"><label>发布为方案<select id="model-scheme"><option value="baseline">基准 baseline</option><option value="R1">方案 R1</option><option value="R2">方案 R2</option></select></label><label>发布与参数复核依据<input id="publish-note" minlength="10" placeholder="确认空间、参数性质和理想负荷适用范围"></label></div>
  <div class="actions"><button id="publish-model">生成并登记 IDF</button><button id="run-model">提交全年仿真</button><a href="/api${base}/model/export.ifc" download>导出 IFC 空间模型</a><a href="/api${base}/model/export.idf" download>导出 IDF</a></div>
  <p class="subtle">发布会以新版本替代此方案的有效 IDF，旧资料和计算记录保留。还需在「资料」中登记并确认项目对应的全年 EPW。</p>
  <div id="model-runs"></div><details><summary>版本与来源</summary><pre id="model-history"></pre></details>
  </section></div></div>`;
  if(model?.thermal)host.querySelector('#thermal-basis').value=model.thermal.basis;
  const boundaryPolicy=document.createElement('label');
  boundaryPolicy.innerHTML='<span>IFC 未配对边界</span><select id="ifc-boundary-policy"><option value="reject">阻止发布，等待补全邻接</option><option value="adiabatic_scenario">假设情景：未配对内部/未知边界按绝热处理</option></select><small>绝热处理会改变冷热需求，只能用于明确标注的假设情景；不代表完整建筑性能。</small>';
  host.querySelector('#thermal-source').parentElement.after(boundaryPolicy);
  host.querySelector('#ifc-boundary-policy').value=model?.thermal?.ifc_unpaired_policy||'reject';
  const tolerance=document.createElement('label');
  tolerance.innerHTML=`几何归并公差 m<input id="geometry-tolerance" type="number" min="0" max=".05" step=".001" value="${esc(model?.thermal?.geometry_tolerance_m??0)}"><small>默认 0，不调整几何。仅假设情景可显式设置，用于处理引擎不接受的细碎面；发布记录保留实际位移和每个空间的面积、体积变化。</small>`;
  boundaryPolicy.after(tolerance);
  const setStatus=text=>{host.querySelector('#model-status').textContent=text;};
  const markDirty=()=>{dirty=true;setStatus('有未保存的编辑，请保存后再发布或计算。');};
  host.addEventListener('input',e=>{if(e.target.matches('[data-room],[data-point],[data-thermal],#thermal-source,#thermal-basis,#model-name,#model-review'))markDirty();});
  host.querySelector('#thermal-basis').onchange=markDirty;
  host.querySelector('#ifc-boundary-policy').onchange=markDirty;
  host.querySelector('#geometry-tolerance').oninput=markDirty;
  const assemblyPanel=document.createElement('details');
  assemblyPanel.className='model-card';assemblyPanel.innerHTML='<summary>围护结构分层材料 · 热容模型</summary><p>逐层填写由外到内的构造。有构造层时 U 值由材料导热热阻加表面热阻计算，覆盖上面的简化 U 输入。所有材料仍须在参数来源中注明检测或假设依据。</p><div id="construction-forms"></div>';
  host.querySelector('#thermal-fields').parentElement.after(assemblyPanel);
  const layerFields=[['thickness_m','厚度 m'],['conductivity_w_mk','导热 W/(m·K)'],['density_kg_m3','密度 kg/m³'],['specific_heat_j_kgk','比热 J/(kg·K)']];
  function paintConstructions(){
    host.querySelector('#construction-forms').innerHTML=[['wall','外墙'],['roof','屋面'],['floor','底板']].map(([key,title])=>`<fieldset><legend>${title} · 由外到内</legend>${(constructions[key]||[]).map((layer,i)=>`<div class="layer-row"><label>层 ${i+1} 名称<input data-layer="${key}" data-index="${i}" data-key="name" value="${esc(layer.name)}"></label><div class="form-grid">${layerFields.map(([k,l])=>`<label>${l}<input type="number" step="any" data-layer="${key}" data-index="${i}" data-key="${k}" value="${esc(layer[k])}"></label>`).join('')}</div><button data-delete-layer="${key}" data-index="${i}">移除此层</button></div>`).join('')}<button data-add-layer="${key}">＋ 添加材料层</button><p class="subtle">${constructions[key]?.length?'保存时计算对应 U 值':'尚无分层构造；此部分采用简化无热容 U 值模型。'}</p></fieldset>`).join('');
    host.querySelectorAll('[data-layer]').forEach(el=>{el.oninput=()=>{constructions[el.dataset.layer][Number(el.dataset.index)][el.dataset.key]=el.type==='number'?Number(el.value):el.value;markDirty();};});
    host.querySelectorAll('[data-delete-layer]').forEach(b=>{b.onclick=()=>{constructions[b.dataset.deleteLayer].splice(Number(b.dataset.index),1);if(!constructions[b.dataset.deleteLayer].length)delete constructions[b.dataset.deleteLayer];markDirty();paintConstructions();};});
    host.querySelectorAll('[data-add-layer]').forEach(b=>{b.onclick=()=>{const key=b.dataset.addLayer;constructions[key]??=[];if(constructions[key].length>=8){notice('每组最多八层',true);return;}constructions[key].push({name:'待填写材料',thickness_m:'',conductivity_w_mk:'',density_kg_m3:'',specific_heat_j_kgk:''});markDirty();paintConstructions();};});
  }
  paintConstructions();
  const preview=async()=>{
    const area=rooms.filter(r=>r.include_floor_area!==false).reduce((s,r)=>s+roomArea(r),0);
    const unresolved=rooms.filter(r=>r.include_floor_area===null||r.conditioned===null).length;
    host.querySelector('#model-summary').textContent=`${rooms.length} 个空间 · 计入 ${num(area)} m²${unresolved?' · '+unresolved+' 个用途待确认':''} · ${model?'保存版本 v'+model.revision:'未保存'}`;
    host.querySelector('#room-select').innerHTML=rooms.map((r,i)=>`<option value="${i}">${esc(r.name)} · ${num(roomArea(r))} m²</option>`).join('');
    selected=Math.max(0,Math.min(selected,rooms.length-1));host.querySelector('#room-select').value=String(selected);
    paintRoom();dispose();dispose=await renderBuilding(rooms,host,i=>{selected=i;host.querySelector('#room-select').value=String(i);paintRoom();});
  };
  function paintRoom(){
    const r=rooms[selected], target=host.querySelector('#room-editor');
    if(!r){target.innerHTML='<p class="empty">导入空间候选，或从一个矩形房间开始。</p>';return;}
    target.innerHTML=`<label>名称<input data-room="name" value="${esc(r.name)}"></label><div class="form-grid"><label>标高 m<input data-room="elevation_m" type="number" step=".1" value="${r.elevation_m}"></label><label>层高 m<input data-room="height_m" type="number" step=".1" min=".6" value="${r.height_m}"></label></div><label>来源定位<input data-room="source_locator" value="${esc(r.source_locator)}"></label><details><summary>边界顶点 · 米</summary><div class="model-vertices">${r.polygon.map((p,i)=>`<div><span>${i+1}</span>${p.map((v,j)=>`<input aria-label="顶点 ${i+1} ${j?'y':'x'}" data-point="${i}" data-axis="${j}" type="number" step=".01" value="${v}">`).join('')}<button data-remove-point="${i}" aria-label="删除顶点 ${i+1}">×</button></div>`).join('')}</div><button id="add-point">增加顶点</button></details><button id="remove-room">移除此编辑中的房间</button>`;
    const use=document.createElement('div');use.className='form-grid';
    use.innerHTML=[['conditioned','是否设置理想空调和人员/设备负荷'],['include_floor_area','是否计入项目面积']].map(([k,label])=>`<label>${label}<select data-use="${k}"><option value="">待复核</option><option value="true">是</option><option value="false">否</option></select></label>`).join('');
    target.prepend(use);
    use.querySelectorAll('[data-use]').forEach(el=>{const value=r[el.dataset.use];el.value=value===null?'':String(value??true);el.onchange=()=>{r[el.dataset.use]=el.value===''?null:el.value==='true';markDirty();action(preview);};});
    if(r.ifc_source||r.segments?.length){
      const note=document.createElement('p');note.className='subtle';note.textContent=`保留源模型的 ${roomSegments(r).length} 个高度分段。此处不把复杂几何改成普通柱体；尺寸修改请在源 IFC 中完成后重新导入。`;
      target.append(note);
      target.querySelectorAll('[data-point],[data-remove-point],#add-point,[data-room="elevation_m"],[data-room="height_m"]').forEach(el=>{el.disabled=true;});
    }
    target.querySelectorAll('[data-room]').forEach(el=>{el.onchange=()=>{r[el.dataset.room]=el.type==='number'?Number(el.value):el.value;setStatus('有未保存修改');action(preview);};});
    target.querySelectorAll('[data-point]').forEach(el=>{el.onchange=()=>{r.polygon[Number(el.dataset.point)][Number(el.dataset.axis)]=Number(el.value);setStatus('有未保存修改');action(preview);};});
    target.querySelectorAll('[data-remove-point]').forEach(el=>{el.onclick=()=>{if(r.polygon.length<=3){notice('至少保留三个顶点',true);return;}r.polygon.splice(Number(el.dataset.removePoint),1);markDirty();action(preview);};});
    target.querySelector('#add-point').onclick=()=>{const a=r.polygon.at(-1),b=r.polygon[0];r.polygon.push([(a[0]+b[0])/2,(a[1]+b[1])/2]);markDirty();action(preview);};
    target.querySelector('#remove-room').onclick=()=>{rooms.splice(selected,1);markDirty();action(preview);};
  }
  function paintImports(){
    host.querySelector('#model-imports').innerHTML=imports.slice(0,12).map(t=>`<details><summary>${esc(t.source?.name||t.candidate?.source?.name||t.import_id)} · ${esc(({failed:"导入受阻",awaiting_review:"待人工复核",completed:"已采纳",running:"识别中"})[t.status]||t.status)}</summary><p>${esc(t.error||'')}</p><ul>${(t.candidate?.warnings||[]).map(w=>'<li>'+esc(w)+'</li>').join('')}</ul>${importDiagnostics(t,base)}<p>${t.candidate?.rooms?.length??0} 个可采纳候选</p>${t.status==='awaiting_review'?`<button data-adopt="${t.import_id}">合并候选到编辑区</button>`:''}</details>`).join('');
    host.querySelectorAll('[data-adopt]').forEach(b=>{b.onclick=()=>action(async()=>{
      const task=imports.find(t=>t.import_id===b.dataset.adopt);
      if(!task.candidate.rooms.length)throw Error('没有可用的闭合空间，请检查比例、图层或切换视觉识别。');
      if(pending)throw Error('请先保存当前导入的复核结果，再合并其他资料。');
      rooms=mergeRooms(rooms,task.candidate.rooms);pending=task.import_id;markDirty();setStatus('候选已加入编辑区；请复核后确认空间并保存。');await preview();
    },b);});
  }
  async function refresh(){
    const check=await request(base+'/model/validate');
    if(!host.isConnected||state.project?.project_id!==pid)return;
    const review=check.geometry_review, boundaries=review?.boundary_faces;
    const details=review?`<p>热边界面：外界 ${num(boundaries.Outdoors)}；地面 ${num(boundaries.Ground)}；空间配对 ${num(boundaries.Surface)}；绝热 ${num(boundaries.Adiabatic)}。绝热面不与外界或相邻空间传热。</p><p>本次公差 ${num(review.adjustment.tolerance_m*1000)} mm，实际最大单轴位移 ${num(review.adjustment.max_axis_displacement_m*1000)} mm；逐空间变化记录随 IDF 证据保存。</p>`:'';
    host.querySelector('#model-gate').innerHTML=`<p class="${check.can_publish?'':'error-text'}">${check.can_publish?'模型可发布；请核对下列适用范围。':check.blockers.map(esc).join('；')}</p><details><summary>计算范围与简化</summary><ul>${check.limitations.map(l=>'<li>'+esc(l)+'</li>').join('')}</ul>${details}</details>`;
    const history=await request(base+'/model/history');
    if(!host.isConnected||state.project?.project_id!==pid)return;
    host.querySelector('#model-history').textContent=history.map(m=>`v${m.revision} · ${m.status} · ${m.actor} · ${m.updated_at}\n${m.review_note}\n来源：${m.sources.map(s=>s.name+' · SHA256 '+s.hash).join('；')||'人工建模'}`).join('\n\n');
    await refreshRuns();
  }
  async function refreshRuns(){
    const runs=await request(base+'/runs');
    if(!host.isConnected)return;
    host.querySelector('#model-runs').innerHTML=runs.slice(0,5).map(r=>`<p><strong>${esc(r.scheme_id)} · ${esc(r.status)}</strong> ${r.metrics?num(r.metrics.annual_energy_kwh)+' kWh · 核对能源种类及理想负荷范围':''} ${esc(r.error||'')} ${r.status==='queued'?`<button data-cancel-run="${r.run_id}">取消排队</button>`:''} <a href="/api/runs/${r.run_id}/report.html" target="_blank" rel="noopener">报告与依据 ↗</a></p>`).join('');
    host.querySelectorAll('[data-cancel-run]').forEach(b=>{b.onclick=()=>action(async()=>{await post(base+'/runs/'+b.dataset.cancelRun+'/cancel',{});await refreshRuns();},b);});
    await onChange(pid);
  }
  host.querySelector('#room-select').onchange=e=>{selected=Number(e.target.value);paintRoom();};
  host.querySelector('#add-room').onclick=()=>action(async()=>{
    const x=rooms.length?Math.max(...rooms.flatMap(r=>r.polygon.map(p=>p[0])))+1:0;
    rooms=mergeRooms(rooms,[{name:'新房间',polygon:[[x,0],[x+5,0],[x+5,4],[x,4]],elevation_m:0,height_m:3,source_locator:'人工草稿：请修改尺寸及来源'}]);selected=rooms.length-1;markDirty();setStatus('示意尺寸待修改及确认');await preview();
  });
  host.querySelector('#duplicate-floor').onclick=()=>action(async()=>{
    const r=rooms[selected];if(!r)throw Error('先选择房间');
    rooms=mergeRooms(rooms,[duplicateRoom(r)]);selected=rooms.length-1;markDirty();await preview();
  });
  host.querySelector('#model-import').onsubmit=e=>{e.preventDefault();const form=new FormData(e.currentTarget);action(async()=>{
    host.querySelector('#import-progress').textContent='正在读取资料与识别，请等待…';
    try{
      const filedata=new FormData();filedata.set('file',form.get('file'));
      const f=await request(base+'/files',{method:'POST',body:filedata});
      const task=await post(base+'/imports',{file_id:f.file_id,mode:form.get('mode'),
        scale_to_m:form.get('scale_to_m')?Number(form.get('scale_to_m')):null,
        height_m:Number(form.get('height_m')),elevation_m:Number(form.get('elevation_m')),
        page:Number(form.get('page')),layer:form.get('layer')||null,send_to_provider:form.has('send_to_provider')});
      imports.unshift(task);paintImports();host.querySelector('#import-progress').textContent='识别完成，请展开任务并合并候选后复核。';
    }catch(error){if(host.isConnected&&state.project?.project_id===pid){host.querySelector('#import-progress').textContent=error.message;try{imports=await request(base+'/imports');if(host.isConnected&&state.project?.project_id===pid)paintImports();}catch{ /* Preserve the original import failure. */ }}throw error;}
  },e.submitter);};
  host.querySelector('#teaching-thermal').onclick=()=>{
    host.querySelectorAll('[data-thermal]').forEach(el=>{el.value=teachingThermal[el.dataset.thermal];});host.querySelector('#thermal-basis').value='assumed_scenario';host.querySelector('#thermal-source').value=teachingThermal.source_note;
    for(const [key,depth] of [['wall',.04],['roof',.08],['floor',.05]])constructions[key]=[
      {name:'假设混凝土',thickness_m:.2,conductivity_w_mk:1.4,density_kg_m3:2300,specific_heat_j_kgk:900},
      {name:'假设保温层',thickness_m:depth,conductivity_w_mk:.04,density_kg_m3:40,specific_heat_j_kgk:1400}
    ];paintConstructions();markDirty();
  };
  function body(reviewed){
    const values=[...host.querySelectorAll('[data-thermal]')],hasThermal=values.some(el=>el.value!=='');
    if(hasThermal&&values.some(el=>el.value===''))throw Error('请补齐热工字段，或全部留空仅保存空间模型。');
    if(!hasThermal&&Object.keys(constructions).length)throw Error('已输入构造层，请补齐其余热工参数。');
    const thermal=hasThermal?{...Object.fromEntries(values.map(el=>[el.dataset.thermal,Number(el.value)])),constructions,basis:host.querySelector('#thermal-basis').value,source_note:host.querySelector('#thermal-source').value,ifc_unpaired_policy:host.querySelector('#ifc-boundary-policy').value,geometry_tolerance_m:Number(host.querySelector('#geometry-tolerance').value)}:null;
    return {expected_revision:model?.revision||0,name:host.querySelector('#model-name').value,rooms,thermal,reviewed,review_note:host.querySelector('#model-review').value};
  }
  async function save(reviewed){
    const data=body(reviewed);
    if(pending){
      if(!reviewed)throw Error('导入工作流需要「确认空间并保存」；候选任务已持久保存，可稍后继续复核。');
      const result=await post(base+'/imports/'+pending+'/review',data);model=result.model;pending=null;imports=await request(base+'/imports');paintImports();
    }else model=await request(base+'/model',{method:'PUT',body:JSON.stringify(data)});
    rooms=structuredClone(model.rooms);dirty=false;
    if(model.thermal)host.querySelectorAll('[data-thermal]').forEach(el=>{el.value=model.thermal[el.dataset.thermal];});
    setStatus('已保存 v'+model.revision+' · '+model.status);await preview();await refresh();
  }
  host.querySelector('#save-model').onclick=e=>action(()=>save(false),e.currentTarget);
  host.querySelector('#review-model').onclick=e=>action(()=>save(true),e.currentTarget);
  host.querySelector('#sync-model-area').onclick=e=>action(async()=>{if(!model)throw Error('先保存模型');const updated=await post(base+'/model/sync-area',{revision:model.revision});if(!host.isConnected||state.project?.project_id!==pid)return;state.project=updated;await refresh();notice('项目面积已同步；已有计算会重新核验版本。');},e.currentTarget);
  host.querySelector('#publish-model').onclick=e=>action(async()=>{if(!model||dirty)throw Error('请先保存当前编辑');const result=await post(base+'/model/publish',{revision:model.revision,scheme_id:host.querySelector('#model-scheme').value,responsible_person:state.user.display_name,review_note:host.querySelector('#publish-note').value});const [evidence,gate]=await Promise.all([request(base+'/evidence'),request(base+'/gate')]);if(!host.isConnected||state.project?.project_id!==pid)return;state.evidence=evidence;state.gate=gate;notice(result.reused?'已存在此模型对应的有效 IDF':'IDF 已生成并登记；请确认天气后运行。');await refresh();},e.currentTarget);
  host.querySelector('#run-model').onclick=e=>action(async()=>{if(dirty)throw Error('请先保存当前编辑并发布，再提交计算');await post(base+'/model-runs',{scheme_id:host.querySelector('#model-scheme').value});notice('已提交真实 EnergyPlus 队列');await refreshRuns();},e.currentTarget);
  host.querySelector('#model-api').onclick=()=>projectTokens(pid,host,action,notice);
  paintImports();await preview();await refresh();
  const timer=setInterval(()=>{if(!host.isConnected){clearInterval(timer);dispose();return;}if(!document.hidden)action(refreshRuns);},4000);
}

async function renderBuilding(rooms,host,onPick){
  const target=host.querySelector('#building-canvas'), plan=host.querySelector('#model-plan');
  target.innerHTML='';plan.innerHTML='';
  if(!rooms.length){target.innerHTML='<p class="empty">导入或添加房间，开始建立模型。</p>';return ()=>{};}
  const points=rooms.flatMap(r=>roomSegments(r).flatMap(s=>s.polygon)),minX=Math.min(...points.map(p=>p[0])),minY=Math.min(...points.map(p=>p[1]));
  const maxX=Math.max(...points.map(p=>p[0])),maxY=Math.max(...points.map(p=>p[1]));
  plan.innerHTML=`<svg viewBox="${minX-1} ${minY-1} ${maxX-minX+2} ${maxY-minY+2}" role="img" aria-label="房间平面轮廓">${rooms.map((r,i)=>`<polygon data-pick="${i}" points="${r.polygon.map(p=>p.join(',')).join(' ')}"><title>${esc(r.name)} · ${num(polygonArea(r.polygon))} m²</title></polygon>`).join('')}</svg>`;
  plan.querySelectorAll('[data-pick]').forEach(p=>{p.onclick=()=>onPick(Number(p.dataset.pick));});
  try{
    const THREE=await import('three'),{OrbitControls}=await import('three/addons/controls/OrbitControls.js');
    if(!host.isConnected)return ()=>{};
    const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));target.append(renderer.domElement);
    const scene=new THREE.Scene();scene.background=new THREE.Color('#edf2f6');
    const camera=new THREE.PerspectiveCamera(42,1,.05,10000),controls=new OrbitControls(camera,renderer.domElement);
    scene.add(new THREE.HemisphereLight(0xffffff,0x667d91,2.5));
    const sun=new THREE.DirectionalLight(0xffffff,2);sun.position.set(20,40,10);scene.add(sun);
    const meshes=rooms.flatMap((r,i)=>roomSegments(r).map(segment=>{
      const shape=new THREE.Shape(segment.polygon.map(([x,y])=>new THREE.Vector2(x,-y)));
      const mesh=new THREE.Mesh(new THREE.ExtrudeGeometry(shape,{depth:segment.height_m,bevelEnabled:false}),
        new THREE.MeshStandardMaterial({color:new THREE.Color().setHSL(.56+i*.011,.35,.55),roughness:.75,transparent:true,opacity:.85}));
      mesh.rotation.x=-Math.PI/2;mesh.position.y=segment.elevation_m;mesh.userData.index=i;scene.add(mesh);
      const edges=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry),new THREE.LineBasicMaterial({color:0x32566d}));
      mesh.add(edges);return mesh;
    }));
    const bounds=new THREE.Box3();meshes.forEach(m=>bounds.expandByObject(m));const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3()),span=Math.max(size.x,size.y,size.z,5);
    camera.position.copy(center).add(new THREE.Vector3(span,span*.85,span));controls.target.copy(center);controls.update();
    const grid=new THREE.GridHelper(span*2,20,0xaebdca,0xd4dee6);grid.position.set(center.x,bounds.min.y-.02,center.z);scene.add(grid);
    const resize=()=>{const width=Math.max(target.clientWidth,200);renderer.setSize(width,360);camera.aspect=width/360;camera.updateProjectionMatrix();};
    const observer=new ResizeObserver(resize);observer.observe(target);resize();
    host.querySelector('#model-xray').onchange=e=>{meshes.forEach(m=>{m.material.opacity=e.target.checked?.25:.85;m.material.depthWrite=!e.target.checked;});};
    let down;
    renderer.domElement.onpointerdown=e=>{down=[e.clientX,e.clientY];};
    renderer.domElement.onpointerup=e=>{if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),camera);const hit=ray.intersectObjects(meshes,false)[0];if(hit)onPick(hit.object.userData.index);};
    let alive=true;
    const dispose=()=>{if(!alive)return;alive=false;observer.disconnect();controls.dispose();scene.traverse(o=>{o.geometry?.dispose();if(o.material){if(Array.isArray(o.material))o.material.forEach(m=>m.dispose());else o.material.dispose();}});renderer.dispose();};
    function frame(){if(!alive)return;if(!host.isConnected){dispose();return;}renderer.render(scene,camera);requestAnimationFrame(frame);}frame();return dispose;
  }catch(error){target.textContent='三维渲染不可用，可使用下方二维轮廓与尺寸编辑。'+error.message;return ()=>{};}
}
