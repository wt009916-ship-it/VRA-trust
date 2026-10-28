import {request,post,escape as esc,number as num} from './api.js';

export function plantCalibrationPanel(anchor,{base,action}){
  const panel=document.createElement('details');panel.className='model-card';
  const select=(name,label,values=[])=>`<label>${label} · 必填<select name="${name}" required><option value="">请选择</option>${values.map(([value,text])=>`<option value="${value}">${text}</option>`).join('')}</select></label>`;
  const columns=[['timestamp','时间'],['power','电功率'],['cooling','冷量功率'],['flow','蒸发器流量'],['return_temperature','回水温度'],['supply_temperature','供水温度'],['condenser_temperature','冷凝器进水温度']];
  panel.innerHTML=`<summary>中央冷站 · 水侧平衡与工况拟合</summary><p>用同一设备、同一时刻的冷量、流量、温差和电功率检查能量平衡，再按时间留出拟合功率。全部异常行保留。工况拟合需工程师复核，尚不签发现场校准通过证明或替换全年热模型。</p><label>同步工况CSV · UTF-8、最大20MB<input data-file type="file" accept=".csv"></label><button data-read type="button">上传并读取工况列</button><form data-fit hidden><div class="form-grid"><label>建筑标识 · 必填<input name="building_ref" required maxlength="200"></label><label>设备或系统标识 · 必填<input name="equipment_ref" required maxlength="200"></label>
  ${select('boundary','电表边界',[['chiller_electricity','单冷机（不含泵、塔）'],['chiller_train_electricity','单机组及所属泵塔电功率'],['plant_electricity','全冷站总电（含全部机组、泵、塔）']])}${select('source_nature','数据来源',[['field_raw','现场原始计量'],['field_processed','现场记录经来源方处理'],['laboratory','实验台'],['simulation','模拟数据']])}
  ${columns.map(([key,label])=>select(key+'_column',label)).join('')}
  ${select('power_unit','电功率单位',[['W','W'],['kW','kW']])}${select('cooling_unit','冷量功率单位',[['W','W'],['kW','kW'],['refrigeration_ton','美制冷吨（不是文件列名Tons的默认含义）']])}${select('flow_unit','体积流量单位',[['m3/s','m³/s'],['m3/h','m³/h'],['L/s','L/s'],['US_gpm','美制加仑/分钟']])}${select('temperature_unit','全部温度列单位',[['C','℃'],['K','K'],['F','℉']])}
  <label>时间间隔秒数 · 必填<input name="interval_seconds" type="number" required min="60" max="86400"></label><label>无时区时间的固定UTC偏移（分钟）<input name="utc_offset_minutes" type="number" min="-720" max="840" placeholder="已有时区可留空"></label><label>留出期起点 · 必填<input name="holdout_start" required placeholder="2025-07-01T00:00:00+08:00"></label><label>流体密度 kg/m³ · 必填<input name="fluid_density_kg_m3" type="number" step="any" required min="900" max="1300"></label><label>比热 J/(kg·K) · 必填<input name="fluid_heat_capacity_j_kgk" type="number" step="any" required min="2000" max="4500"></label><label>水侧平衡允许误差 % · 必填<input name="balance_tolerance_percent" type="number" step="any" required min="0.01" max="30"></label></div><label>计量边界、单位、时区、流体物性及允许误差依据 · 至少20字<textarea name="source_note" minlength="20" maxlength="4000" required></textarea></label><button>检查并拟合 · 保留失败</button></form><p data-status role="status"></p><div data-results></div>`;
  anchor.after(panel);let source=null;
  async function refresh(){
    const rows=await request(base+'/calibrations');if(!panel.isConnected)return;
    panel.querySelector('[data-results]').innerHTML=rows.length?rows.map(r=>`<article><h3>${esc(r.options.equipment_ref)} · ${r.result.status==='blocked'?'存在阻断':'拟合候选，待工程复核'}</h3><p>${r.result.valid_operating_rows}/${r.result.rows}个有效工况 · 水侧不平衡 ${r.result.balance_failed_rows} 行 · 插补 ${r.result.imputed_rows} 行</p>${r.result.blockers.map(b=>`<p class="error">${esc(b)}</p>`).join('')}${r.result.fit?`<table><thead><tr><th>时段</th><th>工况数</th><th>NMBE</th><th>CVRMSE</th></tr></thead><tbody>${[['训练',r.result.fit.training],['留出',r.result.fit.holdout]].map(([name,m])=>`<tr><td>${name}</td><td>${m.n}</td><td>${num(m.nmbe_percent)}%</td><td>${num(m.cvrmse_percent)}%</td></tr>`).join('')}</tbody></table>`:''}<details><summary>原件、参数、全部检查及适用范围</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details><button data-rows="${esc(r.calibration_id)}" type="button">查看前100行审计</button><div data-audit="${esc(r.calibration_id)}"></div></article>`).join(''):'<p>尚无冷站工况记录。不会用示例代替你的现场数据。</p>';
    panel.querySelectorAll('[data-rows]').forEach(b=>b.onclick=()=>action(async()=>{const r=await request(base+'/calibrations/'+b.dataset.rows+'/rows');if(!panel.isConnected)return;panel.querySelector(`[data-audit="${b.dataset.rows}"]`).innerHTML='<pre>'+esc(JSON.stringify(r,null,2))+'</pre>';},b));
  }
  panel.addEventListener('toggle',()=>{if(panel.open)action(refresh);});
  panel.querySelector('[data-file]').onchange=()=>{source=null;panel.querySelector('[data-fit]').hidden=true;};
  panel.querySelector('[data-read]').onclick=e=>action(async()=>{
    const f=panel.querySelector('[data-file]').files[0];if(!f||f.size>20_000_000)throw Error('请选择20MB以内CSV');const body=new FormData();body.set('file',f);
    source=await request(base+'/files',{method:'POST',body});const r=await request(base+'/measurements/columns/'+source.file_id);if(!panel.isConnected)return;
    columns.forEach(([key])=>{panel.querySelector(`[name="${key}_column"]`).innerHTML='<option value="">选择来源列</option>'+r.columns.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');});panel.querySelector('[data-fit]').hidden=false;
  },e.currentTarget);
  panel.querySelector('[data-fit]').onsubmit=e=>{e.preventDefault();action(async()=>{
    if(!source)throw Error('请重新上传原件');const body=Object.fromEntries(new FormData(e.target));body.file_id=source.file_id;
    for(const key of ['interval_seconds','fluid_density_kg_m3','fluid_heat_capacity_j_kgk','balance_tolerance_percent'])body[key]=Number(body[key]);body.utc_offset_minutes=body.utc_offset_minutes===''?null:Number(body.utc_offset_minutes);
    const r=await post(base+'/calibrations',body);await refresh();if(panel.isConnected)panel.querySelector('[data-status]').textContent='记录已保存：'+(r.result.status==='blocked'?'存在阻断，请核对原件、单位或计量。':'拟合候选生成，仍需现场及工程复核。');
  },e.submitter);};
  return panel;
}
