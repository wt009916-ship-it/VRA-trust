import {request,post,escape as esc,number as fmt} from './api.js';

export function processingControls(){
  return `<fieldset><legend>处理版本（原件保留）</legend><label>纠偏方式<select name="deskew_mode"><option value="none">保持原方向</option><option value="auto">尝试自动纠偏，方向不明确则保持原图</option><option value="manual">明确输入旋转角度</option></select></label><label>顺时针旋转角度 °（手动时使用，−15～15）<input name="angle_degrees" type="number" min="-15" max="15" step="any" value="0"></label><label><input name="median_filter" type="checkbox">生成 3×3 中值过滤版本及差异图（可能删除细线、文字）</label></fieldset>`;
}

export function processingInput(form){
  const mode=form.get('deskew_mode');
  if(mode==='manual'&&(form.get('angle_degrees')==null||form.get('angle_degrees')===''))throw Error('请输入明确的旋转角度。');
  return {deskew_mode:mode,angle_degrees:mode==='manual'?Number(form.get('angle_degrees')):0,median_filter:form.has('median_filter')};
}

export function geometryMarkup(record,base){
  const p=record.result?.processing;
  if(record.status==='stale'||!p)return '';
  const t=p.transform,url=`/api${base}/drawings/${record.drawing_id}/derivatives/`;
  const states={insufficient_lines:'线段证据不足',ambiguous_directions:'方向相互冲突',outside_rotation_range:'倾角超出支持范围',suggestion_requires_review:'方向建议待人工核对'};
  return `<section id="drawing-geometry"><h2>原图对照与尺度核验</h2><p>本版旋转 ${fmt(t.angle_degrees_clockwise,3)}°（顺时针）；${p.resampling==='none'?'未重采样':'使用双三次插值，可能改变像素'}。保留独立原件、规范化原图和处理图。</p>${p.auto_suggestion?`<p>自动方向：${esc(states[p.auto_suggestion.status]||p.auto_suggestion.status)}；线长支持率 ${p.auto_suggestion.support_ratio==null?'—':fmt(p.auto_suggestion.support_ratio*100,1)+'%'}。此比率不是正确概率。${p.state==='auto_not_applied'?'本次未自动旋转。':''}</p>`:''}${p.filter_difference?`<p>过滤改变 ${p.filter_difference.changed_pixels} 个像素；按灰度阈值统计，暗像素减少 ${p.filter_difference.dark_pixels_removed}、增加 ${p.filter_difference.dark_pixels_added}。这不代表语义修复质量；须核对细线和文字。<a href="${url}filter-difference.png" target="_blank" rel="noopener">查看过滤差异图</a></p>`:''}<p><a href="${url}source-preview.png" target="_blank" rel="noopener">下载规范化原图</a> · <a href="/api${base}/drawings/${record.drawing_id}/preview.png" target="_blank" rel="noopener">下载处理版本</a></p><details><summary>对照原图并标定尺寸</summary><p>下图坐标属于 EXIF 方向规范化或 PDF 光栅化后的原图。DPI 不代表工程比例尺。点击选点只记录位置；尺寸与误差须从可靠依据填写。</p><label>下一次点击填写<select id="scale-pick-target">${['a','b','m'].flatMap((key,i)=>['start','end'].map((side,j)=>`<option value="${key}_${side}">${['参考 A','参考 B','待估算线段'][i]} ${j?'终点':'起点'}</option>`)).join('')}</select></label><div class="drawing-source-canvas" style="position:relative;max-width:900px"><img id="drawing-source-pick" src="${url}source-preview.png" alt="规范化原图；点击记录标定点，不能恢复不存在的尺寸" style="display:block;width:100%;height:auto;cursor:crosshair"><svg id="scale-points" viewBox="0 0 ${t.source_size[0]} ${t.source_size[1]}" aria-label="用户选取的参考线段，不是自动识别构件" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none"></svg></div><form id="drawing-scale-form">${referenceFields('a','参考 A')}${referenceFields('b','参考 B')}<label>相对一致性容差（0～0.05，由你声明，不是规范值）<input name="relative_tolerance" type="number" value="0" min="0" max="0.05" step="any" required></label><label>标定依据和同页等比假设的理由<textarea name="basis" minlength="10" maxlength="2000" required></textarea></label><label><input type="checkbox" name="uniform" required>我声明本次只在同一图页等比平面假设下估算；尚未排除扫描畸变</label><p>误差填 0 表示未计入该项不确定性，不代表实际没有误差。冲突不会被平均成有效尺度。</p><button class="primary">保存尺度核验记录</button></form><label>已保存尺度记录<select id="drawing-scale-select"></select></label><div id="drawing-scale-result" aria-live="polite"></div><form id="drawing-length-form">${pointFields('m','待估算线段')}<button>按当前有效尺度估算长度</button></form><div id="drawing-length-result" aria-live="polite"></div></details></section>`;
}

function pointFields(key,title){
  return `<fieldset><legend>${title}：原图像素坐标</legend>${['start','end'].map((side,i)=>`<div>${i?'终点':'起点'} ${['x','y'].map(axis=>`<label>${axis}<input name="${key}_${side}_${axis}" type="number" min="0" max="6000" step="any" required></label>`).join('')}</div>`).join('')}</fieldset>`;
}
function referenceFields(key,title){
  return `${pointFields(key,title)}<label>${title} 已知长度<input name="${key}_length" type="number" min="0.000001" step="any" required></label><label>长度单位<select name="${key}_unit"><option>mm</option><option>cm</option><option>m</option></select></label><label>长度绝对误差（同单位）<input name="${key}_length_uncertainty" type="number" min="0" step="any" value="0" required></label><label>每个端点位置误差（像素）<input name="${key}_point_uncertainty" type="number" min="0" max="100" step="any" value="0" required></label>`;
}
function readPoint(form,key,side){return {x:Number(form.get(`${key}_${side}_x`)),y:Number(form.get(`${key}_${side}_y`))};}

export function scaleResult(scale){
  if(scale.status==='stale'||!scale.result)return '<p class="error">图页或算法依据已变化，旧尺度失效，不能继续估算。</p>';
  const r=scale.result,states={conflicting_references:'参考尺寸冲突，不能换算长度',single_reference_unverified:'仅一条参考，保持待核验',consistent_declared_references:'声明的参考区间相符（不是测绘认证）'};
  return `<p>${esc(states[r.status]||r.status)}</p>${r.scale_m_per_px==null?'':`<p>条件尺度 ${fmt(r.scale_m_per_px,6)} m/px；声明区间 ${r.interval_m_per_px.map(n=>fmt(n,6)).join(' ～ ')} m/px。</p>`}<ul>${r.references.map(x=>`<li>${esc(x.label)}：${fmt(x.distance_px,3)} px，声明长度 ${fmt(x.length_m,4)} m；${fmt(x.m_per_px,6)} m/px</li>`).join('')}</ul><p>相符不证明没有透视、局部拉伸或错误标注；不输出构件工程量，不自动写入工程参数。</p>`;
}

export async function attachGeometry(host,record,base,action){
  const section=host.querySelector('#drawing-geometry');if(!section)return;
  const url=base+'/drawings/'+record.drawing_id+'/scales';let current=null,measurementSequence=0,scaleSequence=0,measurementPending=0;
  const scaleForm=section.querySelector('#drawing-scale-form'),lengthForm=section.querySelector('#drawing-length-form'),select=section.querySelector('#drawing-scale-select');
  function points(){
    const svg=section.querySelector('#scale-points');
    svg.innerHTML=['a','b','m'].map((key,index)=>{
      const form=key==='m'?lengthForm:scaleForm,values=['start_x','start_y','end_x','end_y'].map(s=>form.elements[key+'_'+s].value);
      if(values.some(v=>v===''))return '';
      const [x1,y1,x2,y2]=values.map(Number);if(![x1,y1,x2,y2].every(Number.isFinite))return '';
      return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${['#167d92','#ac6f13','#a33b64'][index]}" stroke-width="3"/>`;
    }).join('');
  }
  function clearMeasurement(){measurementSequence++;section.querySelector('#drawing-length-result').innerHTML='';}
  function measurementButton(){lengthForm.querySelector('button').disabled=measurementPending>0||current?.status!=='consistent_declared_references';}
  scaleForm.oninput=points;lengthForm.oninput=()=>{clearMeasurement();points();};
  section.querySelector('#drawing-source-pick').onclick=e=>{
    const rect=e.currentTarget.getBoundingClientRect(),size=record.result.processing.transform.source_size;
    const target=section.querySelector('#scale-pick-target').value,form=target.startsWith('m')?lengthForm:scaleForm;
    form.elements[target+'_x'].value=((e.clientX-rect.left)*size[0]/rect.width).toFixed(3);
    form.elements[target+'_y'].value=((e.clientY-rect.top)*size[1]/rect.height).toFixed(3);if(form===lengthForm)clearMeasurement();points();
  };
  async function show(id){
    const sequence=++scaleSequence;current=null;lengthForm.querySelector('button').disabled=true;clearMeasurement();
    section.querySelector('#drawing-scale-result').textContent='正在核验所选尺度…';
    const row=await request(url+'/'+id);if(!section.isConnected||select.value!==id||sequence!==scaleSequence)return;
    current=row;section.querySelector('#drawing-scale-result').innerHTML=scaleResult(row)+`<p><a href="/api${url}/${id}" target="_blank" rel="noopener">导出当前尺度核验 JSON</a></p>`;
    measurementButton();
  }
  async function refresh(id){
    const rows=await request(url);if(!section.isConnected)return;
    select.innerHTML=rows.map(r=>`<option value="${r.scale_id}">${esc(r.created_at)} · ${esc(r.scale_id.slice(-8))}</option>`).join('');
    select.disabled=!rows.length;lengthForm.querySelector('button').disabled=true;
    if(rows.length){select.value=id||rows[0].scale_id;await show(select.value);}else section.querySelector('#drawing-scale-result').textContent='尚无尺度记录。';
  }
  select.onchange=()=>action(()=>show(select.value));
  scaleForm.onsubmit=e=>{e.preventDefault();const f=new FormData(scaleForm);action(async()=>{
    const body={basis_hash:record.geometry_basis_hash,references:['a','b'].map((key,i)=>({label:'用户参考 '+['A','B'][i],start:readPoint(f,key,'start'),end:readPoint(f,key,'end'),length:Number(f.get(key+'_length')),unit:f.get(key+'_unit'),length_uncertainty:Number(f.get(key+'_length_uncertainty')),point_uncertainty_px:Number(f.get(key+'_point_uncertainty'))})),relative_tolerance:Number(f.get('relative_tolerance')),basis:f.get('basis'),plane_assumption:'user_declares_uniform_scale_on_this_page'};
    const row=await post(url,body);await refresh(row.scale_id);
  },e.submitter);};
  lengthForm.onsubmit=e=>{e.preventDefault();clearMeasurement();if(current?.status!=='consistent_declared_references'||measurementPending)return;const sequence=measurementSequence,id=current.scale_id,f=new FormData(lengthForm);measurementPending++;measurementButton();action(async()=>{
    try{
      const row=await post(url+'/'+id+'/measure',{start:readPoint(f,'m','start'),end:readPoint(f,'m','end'),coordinates:'source'});
      if(!section.isConnected||current?.scale_id!==id||sequence!==measurementSequence)return;
    section.querySelector('#drawing-length-result').innerHTML=`<p>条件长度 ${fmt(row.length_m,4)} m；仅传播尺度区间：${row.scale_interval_length_m.map(x=>fmt(x,4)).join(' ～ ')} m。</p><p>${esc(row.notice)}</p><button type="button" id="drawing-length-export">导出本次条件长度 JSON</button>`;
    section.querySelector('#drawing-length-export').onclick=()=>{
      const objectUrl=URL.createObjectURL(new Blob([JSON.stringify(row,null,2)],{type:'application/json'}));
      const link=document.createElement('a');link.href=objectUrl;link.download='conditional-drawing-length.json';link.click();setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
    };
    }finally{measurementPending--;if(section.isConnected)measurementButton();}
  });};
  await refresh();
}
