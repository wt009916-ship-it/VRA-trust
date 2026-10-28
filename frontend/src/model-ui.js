import { polygonArea, geometricFloorArea } from './floor-area.js';
export { polygonArea };
import { reviewUseScope } from './scope-review.js';
import { shellGeometry, storeyKey } from './solid-preview.js';
import { engineeringInputs } from './engineering-inputs.js';
import { centralSystemInputs } from './central-system.js';
import { markUnsaved } from './editing-guard.js';
import { mountModelStudio } from './studio-layout.js';
import { planCalibration } from './plan-calibration.js';
import { thermalResults } from './thermal-results.js';
import { importDiagnostics } from './assurance-ui.js';
import { request, post, escape as esc, number as num, uploadLimitMB } from './api.js';
function projectTokens(pid, host, action, notice) {
  action(async()=>{
    const base='/projects/'+pid,dialog=document.createElement('dialog');
    dialog.className='token-dialog';document.body.append(dialog);
    dialog.innerHTML=`<div class="dialog-heading"><h2>项目 API / MCP</h2><button id="close-token" aria-label="关闭">×</button></div><p>Token 仅限当前项目。密钥只显示一次，后端只保存哈希；可随时撤销。</p><form id="token-form"><label>用途名称<input name="name" required maxlength="80" placeholder="如 Codex 工程助手"></label><label>有效期 · 天<input name="days" type="number" value="30" min="1" max="90"></label><label class="check-option"><input name="read" type="checkbox" checked>读取模型、证据和结果</label><label class="check-option"><input name="write" type="checkbox">编辑资料与模型</label><label class="check-option"><input name="compute" type="checkbox">提交真实计算</label><button class="primary">创建专属 Token</button></form><div id="new-token" role="status"></div><div id="token-list"></div><details><summary>MCP 客户端配置示例</summary><pre id="mcp-config"></pre></details><p class="subtle">将 command 与 args 改成项目虚拟环境 Python 和 scripts/run_mcp.py 的绝对路径。Token 放在客户端配置或进程环境中，勿提交到 Git。</p>`;
    dialog.querySelector('#mcp-config').textContent=JSON.stringify({mcpServers:{'vra-trust':{command:'<项目>/.venv/Scripts/python.exe',args:['<项目绝对路径>/scripts/run_mcp.py'],env:{VRA_BASE_URL:location.origin,VRA_PROJECT_ID:pid,VRA_API_TOKEN:'<本项目 Token>'}}}},null,2);
    dialog.querySelector('#close-token').onclick=()=>dialog.close();
    dialog.onclose=()=>dialog.remove();dialog.showModal();
    async function paint(){
      const tokens=await request(base+'/tokens');if(!dialog.isConnected)return;
      dialog.querySelector('#token-list').innerHTML=tokens.map(t=>`<p><strong>${esc(t.name)}</strong> · ${esc(t.scopes.join('/'))} · ${new Date(t.expires*1000).toLocaleDateString()} ${t.revoked?'已撤销':`<button data-revoke="${t.id}">撤销</button>`}</p>`).join('');
      dialog.querySelectorAll('[data-revoke]').forEach(b=>{b.onclick=()=>action(async()=>{await request(base+'/tokens/'+b.dataset.revoke,{method:'DELETE'});await paint();},b);});
    }
    dialog.querySelector('#token-form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.currentTarget);action(async()=>{
      const token=await post(base+'/tokens',{name:f.get('name'),days:Number(f.get('days')),scopes:['read','write','compute'].filter(k=>f.has(k))});
      dialog.querySelector('#new-token').innerHTML=`<label>立即复制，关闭后不再显示<input readonly value="${esc(token.token)}" aria-label="新创建的 API Token"></label>`;
      await paint();notice('项目 Token 已创建');
    },e.submitter);};await paint();
  });
}


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

export function roomSegments(room) {
  return room.segments?.length ? room.segments : [room];
}

export function roomArea(room) { return geometricFloorArea(room); }

export function duplicateRoom(room) {
  const r=structuredClone(room),dz=r.height_m;
  r.name+=' 上层';r.elevation_m+=dz;
  r.segments?.forEach(s=>{s.elevation_m+=dz;});
  r.shell?.forEach(f=>f.points.forEach(p=>{p[2]+=dz;}));
  r.source_openings?.forEach(f=>f.points.forEach(p=>{p[2]+=dz;}));
  r.boundary_hints?.forEach(h=>h.points.forEach(p=>{p[2]+=dz;}));
  r.geometry_inferred=true;r.storey_id=null;r.storey_name=(r.storey_name||'人工楼层')+' 上层副本';
  r.source_locator+=`；人工复制并上移 ${dz} m，须重新复核`;
  return r;
}

export function mergeRooms(existing, candidates) {
  const rooms=structuredClone(existing),used=new Set(rooms.map(r=>r.id));let next=1;
  for(const candidate of structuredClone(candidates)){
    if(used.has(candidate.id)){while(used.has('R'+next))next++;candidate.id='R'+next++;}
    used.add(candidate.id);rooms.push(candidate);
  }
  return rooms;
}

export async function spatialWorkspace(state, host, action, notice, onChange=()=>{}) {
  const pid=state.project.project_id, base='/projects/'+pid;
  let model=await request(base+'/model'), imports=await request(base+'/imports');
  if(!host.isConnected)return;
  let rooms=structuredClone(model?.rooms||[]), pending=null, selected=Math.max(0,(model?.rooms||[]).findIndex(r=>r.id===state.reviewRoomId)), dispose=()=>{}, dirty=false, previewGeneration=0;
  const constructions=structuredClone(model?.thermal?.constructions||{});
  host.innerHTML=`<div class="view-heading"><div><span class="eyebrow">BUILDING WORKBENCH</span><h1>资料进入，空间成形。</h1><p>DXF · 矢量 PDF · IFC · 图片识别 → 几何复核 → 三维模型 → EnergyPlus</p></div><button id="model-api">项目 API / MCP</button></div>
  <div class="model-workbench"><div class="model-inputs">
  <details class="model-card" open><summary>01 / 导入与识别</summary><form id="model-import">
  <label>选择资料 · 最大 ${uploadLimitMB()} MB<input name="file" type="file" accept=".dxf,.dwg,.pdf,.ifc,.png,.jpg,.jpeg" required></label>
  <label>识别方式<select name="mode"><option value="geometry">本地几何解析 · DXF / PDF / IFC</option><option value="damaged_raster">老旧图纸增强 · 破损 / 褪色 / 扫描倾斜</option><option value="local_raster">原始墙线 + OCR · 对照模式</option><option value="vision">视觉模型 · 扫描 PDF / 图片</option></select></label>
  <div class="form-grid"><label>长度换算系数<input name="scale_to_m" type="number" step="any" min=".0000001" placeholder="DXF 可自动读取单位"></label><label>页码<input name="page" type="number" value="1" min="1" max="500"></label><label>候选层高 m<input name="height_m" type="number" value="3" step=".1" min=".6" max="30"></label><label>候选标高 m<input name="elevation_m" type="number" value="0" step=".1"></label></div>
  <label>DXF 图层（可选）<input name="layer" placeholder="建议先选择房间边界图层"></label>
  <p class="subtle">换算系数 = 米 / 图纸单位；PDF 为米 / point，图片为米 / 原图像素。PDF 视觉识别按 72 dpi 渲染；本地图纸模式使用下方预览像素标定。DWG 请先导出 DXF。</p>
  <label class="check-option"><input name="reconstruct_elements" type="checkbox" checked>无IfcSpace时从实际墙板截面生成待复核空间；缺外立面/上界会明确标记</label><label>构件重建修模公差 m<input name="reconstruction_tolerance_m" type="number" value="0" min="0" max=".02" step=".001"><small>0保留细节；非零须同时满足逐源轮廓的位移、0.01m²绝对面积和1%相对面积预算。</small></label><label>源窗修模公差 m<input name="source_window_tolerance_m" type="number" value="0" min="0" max=".02" step=".001"><small>0保留原形；非零为显式候选简化，位移受限且窗面积变化不得超过1%。</small></label><label class="check-option"><input name="reconstruct_footprints" type="checkbox">IFC 缺少 Body 时，允许从闭合 FootPrint 与一致的高度/面积/体积工程量生成待复核柱体</label><label class="check-option"><input name="send_to_provider" type="checkbox">允许把本次选中的图页发送给开发者设置中的视觉服务</label>
  <button class="primary">识别空间候选</button><p id="import-progress" role="status"></p></form>
  <div id="model-imports"></div></details>
  <section class="model-card"><h2>02 / 空间与尺寸</h2><div class="actions"><button id="add-room">＋ 矩形房间</button><button id="duplicate-floor">复制到上一层</button></div>
  <label>当前房间<select id="room-select"></select></label><div id="room-editor"></div></section>
  </div><div class="model-main">
  <section class="model-card model-preview"><div class="model-preview-top"><span id="model-summary"></span><label class="check-option"><input id="model-xray" type="checkbox">透视</label></div><div id="building-canvas" aria-label="建筑空间三维预览"></div><div id="model-plan" aria-label="二维空间轮廓"></div><p class="subtle">蓝色空间为当前编辑内容；三维预览用于检查空间关系，未保存的修改不会进入仿真。</p></section>
  <details class="model-card"><summary>03 / 热工与运行参数</summary><p>所有参数须注明来源。理想负荷输出冷热需求；PTHP与中央系统输出所配置设备的分能源情景用能，不能与实测混同。</p><button id="teaching-thermal">填入教学假设供试运行</button><p class="subtle">发布前须填齐下列参数及来源。无法从图纸确定的值应保留为空，或明确声明假设。</p><div class="form-grid" id="thermal-fields">${thermalFields.map(([k,l])=>`<label>${l}<input data-thermal="${k}" type="number" step="any" value="${esc(model?.thermal?.[k]??'')}"></label>`).join('')}</div><label>参数性质<select id="thermal-basis"><option value="assumed_scenario">明确假设的工程情景</option value="documented">有设计 / 检测文件依据</option></select></label><label>参数来源与适用条件<textarea id="thermal-source" minlength="10">${esc(model?.thermal?.source_note||'')}</textarea></label></details>
  <section class="model-card"><h2>04 / 复核、保存与计算</h2><label>模型名称 · 必填<input required id="model-name" value="${esc(model?.name||state.project.name)}"></label><label>复核说明 · 确认空间时必填<textarea id="model-review" minlength="5" placeholder="说明比例依据、核对的房间和仍存在的假设">${esc(model?.review_note||'')}</textarea></label>
  <div class="actions"><button id="save-model">保存草稿</button><button class="primary" id="review-model">确认空间并保存</button><button id="sync-model-area">同步项目面积</button></div>
  <p id="model-status" role="status"></p><div id="model-gate"></div>
  <div class="form-grid"><label>发布为方案<select id="model-scheme"><option value="baseline">基准 baseline</option><option value="R1">方案 R1</option><option value="R2">方案 R2</option></select></label><label>发布与参数复核依据 · 必填<input id="publish-note" minlength="10" placeholder="确认空间、参数性质和设备计算口径"></label></div>
  <div class="actions"><button id="publish-model">生成并登记 IDF</button><button id="run-model">提交全年仿真</button><a href="/api${base}/model/export.ifc" download>导出 IFC 空间模型</a><a href="/api${base}/model/export.idf" download>导出 IDF</a><a href="/api${base}/model/geometry.hbjson" download>Honeybee 几何交换</a></div>
  <p class="subtle">发布会以新版本替代此方案的有效 IDF，旧资料和计算记录保留。还需在「资料」中登记并确认项目对应的全年 EPW。</p>
  <div id="model-runs"></div><details><summary>版本与来源</summary><pre id="model-history"></pre></details>
  </section></div></div>`;
  const importForm=host.querySelector('#model-import');
  const calibration=planCalibration(importForm,base,action);
  let ifcOrigin=null;
  const floorPanel=document.createElement('details');floorPanel.className='model-card';
  floorPanel.innerHTML='<summary>IFC 楼层范围</summary><button type="button" data-storeys>读取所选 IFC 楼层</button><p>不选择楼层时解析整份文件；勾选后仅尝试选定楼层，范围外空间不计入本次模型。单模型预算2000空间，保留逐层来源与范围。楼层边界须人工核对。</p><div data-storey-list></div>';
  importForm.querySelector('[name="reconstruct_footprints"]').closest('label').before(floorPanel);
  importForm.elements.file.addEventListener('change',()=>{floorPanel.querySelector('[data-storey-list]').innerHTML='';ifcOrigin=null;});
  floorPanel.querySelector('[data-storeys]').onclick=e=>action(async()=>{
    const file=await calibration.upload(), info=await request(base+'/files/'+file.file_id+'/ifc-storeys');
    ifcOrigin=info.suggested_origin_m;
    floorPanel.querySelector('[data-storey-list]').innerHTML=(ifcOrigin?`<label class="check-option"><input type="checkbox" data-local-origin>将源站点原点 ${ifcOrigin.map(v=>num(v)).join(', ')} m 平移为本地原点（保留方向及转换记录）</label>`:'')+`<p>共 ${info.total_spaces} 个空间 · ${info.unassigned_spaces} 个无楼层归属</p>`+info.storeys.map(f=>`<label class="check-option"><input type="checkbox" data-storey value="${esc(f.id)}">${esc(f.name)} · ${f.spaces} 个源空间 · ${f.elements||0} 个构件 · 标高 ${num(f.elevation_m)} m</label>`).join('');
  },e.currentTarget);
  if(model?.thermal)host.querySelector('#thermal-basis').value=model.thermal.basis;
  const boundaryPolicy=document.createElement('label');
  boundaryPolicy.innerHTML='<span>IFC 未配对边界</span><select id="ifc-boundary-policy"><option value="reject">阻止发布，等待补全邻接</option><option value="adiabatic_scenario">假设情景：未配对内部/未知边界按绝热处理</option></select><small>绝热处理会改变冷热需求，只能用于明确标注的假设情景；不代表完整建筑性能。</small>';
  host.querySelector('#thermal-source').parentElement.after(boundaryPolicy);
  host.querySelector('#ifc-boundary-policy').value=model?.thermal?.ifc_unpaired_policy||'reject';
  const tolerance=document.createElement('label');
  tolerance.innerHTML=`几何归并公差 m<input id="geometry-tolerance" type="number" min="0" max=".05" step=".001" value="${esc(model?.thermal?.geometry_tolerance_m??0)}"><small>默认 0，不调整几何。仅假设情景可显式设置，用于处理引擎不接受的细碎面；发布记录保留实际位移和每个空间的面积、体积变化。</small>`;
  boundaryPolicy.after(tolerance);
  const gap=document.createElement('label');gap.innerHTML=`跨墙厚配对上限 m<input id="adjacency-gap" type="number" min="0" max=".6" step=".01" value="${esc(model?.thermal?.adjacency_gap_m??0)}"><small>默认不推断；仅明确假设情景可按距离将相向平行面配对，保留原空间体积和逐面距离。不是施工连接证明。</small>`;tolerance.after(gap);
  const operationPanel=document.createElement('details');operationPanel.className='model-card';
  operationPanel.innerHTML='<summary>逐时运行、新风与热回收</summary><label class="check-option"><input id="operation-enabled" type="checkbox">启用有来源的运行档案</label><p>每个格子是该小时的使用率 0–1；人员、照明、设备共享此档案。使用率为 0 时采用非使用温度；理想负荷模式新风按人数及面积之和计算；人数部分随使用率变化，面积部分全天持续。PTHP 的新风与风机规则见设备卡。假日按周末处理，未配置当地节假日日历。</p><div id="operation-fields"></div>';
  gap.after(operationPanel);
  const operationFields=[['outdoor_air_l_s_person','新风 L/(s·人)'],['outdoor_air_l_s_m2','新风 L/(s·m²)'],['sensible_recovery','显热回收效率 0–0.95'],['latent_recovery','潜热回收效率 0–0.95'],['heating_setback_c','非使用供暖温度 °C'],['cooling_setback_c','非使用制冷温度 °C']];
  function paintOperation(op){
    host.querySelector('#operation-enabled').checked=!!op;
    host.querySelector('#operation-fields').innerHTML=['weekday','weekend'].map((key,i)=>`<fieldset><legend>${i?'周末 / 假日':'工作日'} · 24 小时使用率</legend><div class="hour-grid">${Array.from({length:24},(_,h)=>`<label>${h}时<input data-hour="${key}" data-index="${h}" type="number" min="0" max="1" step=".1" value="${esc(op?.[key]?.[h]??'')}"></label>`).join('')}</div></fieldset>`).join('')+`<div class="form-grid">${operationFields.map(([key,label])=>`<label>${label}<input data-operation="${key}" type="number" step="any" value="${esc(op?.[key]??'')}"></label>`).join('')}</div><label>运行档案来源（必填）<textarea id="operation-source" minlength="10">${esc(op?.source_note||'')}</textarea></label>`;
  }
  paintOperation(model?.thermal?.operation);
  const pumpPanel=document.createElement('details');pumpPanel.className='model-card';
  const pumpFields=[['cooling_w_m2','额定制冷量 W/m²',10,500],['heating_w_m2','额定制热量 W/m²',10,500],['airflow_l_s_m2','额定风量 L/(s·m²)',.5,30],['cooling_cop','制冷 COP',1,8],['heating_cop','制热 COP',1,8],['sensible_heat_ratio','额定显热比',.5,.95],['fan_pressure_pa','风机压升 Pa',0,1500],['fan_total_efficiency','风机总效率',.1,1],['fan_motor_efficiency','电机效率',.1,1],['supplemental_w_m2','电辅热 W/m²',0,500],['minimum_outdoor_c','制热压缩机最低室外温度 °C',-20,5],['minimum_cooling_outdoor_c','制冷压缩机最低室外温度 °C',0,18]];
  const pump=model?.thermal?.heat_pump;
  pumpPanel.innerHTML=`<summary>设备模型 · 单速空气源热泵</summary><label class="check-option"><input id="pump-enabled" type="checkbox" ${pump?'checked':''}>采用定容 PTHP 计算设备耗电</label><p>不勾选则计算理想冷热需求。勾选后，每个空调空间按面积配置独立热泵、风机和电辅热，以下参数全部必填。须启用逐时档案且热回收效率为 0。新风按设计人数和面积定流量，使用时连续风机，其余随冷热负荷启停。</p><p>原生引擎计算变工况与除霜；曲线为 EnergyPlus 官方模板假设，不能代替厂家性能数据。容量不足会出现未满足温度时数，须一起审阅。</p><div class="form-grid">${pumpFields.map(([key,label,min,max])=>`<label>${label}<input data-pump="${key}" type="number" step="any" min="${min}" max="${max}" value="${esc(pump?.[key]??'')}"></label>`).join('')}</div><label>设备参数来源（必填，至少 10 字）<textarea id="pump-source" minlength="10">${esc(pump?.source_note||'')}</textarea></label>`;
  operationPanel.after(pumpPanel);
  function pumpBody(){
    if(!host.querySelector('#pump-enabled').checked)return null;
    const fields=[...host.querySelectorAll('[data-pump]')];
    if(fields.some(el=>el.value===''))throw Error('启用热泵后须填齐额定容量、效率、风量及电辅热参数；不会自动猜测设备。');
    return {...Object.fromEntries(fields.map(el=>[el.dataset.pump,Number(el.value)])),source_note:host.querySelector('#pump-source').value};
  }
  function operationBody(){
    if(!host.querySelector('#operation-enabled').checked)return null;
    const fields=[...host.querySelectorAll('[data-operation],[data-hour]')];
    if(fields.some(el=>el.value===''))throw Error('启用运行档案后须补齐逐时使用率、新风、回收和非使用温度；无新风/回收请明确填写 0。');
    return {...Object.fromEntries([...host.querySelectorAll('[data-operation]')].map(el=>[el.dataset.operation,Number(el.value)])),weekday:[...host.querySelectorAll('[data-hour="weekday"]')].map(el=>Number(el.value)),weekend:[...host.querySelectorAll('[data-hour="weekend"]')].map(el=>Number(el.value)),source_note:host.querySelector('#operation-source').value};
  }
  const setStatus=text=>{host.querySelector('#model-status').textContent=text;};
  const markDirty=()=>{dirty=true;markUnsaved(host);setStatus('有未保存的编辑，请保存后再发布或计算。');};
  host.addEventListener('input',e=>{if(e.target.matches('[data-room],[data-point],[data-thermal],[data-operation],[data-hour],[data-pump],#pump-source,#pump-enabled,#operation-source,#operation-enabled,#adjacency-gap,#thermal-source,#thermal-basis,#model-name,#model-review'))markDirty();});
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
  const engineering=engineeringInputs(host,{base,model,action,markDirty,notice});
  const centralBody=centralSystemInputs(host,{base,model,action,markDirty,notice});
  const studio=mountModelStudio(host,{projectId:pid,area:roomArea,
    selectRoom:index=>{selected=index;host.querySelector('#room-select').value=String(index);paintRoom();dispose.select?.(index);},
    fit:()=>dispose.fit?.(),filterStorey:key=>dispose.filterStorey?.(key),
    batchUse:options=>action(async()=>{const result=reviewUseScope(rooms,options),field=host.querySelector('#model-review'),note=[field.value,result.note].filter(Boolean).join('\n');if(note.length>2000)throw Error('复核说明超过2000字符，请整理后再批量确认。');rooms=result.rooms;field.value=note;markDirty();await preview();notice(result.affected.length+'个空间属性已更新到草稿，确认依据将随模型版本保存。');})});
  const preview=async()=>{
    const generation=++previewGeneration;
    const area=rooms.filter(r=>r.include_floor_area!==false).reduce((s,r)=>s+roomArea(r),0);
    const unresolved=rooms.filter(r=>r.include_floor_area===null||r.conditioned===null).length;
    host.querySelector('#model-summary').textContent=`${rooms.length} 个空间 · ${rooms.some(r=>r.include_floor_area===null)?'候选面积':'计入面积'} ${num(area)} m²${unresolved?' · '+unresolved+' 个用途待确认':''} · ${model?'保存版本 v'+model.revision:'未保存'}`;
    host.querySelector('#room-select').innerHTML=rooms.map((r,i)=>`<option value="${i}">${esc(r.name)} · ${num(roomArea(r))} m²</option>`).join('');
    selected=Math.max(0,Math.min(selected,rooms.length-1));host.querySelector('#room-select').value=String(selected);
    paintRoom();dispose();dispose=()=>{};
    const rendered=await renderBuilding(rooms,host,i=>{selected=i;host.querySelector('#room-select').value=String(i);paintRoom();dispose.select?.(i);});
    if(generation!==previewGeneration||!host.isConnected){rendered();return;}
    dispose=rendered;dispose.select?.(selected);studio.update({rooms,selected,sources:model?.sources||[],model,canFit:!!dispose.fit});
  };
  function paintRoom(){
    studio.update({rooms,selected,sources:model?.sources||[],model,canFit:!!dispose.fit});
    const r=rooms[selected], target=host.querySelector('#room-editor');
    if(!r){target.innerHTML='<p class="empty">导入空间候选，或从一个矩形房间开始。</p>';return;}
    target.innerHTML=`<label>名称<input data-room="name" value="${esc(r.name)}"></label><div class="form-grid"><label>标高 m<input data-room="elevation_m" type="number" step=".1" value="${r.elevation_m}"></label><label>层高 m<input data-room="height_m" type="number" step=".1" min=".6" value="${r.height_m}"></label></div><label>来源定位<input data-room="source_locator" value="${esc(r.source_locator)}"></label><details><summary>边界顶点 · 米</summary><div class="model-vertices">${r.polygon.map((p,i)=>`<div><span>${i+1}</span>${p.map((v,j)=>`<input aria-label="顶点 ${i+1} ${j?'y':'x'}" data-point="${i}" data-axis="${j}" type="number" step=".01" value="${v}">`).join('')}<button data-remove-point="${i}" aria-label="删除顶点 ${i+1}">×</button></div>`).join('')}</div><button id="add-point">增加顶点</button></details><button id="remove-room">移除此编辑中的房间</button>`;
    const use=document.createElement('div');use.className='form-grid';
    use.innerHTML=[['conditioned','是否设置空调和人员/设备负荷'],['include_floor_area','是否计入项目面积']].map(([k,label])=>`<label>${label}<select data-use="${k}"><option value="">待复核</option><option value="true">是</option><option value="false">否</option></select></label>`).join('');
    target.prepend(use);
    if(r.drawing?.interior_islands_px?.length){
      const review=document.createElement('section');review.className='model-card';
      review.innerHTML=`<h3>内部线岛待复核 · ${r.drawing.interior_islands_px.length} 处</h3><p>已保留房间轮廓，并从面积和体积中排除这些区域。线岛可能是柱、孔洞或图上标注；目前没有自动判定为真实竖井。确认前请对照原图，说明保留这些排除区的工程依据。若它们实际是标注，请修订源几何后再导入，不能只填说明消除几何问题。</p><label>内部排除区复核依据 · 确认时必填，至少10字<textarea data-interior-review minlength="10" maxlength="1000">${esc(r.drawing.interior_review_note||'')}</textarea></label>`;
      target.prepend(review);
      review.querySelector('textarea').oninput=e=>{r.drawing.interior_review_note=e.target.value;markDirty();};
    }
    use.querySelectorAll('[data-use]').forEach(el=>{const value=r[el.dataset.use];el.value=value===null?'':String(value??true);el.onchange=()=>{r[el.dataset.use]=el.value===''?null:el.value==='true';markDirty();action(preview);};});
    if(r.ifc_source||r.segments?.length||r.shell?.length){
      const note=document.createElement('p');note.className='subtle';note.textContent=r.drawing?`保留图纸区域及内部排除区的 ${roomSegments(r).length} 个几何分片。复杂轮廓不可在此仅改外边界而破坏孔洞；须结合原图复核。`:`保留源模型的 ${r.shell?.length?`${r.shell.length}个实体斜面`:roomSegments(r).length+'个高度分段'}。此处不把复杂几何改成普通柱体；尺寸修改请在源 IFC 中完成后重新导入。`;
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
    host.querySelector('#model-imports').innerHTML=imports.length?imports.slice(0,12).map(t=>`<details><summary>${esc(t.source?.name||t.candidate?.source?.name||t.import_id)} · ${esc(({failed:"导入受阻",awaiting_review:"待人工复核",completed:"已采纳",running:"识别中"})[t.status]||t.status)}</summary><p>${esc(t.error||'')}</p><ul>${(t.candidate?.warnings||[]).map(w=>'<li>'+esc(w)+'</li>').join('')}</ul>${importDiagnostics(t,base)}<p>${t.candidate?.rooms?.length??0} 个可采纳候选</p>${(t.candidate?.rooms?.some(r=>r.drawing)||t.diagnostics?.damage_analysis)?`<button data-overlay="${t.import_id}">原图叠加与面积误差</button>`:''}${t.status==='awaiting_review'?`<button data-adopt="${t.import_id}">合并候选到编辑区</button>`:''}</details>`).join(''):'<p class="studio-empty">尚无识别任务。导入资料后，可在这里核对候选与来源。</p>';
    host.querySelectorAll('[data-overlay]').forEach(b=>{b.onclick=()=>action(async()=>{studio.showOverlay();await calibration.overlay(imports.find(t=>t.import_id===b.dataset.overlay));},b);});
    host.querySelectorAll('[data-adopt]').forEach(b=>{b.onclick=()=>action(async()=>{
      const task=imports.find(t=>t.import_id===b.dataset.adopt);
      if(!task.candidate.rooms.length)throw Error('没有可用的闭合空间，请检查比例、图层或切换视觉识别。');
      if(pending)throw Error('请先保存当前导入的复核结果，再合并其他资料。');
      engineering.imported(task.candidate);rooms=mergeRooms(rooms,task.candidate.rooms);pending=task.import_id;markDirty();setStatus('候选已加入编辑区；请复核后确认空间并保存。');await preview();studio.adopted();
    },b);});
  }
  async function refresh(){
    const check=await request(base+'/model/validate');
    if(!host.isConnected||state.project?.project_id!==pid)return;
    const review=check.geometry_review, boundaries=review?.boundary_faces;
    const details=review?`<p>Honeybee 独立校验：${review.independent_audit?.passed?'通过':'未通过'} · 检查闭合实体、平面性、自交和邻接面积；跨墙厚假设配对 ${num(review.assumed_gap_faces)} 面。</p><p>热容构造 ${review.coverage?.thermal_mass_assemblies?.length??0}/3 类；逐时运行 ${review.coverage?.hourly_operation?'已配置':'未配置'}；推导空间 ${num(review.coverage?.inferred_rooms)} 个；绝热表面积 ${num(review.coverage?.adiabatic_area_m2)} m²。设备口径：${review.coverage?.hvac_scope==='central_chiller_boiler_energy'?'中央冷热源、泵与末端用能':review.coverage?.hvac_scope==='packaged_heat_pump_electricity'?'定容 PTHP 耗电':'理想冷热需求'}；源窗几何 ${review.coverage?.source_window_geometry?'已采用，光学参数仍须核对':'未采用，使用显式窗墙比'}。</p><p>热边界面：外界 ${num(boundaries.Outdoors)}；地面 ${num(boundaries.Ground)}；空间配对 ${num(boundaries.Surface)}；绝热 ${num(boundaries.Adiabatic)}。绝热面不与外界或相邻空间传热。</p><p>本次公差 ${num(review.adjustment.tolerance_m*1000)} mm，实际最大单轴位移 ${num(review.adjustment.max_axis_displacement_m*1000)} mm；逐空间变化记录随 IDF 证据保存。</p>`:'';
    const precision=review?.numerical_precision;
    const precisionNote=precision?`<p>热网格数值精度：最大顶点位移 ${num(precision.max_displacement_m*1e6,3)} µm；${precision.collapsed_faces.length} 个舍入后零面积片已归并。原始空间与边界类别保留，逐空间面积和体积变化随 IDF 证据记录。</p>`:'';
    host.querySelector('#model-gate').innerHTML=`${precisionNote}<p class="${check.can_publish?'':'error-text'}">${check.can_publish?'模型可发布；请核对下列适用范围。':check.blockers.map(esc).join('；')}</p><details><summary>计算范围与简化</summary><ul>${check.limitations.map(l=>'<li>'+esc(l)+'</li>').join('')}</ul>${details}</details>`;
    const history=await request(base+'/model/history');
    if(!host.isConnected||state.project?.project_id!==pid)return;
    host.querySelector('#model-history').textContent=history.map(m=>`v${m.revision} · ${m.status} · ${m.actor} · ${m.updated_at}\n${m.review_note}\n来源：${m.sources.map(s=>s.name+' · SHA256 '+s.hash).join('；')||'人工建模'}`).join('\n\n');
    await refreshRuns();
  }
  async function refreshRuns(){
    const runs=await request(base+'/runs');
    if(!host.isConnected)return;
    host.querySelector('#model-runs').innerHTML=runs.slice(0,5).map(r=>`<p><strong>${esc(r.scheme_id)} · ${esc(r.status)}</strong> ${r.metrics?num(r.metrics.annual_energy_kwh)+' kWh · 按下方能源口径解释':''} ${esc(r.error||'')} ${r.status==='queued'?`<button data-cancel-run="${r.run_id}">取消排队</button>`:''} <a href="/api/runs/${r.run_id}/report.html" target="_blank" rel="noopener">报告与依据 ↗</a></p>${thermalResults(r)}`).join('');
    host.querySelectorAll('[data-cancel-run]').forEach(b=>{b.onclick=()=>action(async()=>{await post(base+'/runs/'+b.dataset.cancelRun+'/cancel',{});await refreshRuns();},b);});
    await onChange(pid);
  }
  host.querySelector('#room-select').onchange=e=>{selected=Number(e.target.value);paintRoom();dispose.select?.(selected);};
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
      const f=await calibration.upload();
      const task=await post(base+'/imports',{...calibration.options(),file_id:f.file_id,mode:form.get('mode'),
        scale_to_m:form.get('scale_to_m')?Number(form.get('scale_to_m')):null,
        height_m:Number(form.get('height_m')),elevation_m:Number(form.get('elevation_m')),
        ifc_origin_m:floorPanel.querySelector('[data-local-origin]')?.checked?ifcOrigin:null,ifc_storey_ids:[...floorPanel.querySelectorAll('[data-storey]:checked')].map(el=>el.value),reconstruct_footprints:form.has('reconstruct_footprints'),reconstruct_elements:form.has('reconstruct_elements'),reconstruction_tolerance_m:Number(form.get('reconstruction_tolerance_m')),source_window_tolerance_m:Number(form.get('source_window_tolerance_m')),page:Number(form.get('page')),layer:form.get('layer')||null,send_to_provider:form.has('send_to_provider')});
      imports.unshift(task);paintImports();if(task.candidate?.rooms.some(r=>r.drawing))await calibration.overlay(task);host.querySelector('#import-progress').textContent='识别完成，请展开任务并合并候选后复核。';studio.imported();
    }catch(error){if(host.isConnected&&state.project?.project_id===pid){host.querySelector('#import-progress').textContent=error.message;try{imports=await request(base+'/imports');if(host.isConnected&&state.project?.project_id===pid)paintImports();}catch{ /* Preserve the original import failure. */ }}throw error;}
  },e.submitter);};
  host.querySelector('#teaching-thermal').onclick=()=>{
    host.querySelectorAll('[data-thermal]').forEach(el=>{el.value=teachingThermal[el.dataset.thermal];});host.querySelector('#thermal-basis').value='assumed_scenario';host.querySelector('#thermal-source').value=teachingThermal.source_note;
    paintOperation({weekday:Array.from({length:24},(_,h)=>h>=8&&h<18?1:0),weekend:Array(24).fill(0),outdoor_air_l_s_person:5,outdoor_air_l_s_m2:.3,sensible_recovery:.6,latent_recovery:0,heating_setback_c:12,cooling_setback_c:32,source_note:'教学假设：工作日 8–18 时；周末无人；新风和热回收仅测试，须替换为项目资料。'});
    for(const [key,depth] of [['wall',.04],['roof',.08],['floor',.05]])constructions[key]=[
      {name:'假设混凝土',thickness_m:.2,conductivity_w_mk:1.4,density_kg_m3:2300,specific_heat_j_kgk:900},
      {name:'假设保温层',thickness_m:depth,conductivity_w_mk:.04,density_kg_m3:40,specific_heat_j_kgk:1400}
    ];paintConstructions();markDirty();
  };
  function body(reviewed){
    const values=[...host.querySelectorAll('[data-thermal]')],hasThermal=values.some(el=>el.value!=='');
    if(hasThermal&&values.some(el=>el.value===''))throw Error('请补齐热工字段，或全部留空仅保存空间模型。');
    if(!hasThermal&&Object.keys(constructions).length)throw Error('已输入构造层，请补齐其余热工参数。');
    const central=centralBody();if(central&&!hasThermal)throw Error('中央系统须同时补齐建筑热工和运行参数，不能忽略已启用的系统。');
    const thermal=hasThermal?{...engineering.thermal(),...Object.fromEntries(values.map(el=>[el.dataset.thermal,Number(el.value)])),constructions,operation:operationBody(),heat_pump:pumpBody(),central_system:central,adjacency_gap_m:Number(host.querySelector('#adjacency-gap').value),basis:host.querySelector('#thermal-basis').value,source_note:host.querySelector('#thermal-source').value,ifc_unpaired_policy:host.querySelector('#ifc-boundary-policy').value,geometry_tolerance_m:Number(host.querySelector('#geometry-tolerance').value)}:null;
    return {...engineering.body(),expected_revision:model?.revision||0,name:host.querySelector('#model-name').value,rooms,thermal,reviewed,review_note:host.querySelector('#model-review').value};
  }
  async function save(reviewed){
    const data=body(reviewed),focus=document.activeElement;
    const workbench=host.querySelector('.model-workbench');
    const headingButtons=[...host.querySelectorAll('.studio-heading-actions button')];
    workbench.inert=true;host.setAttribute('aria-busy','true');headingButtons.forEach(b=>{b.disabled=true;});
    setStatus('正在保存，请等待服务器确认…');
    let saved=false,adopted=false;
    try{
      if(pending){
        if(!reviewed)throw Error('导入工作流需要「确认空间并保存」；候选任务已持久保存，可稍后继续复核。');
        const result=await post(base+'/imports/'+pending+'/review',data);model=result.model;pending=null;adopted=true;
      }else model=await request(base+'/model',{method:'PUT',body:JSON.stringify(data)});
      rooms=structuredClone(model.rooms);dirty=false;markUnsaved(host,false);saved=true;
      if(model.thermal)host.querySelectorAll('[data-thermal]').forEach(el=>{el.value=model.thermal[el.dataset.thermal];});
      setStatus('已保存 v'+model.revision+' · '+model.status);
      if(adopted){imports=await request(base+'/imports');paintImports();}
      await preview();await refresh();
    }catch(error){setStatus((saved?'已保存 v'+model.revision+'，但刷新校验失败：':'保存未确认：')+error.message);throw error;}
    finally{workbench.inert=false;host.removeAttribute('aria-busy');headingButtons.forEach(b=>{b.disabled=false;});if(focus?.isConnected)focus.focus();}
  }
  host.querySelector('#save-model').onclick=e=>action(()=>save(false),e.currentTarget);
  host.querySelector('#review-model').onclick=e=>action(()=>save(true),e.currentTarget);
  host.querySelector('#sync-model-area').onclick=e=>action(async()=>{if(!model)throw Error('先保存模型');const updated=await post(base+'/model/sync-area',{revision:model.revision});if(!host.isConnected||state.project?.project_id!==pid)return;state.project=updated;await refresh();notice('项目面积已同步；已有计算会重新核验版本。');},e.currentTarget);
  host.querySelector('#publish-model').onclick=e=>action(async()=>{if(!model||dirty)throw Error('请先保存当前编辑');const result=await post(base+'/model/publish',{revision:model.revision,scheme_id:host.querySelector('#model-scheme').value,responsible_person:state.user.display_name,review_note:host.querySelector('#publish-note').value});const [evidence,gate]=await Promise.all([request(base+'/evidence'),request(base+'/gate')]);if(!host.isConnected||state.project?.project_id!==pid)return;state.evidence=evidence;state.gate=gate;notice(result.reused?'已存在此模型对应的有效 IDF':'IDF 已生成并登记；请确认天气后运行。');await refresh();},e.currentTarget);
  host.querySelector('#run-model').onclick=e=>action(async()=>{if(dirty)throw Error('请先保存当前编辑并发布，再提交计算');await post(base+'/model-runs',{scheme_id:host.querySelector('#model-scheme').value});notice('已提交真实 EnergyPlus 队列');await refreshRuns();},e.currentTarget);
  host.querySelector('#model-api').onclick=()=>projectTokens(pid,host,action,notice);
  host.reviewFocus=id=>{
    const index=rooms.findIndex(r=>r.id===id);if(index<0){notice('此空间已不在当前模型，请刷新工程复核清单。',true);return;}
    const floor=host.querySelector('[data-storey-filter]');floor.value='';dispose.filterStorey?.('');
    selected=index;host.querySelector('#room-select').value=String(index);paintRoom();dispose.select?.(index);
    host.querySelector('[data-property="space"]').click();delete state.reviewRoomId;
  };
  paintImports();await preview();if(state.reviewRoomId)host.reviewFocus(state.reviewRoomId);setStatus(model?'已读取保存版本 v'+model.revision+' · 未保存的编辑不会参与计算':'尚未保存模型 · 先导入资料或添加空间');await refresh();
  const timer=setInterval(()=>{if(!host.isConnected){clearInterval(timer);dispose();return;}if(!document.hidden&&!document.querySelector('.reauth-dialog[open]'))action(refreshRuns);},4000);
}

async function renderBuilding(rooms,host,onPick){
  const target=host.querySelector('#building-canvas'), plan=host.querySelector('#model-plan');
  target.innerHTML='';plan.innerHTML='';
  if(!rooms.length){target.innerHTML='<p class="empty">导入或添加房间，开始建立模型。</p>';return ()=>{};}
  const points=rooms.flatMap(r=>roomSegments(r).flatMap(s=>s.polygon)),minX=Math.min(...points.map(p=>p[0])),minY=Math.min(...points.map(p=>p[1]));
  const maxX=Math.max(...points.map(p=>p[0])),maxY=Math.max(...points.map(p=>p[1]));
  plan.innerHTML=`<svg viewBox="${minX-1} ${minY-1} ${maxX-minX+2} ${maxY-minY+2}" role="img" aria-label="房间平面轮廓">${rooms.map((r,i)=>`<path data-pick="${i}" fill-rule="evenodd" d="${[r.polygon,...(r.holes||[])].map(ring=>'M'+ring.map(p=>p.join(',')).join('L')+'Z').join(' ')}"><title>${esc(r.name)} · ${num(roomArea(r))} m² · ${r.holes?.length||0} 个孔洞</title></path>`).join('')}</svg>`;
  plan.querySelectorAll('[data-pick]').forEach(p=>{p.onclick=()=>onPick(Number(p.dataset.pick));});
  const selectPlan=index=>plan.querySelectorAll('[data-pick]').forEach(p=>p.classList.toggle('selected',Number(p.dataset.pick)===index));
  try{
    const THREE=await import('three'),{OrbitControls}=await import('three/addons/controls/OrbitControls.js');
    if(!host.isConnected)return ()=>{};
    const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));target.append(renderer.domElement);
    const scene=new THREE.Scene();scene.background=new THREE.Color('#edf2f6');
    const camera=new THREE.PerspectiveCamera(42,1,.05,10000),controls=new OrbitControls(camera,renderer.domElement);
    scene.add(new THREE.HemisphereLight(0xffffff,0x667d91,2.5));
    const sun=new THREE.DirectionalLight(0xffffff,2);sun.position.set(20,40,10);scene.add(sun);
    const meshes=rooms.flatMap((r,i)=>{const bases=r.shell?.length?[new THREE.Mesh(shellGeometry(r.shell,THREE),new THREE.MeshStandardMaterial({color:0x91a9b7,roughness:.75,transparent:true,opacity:.85,side:THREE.DoubleSide}))]:roomSegments(r).map(segment=>{
      const shape=new THREE.Shape(segment.polygon.map(([x,y])=>new THREE.Vector2(x,-y)));
      (segment.holes||(!r.segments?.length?r.holes:[])||[]).forEach(ring=>shape.holes.push(new THREE.Path(ring.map(([x,y])=>new THREE.Vector2(x,-y)))));
      const mesh=new THREE.Mesh(new THREE.ExtrudeGeometry(shape,{depth:segment.height_m,bevelEnabled:false}),
        new THREE.MeshStandardMaterial({color:new THREE.Color().setHSL(.56+i*.011,.35,.55),roughness:.75,transparent:true,opacity:.85}));
      mesh.rotation.x=-Math.PI/2;mesh.position.y=segment.elevation_m;mesh.userData.index=i;scene.add(mesh);
      const edges=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry),new THREE.LineBasicMaterial({color:0x32566d}));
      mesh.add(edges);return mesh;
    });const windows=(r.source_openings||[]).map(opening=>{const mesh=new THREE.Mesh(shellGeometry([opening],THREE),new THREE.MeshStandardMaterial({color:0x2b79ba,transparent:true,opacity:.75,side:THREE.DoubleSide}));mesh.userData.sourceWindow=true;return mesh;});return [...bases,...windows].map(mesh=>{mesh.userData.index=i;mesh.userData.storey=storeyKey(r);if(!mesh.parent)scene.add(mesh);return mesh;});});
    const bounds=new THREE.Box3();meshes.forEach(m=>bounds.expandByObject(m));const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3()),span=Math.max(size.x,size.y,size.z,5);
    const fit=()=>{const active=new THREE.Box3();meshes.filter(m=>m.visible).forEach(m=>active.expandByObject(m));if(active.isEmpty())return;const c=active.getCenter(new THREE.Vector3()),s=active.getSize(new THREE.Vector3());camera.position.copy(c).add(new THREE.Vector3(1,.85,1).normalize().multiplyScalar(Math.max(s.length(),5)/2/Math.sin(THREE.MathUtils.degToRad(camera.fov/2))*1.05/Math.min(1,camera.aspect)));controls.target.copy(c);controls.update();};fit();
    const grid=new THREE.GridHelper(span*2,20,0xaebdca,0xd4dee6);grid.position.set(center.x,bounds.min.y-.02,center.z);scene.add(grid);
    const canvasTheme=()=>{const dark=document.documentElement.dataset.theme==='dark';scene.background.set(dark?'#192534':'#edf2f6');grid.material.color.set(dark?'#667b96':'#ffffff');};
    canvasTheme();const themeObserver=new MutationObserver(canvasTheme);themeObserver.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
    const resize=()=>{const width=Math.max(target.clientWidth,200);const height=Math.max(target.clientHeight,1);renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();fit();};
    const observer=new ResizeObserver(resize);observer.observe(target);resize();
    host.querySelector('#model-xray').onchange=e=>{meshes.forEach(m=>{m.material.opacity=e.target.checked?.25:.85;m.material.depthWrite=!e.target.checked;});};
    let down;
    renderer.domElement.onpointerdown=e=>{down=[e.clientX,e.clientY];};
    renderer.domElement.onpointerup=e=>{if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),camera);const hit=ray.intersectObjects(meshes.filter(m=>m.visible),false)[0];if(hit)onPick(hit.object.userData.index);};
    let alive=true;
    const dispose=()=>{if(!alive)return;alive=false;observer.disconnect();themeObserver.disconnect();controls.dispose();scene.traverse(o=>{o.geometry?.dispose();if(o.material){if(Array.isArray(o.material))o.material.forEach(m=>m.dispose());else o.material.dispose();}});renderer.dispose();};
    dispose.filterStorey=key=>{meshes.forEach(m=>{m.visible=!key||m.userData.storey===key;});plan.querySelectorAll('[data-pick]').forEach(p=>{p.style.display=!key||storeyKey(rooms[Number(p.dataset.pick)])===key?'':'none';});fit();};dispose.fit=fit;dispose.select=index=>{meshes.forEach(m=>{m.material.color.set(m.userData.sourceWindow?'#2b79ba':m.userData.index===index?'#4f81cd':new THREE.Color().setHSL(.57+m.userData.index*.005,.17,.68));});selectPlan(index);};
    function frame(){if(!alive)return;if(!host.isConnected){dispose();return;}if(!document.hidden&&!host.hidden)renderer.render(scene,camera);requestAnimationFrame(frame);}frame();return dispose;
  }catch(error){target.textContent='三维渲染不可用，可使用下方二维轮廓与尺寸编辑。'+error.message;const fallback=()=>{};fallback.select=selectPlan;return fallback;}
}
