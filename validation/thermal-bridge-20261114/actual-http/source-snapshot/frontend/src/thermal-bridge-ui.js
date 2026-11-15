import {request,post,escape as esc} from './api.js';
import {nullableNumber,geometryMarkup,resultMarkup,drawTemperature,statusText,sideText} from './thermal-bridge-view.js';

const numeric=(name,label,value='',extra='')=>`<label>${label}<input name="${name}" type="number" step="any" value="${esc(value??'')}" ${extra}></label>`;
const text=(name,label,value='',max=1000)=>`<label>${label}<input name="${name}" value="${esc(value)}" required minlength="${name==='name'||name==='section_name'?1:3}" maxlength="${max}"></label>`;
const select=(name,options,value)=>`<select name="${name}">${options.map(([v,t])=>`<option value="${v}" ${value===v?'selected':''}>${t}</option>`).join('')}</select>`;
const regionRow=r=>`<fieldset data-region><legend>矩形材料区</legend><div class="form-grid">${text('name','名称',r.name||'',100)}${numeric('x0','x 起点',r.x0,'required min="0"')}${numeric('x1','x 终点',r.x1,'required min="0"')}${numeric('y0','y 起点',r.y0,'required min="0"')}${numeric('y1','y 终点',r.y1,'required min="0"')}${numeric('conductivity','导热系数 λ（未知留空）',r.conductivity,'min="0.000001"')}<label>λ 单位${select('conductivity_unit',[['W/(m K)','W/(m K)'],['mW/(m K)','mW/(m K)']],r.conductivity_unit)}</label></div>${text('source','材料数据来源、版本及适用状态',r.source||'')}<button type="button" data-remove-region>移除此区</button></fieldset>`;

export async function thermalBridgeWorkspace(state,host,action){
  const base='/projects/'+state.project.project_id+'/thermal-bridges';
  host.classList.add('thermal-bridge');
  host.innerHTML=`<h2>二维截面稳态导热</h2><p>定义矩形截面的材料分区及四边工况，查看温度场和单位延伸长度热流。无热源、恒定各向同性材料；不计算 ψ、结露或合规结论。</p>
    <form data-section-form><div class="form-grid">${text('section_name','计算名称','',160)}<label>截面坐标单位${select('length_unit',[['mm','mm'],['cm','cm'],['m','m']],'mm')}</label>${numeric('width','截面宽度（x）','','required min="0.000001"')}${numeric('height','截面高度（y）','','required min="0.000001"')}${numeric('cell_size','初始最大网格边长（同坐标单位）','','required min="0.000001"')}</div>
    <p>自动追加一遍半网格计算；最多 160000 单元／网格、25 秒求解预算。请按材料最薄尺寸选择网格，超限会拒绝计算。</p>${text('geometry_source','截面几何来源与坐标说明','',2000)}${text('application','适用工况、材料状态和用途','',2000)}
    <div data-regions></div><button type="button" data-add-region>＋ 材料分区</button><div data-geometry></div>
    <h3>四边工况</h3><p>固定温度指表面温度；换热边界填写空气温度和表面热阻，不能混用。温度为 °C，热阻为 m²K/W。</p><div data-boundaries></div>
    <details><summary>指定取温位置（可选，最多 50 个）</summary><div data-probes></div><button type="button" data-add-probe>＋ 取温点</button></details>
    <label>关联项目证据（可多选）<select name="evidence_ids" multiple size="4">${state.evidence.map(e=>`<option value="${esc(e.evidence_id)}" ${e.review_state==='rejected'?'disabled':''}>${esc(e.name)} · ${esc(e.status)}</option>`).join('')}</select></label><p>来源仅作追溯；上传或人工确认不自动证明材料、尺寸和边界真实。</p>
    <button type="submit" class="primary">计算并保存二维记录</button></form>
    <details><summary>读取已有截面输入</summary><p>读取本工具输入 JSON 或历史完整 JSON；只填充表单，不自动计算，也不改变来源状态。</p><input data-import type="file" accept=".json,application/json"></details>
    <section data-result aria-live="polite"></section><h3>二维计算历史</h3><div data-history></div><button type="button" data-more hidden>更多记录</button>`;
  const form=host.querySelector('form'),regions=host.querySelector('[data-regions]'),boundaries=host.querySelector('[data-boundaries]'),probes=host.querySelector('[data-probes]');
  const value=(el,name)=>el.querySelector(`[name="${name}"]`).value;
  function addRegion(r={}){if(regions.children.length>=32)throw new Error('最多 32 个材料区');regions.insertAdjacentHTML('beforeend',regionRow(r));const row=regions.lastElementChild;row.querySelector('button').onclick=()=>{row.remove();preview();};}
  function addProbe(p={}){if(probes.children.length>=50)throw new Error('最多 50 个取温点');probes.insertAdjacentHTML('beforeend',`<fieldset><div class="form-grid">${text('name','位置名称',p.name||'',60)}${numeric('x','x 坐标',p.x,'required min="0"')}${numeric('y','y 坐标',p.y,'required min="0"')}</div><button type="button">移除取温点</button></fieldset>`);const row=probes.lastElementChild;row.querySelector('button').onclick=()=>row.remove();}
  function setBoundaries(input={}){boundaries.innerHTML=Object.entries(sideText).map(([side,title])=>{const b=input[side]||{};return `<fieldset data-side="${side}"><legend>${title}</legend><div class="form-grid"><label>边界类型${select('mode',[['adiabatic','绝热（热流为零）'],['fixed_temperature','固定表面温度'],['film','空气温度及表面热阻']],b.mode||'adiabatic')}</label>${numeric('temperature_c','温度 °C（未知留空）',b.temperature_c,'min="-100" max="200"')}${numeric('resistance_m2k_w','表面热阻 m²K/W（未知留空）',b.resistance_m2k_w,'min="0.000001" max="10"')}</div>${text('basis','该边界工况及取值依据',b.basis||'')}</fieldset>`;}).join('');for(const row of boundaries.children){const mode=row.querySelector('[name=mode]');function update(){row.querySelector('[name=temperature_c]').closest('label').hidden=mode.value==='adiabatic';row.querySelector('[name=resistance_m2k_w]').closest('label').hidden=mode.value!=='film';}mode.onchange=update;update();}}
  function input(){const f=new FormData(form);return {name:f.get('section_name'),width:nullableNumber(f.get('width')),height:nullableNumber(f.get('height')),length_unit:f.get('length_unit'),cell_size:nullableNumber(f.get('cell_size')),geometry_source:f.get('geometry_source'),application:f.get('application'),
    regions:[...regions.children].map(row=>Object.fromEntries(['name','x0','x1','y0','y1','conductivity','conductivity_unit','source'].map(k=>[k,['x0','x1','y0','y1','conductivity'].includes(k)?nullableNumber(value(row,k)):value(row,k)]))),
    boundaries:Object.fromEntries([...boundaries.children].map(row=>{const mode=value(row,'mode');return [row.dataset.side,{mode,basis:value(row,'basis'),temperature_c:mode==='adiabatic'?null:nullableNumber(value(row,'temperature_c')),resistance_m2k_w:mode==='film'?nullableNumber(value(row,'resistance_m2k_w')):null}];})),
    probes:[...probes.children].map(row=>({name:value(row,'name'),x:nullableNumber(value(row,'x')),y:nullableNumber(value(row,'y'))})),evidence_ids:f.getAll('evidence_ids')};}
  function preview(){host.querySelector('[data-geometry]').innerHTML=geometryMarkup(input());}
  addRegion();setBoundaries();preview();
  host.querySelector('[data-add-region]').onclick=()=>action(async()=>addRegion());
  host.querySelector('[data-add-probe]').onclick=()=>action(async()=>addProbe());
  form.addEventListener('input',preview);
  function render(record){const target=host.querySelector('[data-result]');target.innerHTML=resultMarkup(record,base);drawTemperature(target.querySelector('canvas'),record.result);}
  let next=0;
  async function history(reset=false){if(reset){next=0;host.querySelector('[data-history]').innerHTML='';}const data=await request(base+'?offset='+next);if(!host.isConnected)return;const list=host.querySelector('[data-history]');list.insertAdjacentHTML('beforeend',data.items.map(r=>`<p><button type="button" data-record="${esc(r.thermalbridge_id)}">${esc(r.name)} · ${esc(statusText[r.status]||r.status)}</button></p>`).join('')||'<p>暂无二维记录。</p>');list.querySelectorAll('[data-record]').forEach(b=>b.onclick=()=>action(async()=>{const record=await request(base+'/'+encodeURIComponent(b.dataset.record));if(host.isConnected)render(record);},b));next=data.next_offset;host.querySelector('[data-more]').hidden=next===null;}
  host.querySelector('[data-more]').onclick=e=>action(()=>history(),e.currentTarget);
  form.onsubmit=e=>{e.preventDefault();const body=input();action(async()=>{const record=await post(base,body);if(!host.isConnected)return;render(record);await history(true);},e.submitter);};
  host.querySelector('[data-import]').onchange=e=>action(async()=>{const file=e.target.files[0];if(!file)return;if(file.size>262144)throw new Error('输入 JSON 限 256 KiB；请只导入 input 对象');const raw=JSON.parse(await file.text()),b=raw.input||raw;if(!Array.isArray(b.regions)||b.regions.length<1||b.regions.length>32||!Array.isArray(b.probes||[])||(b.probes||[]).length>50||!b.boundaries)throw new Error('不是有效的截面输入结构');
    for(const name of ['width','height','length_unit','cell_size','geometry_source','application'])form.elements[name].value=b[name]??'';form.elements.section_name.value=b.name??'';regions.innerHTML='';b.regions.forEach(addRegion);probes.innerHTML='';(b.probes||[]).forEach(addProbe);setBoundaries(b.boundaries);for(const option of form.elements.evidence_ids.options)option.selected=(b.evidence_ids||[]).includes(option.value)&&!option.disabled;preview();});
  await history();
}
