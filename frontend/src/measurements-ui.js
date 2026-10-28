import {request,post,escape as esc,number as num} from './api.js';
import {plantCalibrationPanel} from './plant-calibration-ui.js';

export function measurementPanel(anchor,{base,action}){
  const panel=document.createElement('details');panel.className='model-card measurement-panel';
  const select=(name,label,choices)=>`<label>${label}<select name="${name}" required><option value="">请选择</option>${choices.map(([key,text])=>`<option value="${key}">${text}</option>`).join('')}</select></label>`;
  panel.innerHTML=`<summary>现场计量 · 原件检查与留出期误差</summary><p>导入固定间隔CSV。缺测、重复、时间缺口均保留，不补零、不把全楼电表当作冷机电表。此处检查数据和预测误差，尚不拟合物理模型或签发校准通过。</p><label>原件CSV · 最大20MB<input data-file type="file" accept=".csv"></label><button data-read type="button">上传并读取列名</button><form data-import hidden><div class="form-grid">
  <label>建筑唯一标识 · 必填<input name="building_ref" required maxlength="200"></label><label>计量边界 · 必填<input name="meter_boundary" required minlength="3" maxlength="300" placeholder="例如冷站总电表（含冷机、泵、塔）"></label>
  ${select('role','序列性质',[['observed','有来源的观测记录'],['prediction','预测结果']])}${select('quantity','计量对象',[['electricity','电能'],['gas','燃气能量'],['heating','供热量'],['cooling','供冷量']])}
  ${select('timestamp_column','时间列',[])}${select('value_column','计量列',[])}${select('unit','单位与数据含义',[['kWh','kWh · 间隔能量，非累计表底'],['Wh','Wh · 间隔能量，非累计表底'],['kW','kW · 间隔平均功率'],['W','W · 间隔平均功率']])}
  <label>间隔秒数 · 必填<input name="interval_seconds" type="number" min="60" max="86400" required placeholder="逐时3600"></label><label>无时区时间的固定UTC偏移 · 分钟<input name="utc_offset_minutes" type="number" min="-720" max="840" placeholder="有时区时间留空；北京时间480"></label></div><label>原件、单位、传感器及时间依据 · 至少10字<textarea name="source_note" required minlength="10" maxlength="2000"></textarea></label><button>检查并保存分析</button></form><div data-history></div>
  <details><summary>与预测序列比较，分开核对训练期和留出期</summary><form data-compare><div class="form-grid">${select('observed_id','观测序列',[])}${select('prediction_id','预测序列',[])}<label>留出期起点 · 带时区ISO时间<input name="holdout_start" required placeholder="2025-10-01T00:00:00+08:00"></label><label>训练期拟合参数个数<input name="fitted_parameters" type="number" min="0" max="50" value="0" required></label></div><label>预测模型与时段划分依据 · 至少10字<textarea name="source_note" required minlength="10" maxlength="2000"></textarea></label><button>计算误差</button></form><div data-result role="status"></div></details><p data-status role="status"></p>`;
  anchor.after(panel);let source=null;
  async function refresh(){
    const [history,comparisons]=await Promise.all([request(base+'/measurements'),request(base+'/measurements/comparisons')]);if(!panel.isConnected)return;
    panel.querySelector('[data-history]').innerHTML=history.length?`<h3>计量记录 · ${history.length} 条</h3>${history.map(r=>`<article><strong>${esc(r.options.building_ref)} · ${esc(r.options.value_column)}</strong><p>${esc(r.options.meter_boundary)} · ${r.summary.valid_rows}/${r.summary.rows}行有效 · ${r.summary.eligible_for_comparison?'时间与数值检查通过':'数据问题阻止误差计算'}</p><p>有效行能量 ${num(r.summary.valid_observed_energy_kwh)} kWh；有缺测时并非完整时段总量。</p><details><summary>原件、问题与时间范围</summary><pre>${esc(JSON.stringify({source:r.source,options:r.options,summary:r.summary},null,2))}</pre></details></article>`).join('')}`:'<p>尚无计量分析。</p>';
    for(const [name,role] of [['observed_id','observed'],['prediction_id','prediction']])panel.querySelector(`[name="${name}"]`).innerHTML='<option value="">请选择同口径序列</option>'+history.filter(r=>r.options.role===role).map(r=>`<option value="${esc(r.measurement_id)}">${esc(r.options.building_ref+' / '+r.options.value_column+' / '+r.measurement_id.slice(-6))}</option>`).join('');
    panel.querySelector('[data-result]').innerHTML=comparisons.map(r=>`<details><summary>历史计算 · ${esc(r.created_at)} · 留出期CVRMSE ${num(r.holdout.cvrmse_percent)}%</summary><pre>${esc(JSON.stringify({sources:[r.observed_source,r.prediction_source],options:r.options,training:r.training,holdout:r.holdout,calibrated:false},null,2))}</pre></details>`).join('');
  }
  panel.addEventListener('toggle',()=>{if(panel.open)action(refresh);});
  panel.querySelector('[data-read]').onclick=e=>action(async()=>{
    const file=panel.querySelector('[data-file]').files[0];if(!file)throw Error('请选择CSV原件');if(file.size>20_000_000)throw Error('请按建筑/设备拆分为20MB以内CSV');
    const body=new FormData();body.set('file',file);source=await request(base+'/files',{method:'POST',body});
    const result=await request(base+'/measurements/columns/'+source.file_id);if(!panel.isConnected)return;
    for(const name of ['timestamp_column','value_column'])panel.querySelector(`[name="${name}"]`).innerHTML='<option value="">请选择原件列名</option>'+result.columns.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');
    panel.querySelector('[data-import]').hidden=false;panel.querySelector('[data-status]').textContent='已绑定原件 '+source.name+'；请核对字段与计量口径。';
  },e.currentTarget);
  panel.querySelector('[data-file]').onchange=()=>{source=null;panel.querySelector('[data-import]').hidden=true;};
  panel.querySelector('[data-import]').onsubmit=e=>{e.preventDefault();action(async()=>{
    if(!source)throw Error('请先上传原件');const body=Object.fromEntries(new FormData(e.target));body.file_id=source.file_id;body.interval_seconds=Number(body.interval_seconds);body.utc_offset_minutes=body.utc_offset_minutes===''?null:Number(body.utc_offset_minutes);
    const r=await post(base+'/measurements',body);await refresh();if(panel.isConnected)panel.querySelector('[data-status]').textContent=r.summary.eligible_for_comparison?'数据检查通过，仍须核对计量边界和传感器。':'已保存问题记录；未自动修补缺测。';
  },e.submitter);};
  panel.querySelector('[data-compare]').onsubmit=e=>{e.preventDefault();action(async()=>{
    const body=Object.fromEntries(new FormData(e.target));body.fitted_parameters=Number(body.fitted_parameters);const r=await post(base+'/measurements/compare',body);if(!panel.isConnected)return;
    panel.querySelector('[data-result]').innerHTML=`<table><thead><tr><th>时段</th><th>样本</th><th>NMBE</th><th>CVRMSE</th></tr></thead><tbody>${[['训练期',r.training],['留出期',r.holdout]].map(([name,m])=>`<tr><td>${name}</td><td>${m.n}</td><td>${num(m.nmbe_percent)}%</td><td>${num(m.cvrmse_percent)}%</td></tr>`).join('')}</tbody></table><p>正偏差表示预测偏高。完整时间戳一一对应；导入序列误差不证明原生热模型已现场校准。</p>`;
  },e.submitter);};
}

export function measurementWorkspace(state,host,action){
  host.innerHTML='<div class="view-heading"><div><span class="eyebrow">METER DATA &amp; VALIDATION</span><h1>计量与验证</h1><p>先核对原始计量，再检验预测。可在尚未建立几何模型时独立使用。</p></div></div>';
  measurementPanel(host.firstElementChild,{base:'/projects/'+state.project.project_id,action});
  host.querySelector('.measurement-panel').open=true;
  plantCalibrationPanel(host.lastElementChild,{base:'/projects/'+state.project.project_id,action});
}
