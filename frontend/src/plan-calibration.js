import { request, escape as esc, number as num } from './api.js';
import {damageMarkup, damageOverlay} from './drawing-damage.js';

// Coordinates always refer to the server preview, never CSS display pixels.
export function planCalibration(form, base, action) {
  let uploaded=null, selection=[], crop=null, scalePoints=null, dimensions=null, interactive=true,bridges=[],overlayBounds=null;
  const panel=document.createElement('details');panel.className='plan-calibration';
  panel.innerHTML=`<summary>原图定位与比例标定 · 本地图纸建模</summary>
    <p>先打开图页。框选平面可排除剖面、图框和说明；标定两端点之间的已知尺寸。识别后会在同一原图叠加候选。</p>
    <button type="button" data-preview>打开所选图页</button>
    <div class="form-grid"><label>点击图页的操作<select data-tool><option value="crop">框选平面：点击左上、右下</option><option value="scale">标定尺寸：点击尺寸两端</option><option value="bridge">人工补接：点击已核对缺口两端</option></select></label>
    <label>已知长度 m<input data-length type="number" min=".01" step="any"></label></div>
    <label>比例依据（必填）<input name="scale_basis" minlength="10" placeholder="例如：第 6 页外轮廓 8.80 m 尺寸线"></label>
    <label>人工补接依据 · 画线后必填<textarea name="manual_bridge_basis" minlength="10" maxlength="1000" placeholder="说明原图可见端点、门洞/墙缺口及现场核对依据；分区闭合不代表该处为实墙"></textarea></label><button type="button" data-clear-bridges>清除本次人工补接线</button>
    <div class="form-grid"><label>闭合门窗缺口 m<input name="closure_m" value="0" type="number" min="0" max="1.5" step=".05"></label><label>最小候选面积 m²<input name="min_room_area_m2" value="1" type="number" min=".5" max="20" step=".1"></label></div>
    <details><summary>老旧 / 破损图纸增强参数</summary><label>断线补接上限 m<input name="damage_gap_m" value="0" type="number" min="0" max=".5" step=".01"></label><label class="check-option"><input name="deskew" type="checkbox" checked>根据可见长线校正扫描倾斜</label><label class="check-option"><input name="ocr_labels" type="checkbox" checked>读取房名及图注面积（不据此缩放）</label><p>选择「老旧图纸增强」后执行光照归一、倾斜校正与多方向墙线提取。补接默认0；不是凭空补全缺页，所有变化保留原图坐标。</p></details>
    <p class="subtle">闭合距离默认 0；增大后可能把通道封为墙，必须对照原图。原始墙线模式保留用于对照。</p>
    <button type="button" data-large>大图标定 / 核对</button><div class="plan-sheet" hidden><img alt="上传的原始图页"><svg aria-label="图纸选区、标定点及空间候选"></svg></div>
    <p data-status role="status"></p><button type="button" data-clear>清除框选与标定</button><div data-regions></div>`;
  form.querySelector('[name="layer"]').parentElement.after(panel);
  const sheet=panel.querySelector('.plan-sheet'),img=sheet.querySelector('img'),svg=sheet.querySelector('svg');
  const status=text=>{panel.querySelector('[data-status]').textContent=text;};
  const page=()=>Number(form.elements.page.value);
  const paint=()=>{if(!dimensions)return;svg.setAttribute('viewBox',`0 0 ${dimensions[0]} ${dimensions[1]}`);svg.innerHTML=`${crop?`<rect class="plan-crop" x="${crop[0]}" y="${crop[1]}" width="${crop[2]-crop[0]}" height="${crop[3]-crop[1]}"/>`:''}${scalePoints?`<line class="plan-scale" x1="${scalePoints[0][0]}" y1="${scalePoints[0][1]}" x2="${scalePoints[1][0]}" y2="${scalePoints[1][1]}"/>`:''}${bridges.map(([a,b,c,d])=>`<line class="plan-manual-bridge" x1="${a}" y1="${b}" x2="${c}" y2="${d}"/>`).join('')}${selection.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="5"/>`).join('')}`;};
  const calculate=()=>{if(!scalePoints)return;const distance=Number(panel.querySelector('[data-length]').value);if(!(distance>0))return;const px=Math.hypot(scalePoints[1][0]-scalePoints[0][0],scalePoints[1][1]-scalePoints[0][1]);if(px<5){status('标定线过短，请重新选择尺寸端点。');return;}form.elements.scale_to_m.value=String(distance/px);status(`已标定 ${distance} m / ${num(px)} 像素；请填写尺寸来源。`);};
  async function upload(){
    if(uploaded?.existing)return uploaded.record;
    const file=form.elements.file.files[0];if(!file)throw Error('先选择一份 PDF 或图片');
    if(uploaded?.file===file)return uploaded.record;
    const data=new FormData();data.set('file',file);const record=await request(base+'/files',{method:'POST',body:data});uploaded={file,record};return record;
  }
  async function show(fileId,selectedPage){
    sheet.hidden=false;
    await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('图页预览失败，请核对页码和文件类型'));img.src=`/api${base}/files/${encodeURIComponent(fileId)}/plan-preview?page=${selectedPage}`;});
    dimensions=[img.naturalWidth,img.naturalHeight];paint();
  }
  panel.querySelector('[data-preview]').onclick=e=>action(async()=>{interactive=true;const file=await upload();await show(file.file_id,page());if(form.elements.mode.value!=='damaged_raster')form.elements.mode.value='local_raster';status(`${dimensions[0]} × ${dimensions[1]} 像素；点击两点框选平面或标定。`);},e.currentTarget);
  svg.onclick=e=>{if(!interactive)return;const rect=svg.getBoundingClientRect();const point=[Math.round((e.clientX-rect.left)/rect.width*dimensions[0]),Math.round((e.clientY-rect.top)/rect.height*dimensions[1])];selection.push(point);if(selection.length===2){if(panel.querySelector('[data-tool]').value==='crop'){crop=[Math.min(selection[0][0],selection[1][0]),Math.min(selection[0][1],selection[1][1]),Math.max(selection[0][0],selection[1][0]),Math.max(selection[0][1],selection[1][1])];status('框选已记录；可切换标定尺寸。');}else if(panel.querySelector('[data-tool]').value==='bridge'){if(bridges.length>=100){status('最多100条人工补接，请拆分图纸。');}else{bridges.push([...selection[0],...selection[1]]);form.elements.mode.value='damaged_raster';status(`已标记 ${bridges.length} 条人工补接，须填写依据；识别后仍为假设。`);}}else{scalePoints=[...selection];calculate();}selection=[];}paint();};
  panel.querySelector('[data-tool]').onchange=()=>{selection=[];paint();};
  panel.querySelector('[data-length]').oninput=calculate;
  panel.querySelector('[data-large]').onclick=()=>{
    if(sheet.hidden){status('请先打开所选图页，或打开识别记录的原图叠加。');return;}
    const modal=document.createElement('dialog');modal.className='plan-dialog';
    modal.innerHTML='<div class="actions"><strong>原图标定与候选核对</strong><button type="button" data-modal-crop>框选平面</button><button type="button" data-modal-scale>标定尺寸两端</button><button type="button" data-modal-bridge>人工补接</button><button type="button" data-modal-close>完成 / 关闭</button></div><p>标定时点击尺寸线两端，关闭后填写已知长度与来源。框选时点击矩形对角点。人工补接须记录依据；识别记录可先选择继续修订。</p><div class="plan-dialog-sheet"></div>';
    const marker=document.createComment('plan-sheet');sheet.before(marker);modal.querySelector('.plan-dialog-sheet').append(sheet);
    document.body.append(modal);modal.showModal();
    const focus=crop||overlayBounds;
    if(focus&&dimensions)requestAnimationFrame(()=>{const viewport=modal.querySelector('.plan-dialog-sheet');viewport.scrollTop=Math.max(0,focus[1]/dimensions[1]*sheet.getBoundingClientRect().height-30);});
    modal.querySelector('[data-modal-crop]').onclick=()=>{panel.querySelector('[data-tool]').value='crop';selection=[];paint();};
    modal.querySelector('[data-modal-scale]').onclick=()=>{panel.querySelector('[data-tool]').value='scale';selection=[];paint();};
    modal.querySelector('[data-modal-bridge]').onclick=()=>{panel.querySelector('[data-tool]').value='bridge';selection=[];paint();};
    if(!interactive)modal.querySelectorAll('[data-modal-crop],[data-modal-scale],[data-modal-bridge]').forEach(b=>{b.disabled=true;});
    modal.querySelector('[data-modal-close]').onclick=()=>modal.close();
    modal.onclose=()=>{marker.replaceWith(sheet);modal.remove();};
  };
  const reset=()=>{crop=null;scalePoints=null;selection=[];bridges=[];form.elements.scale_to_m.value='';paint();status('标定和人工补接已清除，请重新确认。');};
  panel.querySelector('[data-clear-bridges]').onclick=()=>{bridges=[];selection=[];paint();status('本次人工补接已清除。');};
  form.elements.file.addEventListener('change',()=>{uploaded=null;form.elements.file.required=true;reset();sheet.hidden=true;});
  form.elements.page.addEventListener('change',()=>{reset();sheet.hidden=true;});
  panel.querySelector('[data-clear]').onclick=reset;
  return {upload,options:()=>({crop_px:crop,scale_basis:form.elements.scale_basis.value,closure_m:Number(form.elements.closure_m.value),min_room_area_m2:Number(form.elements.min_room_area_m2.value),damage_gap_m:Number(form.elements.damage_gap_m.value),deskew:form.elements.deskew.checked,ocr_labels:form.elements.ocr_labels.checked,manual_bridges_px:bridges,manual_bridge_basis:form.elements.manual_bridge_basis.value}),
    async overlay(task){
      if(!task.candidate)task={...task,candidate:{source:task.source,rooms:[],metadata:task.diagnostics||{}}};
      interactive=false;panel.open=true;await show(task.candidate.source.file_id,task.options?.page||task.candidate.rooms[0]?.drawing?.page||1);
      const rooms=task.candidate.rooms.filter(r=>r.drawing);
      overlayBounds=task.options?.crop_px||null;
      svg.innerHTML=rooms.map(r=>`<polygon class="plan-room" points="${r.drawing.polygon_px.map(p=>p.join(',')).join(' ')}"><title>${esc(r.name)} · 面积偏差 ${num(r.drawing.area_error_percent)}%</title></polygon>`).join('')+damageOverlay(task.candidate.metadata.damage_analysis);
      panel.querySelector('[data-regions]').innerHTML=`<table><thead><tr><th>候选</th><th>图注 m²</th><th>轮廓偏差</th></tr></thead><tbody>${rooms.map(r=>`<tr><td>${esc(r.name)}</td><td>${num(r.drawing.annotated_area_m2)}</td><td>${r.drawing.area_error_percent===null?'待核对':num(r.drawing.area_error_percent)+'%'}</td></tr>`).join('')}</tbody></table><p>未标注区域也在候选中，请确认用途及是否计入面积。</p><ul>${(task.candidate.metadata.regions||[]).filter(r=>r.status!=='candidate').map(r=>`<li>${esc(r.reason)} · ${num(r.area_m2)} m²</li>`).join('')}</ul>`;
      status('原图叠加仅用于复核；选择不同图页或文件后请重新标定。');panel.scrollIntoView({block:'nearest'});
      panel.querySelector('[data-regions]').insertAdjacentHTML('afterbegin',damageMarkup(task.candidate.metadata.damage_analysis));
      const excluded=panel.querySelector('[data-regions]>ul');
      if(excluded){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`非候选区域与排除原因 · ${excluded.children.length}项（完整记录保留）`;excluded.before(details);details.append(summary,excluded);}
      const revise=document.createElement('button');revise.type='button';revise.textContent='在此原图上继续修订补接';
      panel.querySelector('[data-regions]').prepend(revise);
      revise.onclick=()=>{
        interactive=true;const opts=task.options||{};crop=opts.crop_px||null;bridges=structuredClone(opts.manual_bridges_px||[]);selection=[];scalePoints=null;
        uploaded={existing:true,record:task.candidate.source};form.elements.file.value='';form.elements.file.required=false;
        form.elements.mode.value='damaged_raster';
        for(const key of ['page','scale_to_m','scale_basis','closure_m','damage_gap_m','min_room_area_m2','manual_bridge_basis'])if(opts[key]!==undefined&&form.elements[key])form.elements[key].value=opts[key]??'';
        for(const key of ['deskew','ocr_labels'])if(opts[key]!==undefined)form.elements[key].checked=opts[key];
        paint();status('继续使用原件 '+task.candidate.source.name+'；可重新框选、标定和画补接线，新识别将创建新任务，旧版本保留。');
      };
    }};
}
