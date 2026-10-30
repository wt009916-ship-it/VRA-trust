import {request,post,escape as esc} from './api.js';

const parameters=[['chiller_cop','冷水机组额定COP'],['boiler_efficiency','锅炉效率'],['chilled_water_c','冷冻水供水 °C'],['chilled_water_delta_c','冷冻水设计温差 K'],['hot_water_c','热水供水 °C'],['hot_water_delta_c','热水设计温差 K'],['chilled_pump_head_pa','冷冻水泵压头 Pa'],['hot_pump_head_pa','热水泵压头 Pa'],['condenser_pump_head_pa','冷却水泵压头 Pa（水冷必填）'],['fan_pressure_pa','末端风机压升 Pa'],['fan_total_efficiency','末端风机总效率'],['fan_motor_efficiency','末端电机效率']];
const dayFields=[['month','月'],['day','日'],['dry_bulb_c','干球 °C'],['daily_range_c','日较差 K'],['wet_bulb_c','湿球 °C'],['pressure_pa','气压 Pa'],['wind_speed_m_s','风速 m/s'],['wind_direction_deg','风向 °'],['sky_clearness','晴空系数']];

export function centralDesignDays(system){
  return system?.design_days?.length?structuredClone(system.design_days):[{kind:'winter'},{kind:'summer'}];
}

export function centralSystemInputs(host,{base,model,action,markDirty,notice}){
  let source={source_file_id:model?.thermal?.central_system?.source_file_id||null,source_file_hash:model?.thermal?.central_system?.source_file_hash||null};
  const panel=document.createElement('details');panel.className='model-card central-system-panel';
  panel.innerHTML='<summary>中央冷热源、水泵与风机盘管</summary><label class="check-option"><input data-central-enabled type="checkbox">采用四管制风机盘管与中央水系统</label><p>末端 → 冷冻水泵 / 热水泵 → 冷水机组 / 锅炉；水冷机组另带冷却水泵和冷却塔。按显式冬夏设计日计算末端与水流量，保留原生展开、选型和实际分项用能。不自动恢复管路压损、热损或高楼水力分区。</p><label>导入中央系统设计JSON<input data-central-file type="file" accept=".json"></label><button type="button" data-central-import>读取设计参数及来源</button><div data-central-source></div><div data-central-fields></div>';
  host.querySelector('#adjacency-gap').closest('label').after(panel);
  const input=(key,label,value,optional=false)=>`<label>${label}${optional?' · 可留空':' · 必填'}<input data-central="${key}" type="number" step="any" value="${esc(value??'')}"></label>`;
  function paint(p){
    panel.querySelector('[data-central-enabled]').checked=!!p;
    panel.querySelector('[data-central-fields]').innerHTML=`<label>输入性质<select data-central="basis"><option value="design_scenario">明确设计情景</option><option value="documented_design">绑定文件的设计依据</option></select></label><label>冷凝方式<select data-central="condenser"><option value="AirCooled">风冷冷水机组</option><option value="WaterCooled">水冷冷水机组 + 冷却塔</option></select></label><label>锅炉能源<select data-central="boiler_fuel"><option value="NaturalGas">天然气</option><option value="Electricity">电</option></select></label><div class="form-grid">${parameters.map(([key,label])=>input(key,label,p?.[key],key==='condenser_pump_head_pa')).join('')}${input('chiller_capacity_w','冷水机组容量 W',p?.chiller_capacity_w,true)}${input('boiler_capacity_w','锅炉容量 W',p?.boiler_capacity_w,true)}</div><p class="subtle">冷热源容量留空表示明确选择设计日自动选型；不代表已安装铭牌。通用参考性能曲线始终保留为假设。</p>${centralDesignDays(p).map((d,index)=>{const kind=d.kind;return `<fieldset data-design-day="${kind}"><legend>${kind==='summer'?'夏季':'冬季'}设计日 ${index+1} · 全部必填</legend><div class="form-grid">${dayFields.map(([key,label])=>`<label>${label}<input data-day="${key}" type="number" step="any" value="${esc(d?.[key]??'')}"></label>`).join('')}</div></fieldset>`;}).join('')}<label>设计日、设备和运行范围依据 · 至少10字符<textarea data-central="source_note" minlength="10">${esc(p?.source_note||'')}</textarea></label>`;
    for(const key of ['basis','condenser','boiler_fuel'])if(p?.[key])panel.querySelector(`[data-central="${key}"]`).value=p[key];
    panel.querySelector('[data-central-source]').textContent=source.source_file_id?'已绑定项目原件 '+source.source_file_id+' · SHA256 '+source.source_file_hash:'尚无设计原件绑定；仅可记录为明确设计情景。';
    panel.querySelectorAll('[data-central],[data-day]').forEach(el=>el.oninput=markDirty);
  }
  paint(model?.thermal?.central_system);
  panel.querySelector('[data-central-enabled]').onchange=()=>{if(panel.querySelector('[data-central-enabled]').checked)host.querySelector('#pump-enabled').checked=false;markDirty();};
  panel.querySelector('[data-central-import]').onclick=e=>action(async()=>{
    const file=panel.querySelector('[data-central-file]').files[0];if(!file)throw Error('请选择完整的中央系统设计JSON记录');
    const data=new FormData();data.set('file',file);const record=await request(base+'/files',{method:'POST',body:data});
    const result=await post(base+'/model/central-import',{file_id:record.file_id});
    source={source_file_id:record.file_id,source_file_hash:record.hash};paint(result.central_system);host.querySelector('#pump-enabled').checked=false;markDirty();notice('已读取设计记录；请核对运行档案并清除冲突的独立PTHP清单后保存。');
  },e.currentTarget);
  return ()=>{
    if(!panel.querySelector('[data-central-enabled]').checked)return null;
    const result={kind:'four_pipe_fan_coil',curve_basis:'native_reference',...source};
    for(const el of panel.querySelectorAll('[data-central]')){
      const key=el.dataset.central,optional=['condenser_pump_head_pa','chiller_capacity_w','boiler_capacity_w'].includes(key);
      if(!optional&&!el.value.trim())throw Error('中央系统参数和来源须填齐；可从设计JSON一次导入。');
      result[key]=el.type==='number'?(el.value===''?null:Number(el.value)):el.value;
    }
    if(result.source_note.trim().length<10)throw Error('中央系统来源依据须至少10字符');
    result.design_days=[...panel.querySelectorAll('[data-design-day]')].map(row=>({kind:row.dataset.designDay,...Object.fromEntries([...row.querySelectorAll('[data-day]')].map(el=>{if(el.value==='')throw Error('冬夏设计日各项必须有依据，不能用空白替代0');return [el.dataset.day,Number(el.value)];}))}));
    return result;
  };
}
