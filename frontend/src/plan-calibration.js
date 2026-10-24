import { request, escape as esc, number as num } from './api.js';

// Coordinates always refer to the server preview, never CSS display pixels.
export function planCalibration(form, base, action) {
  let uploaded=null, selection=[], crop=null, scalePoints=null, dimensions=null, interactive=true;
  const panel=document.createElement('details');panel.className='plan-calibration';
  panel.innerHTML=`<summary>原图定位与比例标定 · 本地图纸建模</summary>
    <p>先打开图页。框选平面可排除剖面、图框和说明；标定两端点之间的已知尺寸。识别后会在同一原图叠加候选。</p>
    <button type="button" data-preview>打开所选图页</button>
    <div class="form-grid"><label>点击图页的操作<select data-tool><option value="crop">框选平面：点击左上、右下</option><option value="scale">标定尺寸：点击尺寸两端</option></select></label>
    <label>已知长度 m<input data-length type="number" min=".01" step="any"></label></div>
    <label>比例依据（必填）<input name="scale_basis" minlength="10" placeholder="例如：第 6 页外轮廓 8.80 m 尺寸线"></label>
    <div class="form-grid"><label>闭合门窗缺口 m<input name="closure_m" value="0" type="number" min="0" max="1.5" step=".05"></label><label>最小候选面积 m²<input name="min_room_area_m2" value="1" type="number" min=".5" max="20" step=".1"></label></div>
    <p class="subtle">闭合距离默认 0；增大后可能把通道封为墙，必须对照原图。当前本地算法适合正交墙线，斜墙和弧墙须另行建模。</p>
    <button type="button" data-large>大图标定 / 核对</button><div class="plan-sheet" hidden><img alt="上传的原始图页"><svg aria-label="图纸选区、标定点及空间候选"></svg></div>
    <p data-status role="status"></p><button type="button" data-clear>清除框选与标定</button><div data-regions></div>`;
  form.querySelector('[name="layer"]').parentElement.after(panel);
  const sheet=panel.querySelector('.plan-sheet'),img=sheet.querySelector('img'),svg=sheet.querySelector('svg');
  const status=text=>{panel.querySelector('[data-status]').textContent=text;};
  const page=()=>Number(form.elements.page.value);
  const paint=()=>{if(!dimensions)return;svg.setAttribute('viewBox',`0 0 ${dimensions[0]} ${dimensions[1]}`);svg.innerHTML=`${crop?`<rect class="plan-crop" x="${crop[0]}" y="${crop[1]}" width="${crop[2]-crop[0]}" height="${crop[3]-crop[1]}"/>`:''}${scalePoints?`<line class="plan-scale" x1="${scalePoints[0][0]}" y1="${scalePoints[0][1]}" x2="${scalePoints[1][0]}" y2="${scalePoints[1][1]}"/>`:''}${selection.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="5"/>`).join('')}`;};
  const calculate=()=>{if(!scalePoints)return;const distance=Number(panel.querySelector('[data-length]').value);if(!(distance>0))return;const px=Math.hypot(scalePoints[1][0]-scalePoints[0][0],scalePoints[1][1]-scalePoints[0][1]);if(px<5){status('标定线过短，请重新选择尺寸端点。');return;}form.elements.scale_to_m.value=String(distance/px);status(`已标定 ${distance} m / ${num(px)} 像素；请填写尺寸来源。`);};
  async function upload(){
    const file=form.elements.file.files[0];if(!file)throw Error('先选择一份 PDF 或图片');
    if(uploaded?.file===file)return uploaded.record;
    const data=new FormData();data.set('file',file);const record=await request(base+'/files',{method:'POST',body:data});uploaded={file,record};return record;
  }
  async function show(fileId,selectedPage){
    sheet.hidden=false;
    await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('图页预览失败，请核对页码和文件类型'));img.src=`/api${base}/files/${encodeURIComponent(fileId)}/plan-preview?page=${selectedPage}`;});
    dimensions=[img.naturalWidth,img.naturalHeight];paint();
  }
  panel.querySelector('[data-preview]').onclick=e=>action(async()=>{interactive=true;const file=await upload();await show(file.file_id,page());form.elements.mode.value='local_raster';status(`${dimensions[0]} × ${dimensions[1]} 像素；点击两点框选平面或标定。`);},e.currentTarget);
  svg.onclick=e=>{if(!interactive)return;const rect=svg.getBoundingClientRect();const point=[Math.round((e.clientX-rect.left)/rect.width*dimensions[0]),Math.round((e.clientY-rect.top)/rect.height*dimensions[1])];selection.push(point);if(selection.length===2){if(panel.querySelector('[data-tool]').value==='crop'){crop=[Math.min(selection[0][0],selection[1][0]),Math.min(selection[0][1],selection[1][1]),Math.max(selection[0][0],selection[1][0]),Math.max(selection[0][1],selection[1][1])];status('框选已记录；可切换标定尺寸。');}else{scalePoints=[...selection];calculate();}selection=[];}paint();};
  panel.querySelector('[data-tool]').onchange=()=>{selection=[];paint();};
  panel.querySelector('[data-length]').oninput=calculate;
  panel.querySelector('[data-large]').onclick=()=>{
    if(sheet.hidden){status('请先打开所选图页，或打开识别记录的原图叠加。');return;}
    const modal=document.createElement('dialog');modal.className='plan-dialog';
    modal.innerHTML='<div class="actions"><strong>原图标定与候选核对</strong><button type="button" data-modal-crop>框选平面</button><button type="button" data-modal-scale>标定尺寸两端</button><button type="button" data-modal-close>完成 / 关闭</button></div><p>标定时点击尺寸线两端，关闭后填写已知长度与来源。框选时点击矩形对角点。识别结果叠加为只读。</p><div class="plan-dialog-sheet"></div>';
    const marker=document.createComment('plan-sheet');sheet.before(marker);modal.querySelector('.plan-dialog-sheet').append(sheet);
    document.body.append(modal);modal.showModal();
    modal.querySelector('[data-modal-crop]').onclick=()=>{panel.querySelector('[data-tool]').value='crop';selection=[];paint();};
    modal.querySelector('[data-modal-scale]').onclick=()=>{panel.querySelector('[data-tool]').value='scale';selection=[];paint();};
    if(!interactive)modal.querySelectorAll('[data-modal-crop],[data-modal-scale]').forEach(b=>{b.disabled=true;});
    modal.querySelector('[data-modal-close]').onclick=()=>modal.close();
    modal.onclose=()=>{marker.replaceWith(sheet);modal.remove();};
  };
  const reset=()=>{crop=null;scalePoints=null;selection=[];form.elements.scale_to_m.value='';paint();status('标定已清除，请重新确认。');};
  form.elements.file.addEventListener('change',()=>{uploaded=null;reset();sheet.hidden=true;});
  form.elements.page.addEventListener('change',()=>{reset();sheet.hidden=true;});
  panel.querySelector('[data-clear]').onclick=reset;
  return {upload,options:()=>({crop_px:crop,scale_basis:form.elements.scale_basis.value,closure_m:Number(form.elements.closure_m.value),min_room_area_m2:Number(form.elements.min_room_area_m2.value)}),
    async overlay(task){
      interactive=false;panel.open=true;await show(task.candidate.source.file_id,task.options?.page||task.candidate.rooms[0]?.drawing?.page||1);
      const rooms=task.candidate.rooms.filter(r=>r.drawing);
      svg.innerHTML=rooms.map(r=>`<polygon class="plan-room" points="${r.drawing.polygon_px.map(p=>p.join(',')).join(' ')}"><title>${esc(r.name)} · 面积偏差 ${num(r.drawing.area_error_percent)}%</title></polygon>`).join('');
      panel.querySelector('[data-regions]').innerHTML=`<table><thead><tr><th>候选</th><th>图注 m²</th><th>轮廓偏差</th></tr></thead><tbody>${rooms.map(r=>`<tr><td>${esc(r.name)}</td><td>${num(r.drawing.annotated_area_m2)}</td><td>${r.drawing.area_error_percent===null?'待核对':num(r.drawing.area_error_percent)+'%'}</td></tr>`).join('')}</tbody></table><p>未标注区域也在候选中，请确认用途及是否计入面积。</p><ul>${(task.candidate.metadata.regions||[]).filter(r=>r.status!=='candidate').map(r=>`<li>${esc(r.reason)} · ${num(r.area_m2)} m²</li>`).join('')}</ul>`;
      status('原图叠加仅用于复核；选择不同图页或文件后请重新标定。');panel.scrollIntoView({block:'nearest'});
    }};
}
