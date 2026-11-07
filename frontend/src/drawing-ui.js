import {request,post,escape as esc,number as fmt} from './api.js';
import {geometryMarkup,attachGeometry,processingControls,processingInput} from './drawing-geometry-ui.js';

export function drawingResult(record,base){
  if(record.status==='stale'||!record.result)return '<p class="error">原件、预览或解析器已变化；旧识别和复核结果已失效，请新建记录。</p>';
  const r=record.result;
  return `<p>第 ${r.page.page} / ${r.page.page_count} 页 · ${r.width} × ${r.height} 像素 · ${r.candidates.length} 个文字候选。${r.candidates.length?'所有候选均需复核。':'未检测到文字，不表示原图没有文字。'}</p><div class="drawing-canvas" style="aspect-ratio:${r.width}/${r.height}"><img src="/api${base}/drawings/${record.drawing_id}/preview.png" alt="规范化图纸预览，原件另行保留"><svg viewBox="0 0 ${r.width} ${r.height}" role="img" aria-label="OCR候选位置，非工程构件识别">${r.candidates.map(c=>`<polygon data-text-id="${c.candidate_id}" points="${c.polygon_px.map(p=>p.join(',')).join(' ')}"><title>${esc(c.candidate_id+' · '+c.text)}</title></polygon>`).join('')}</svg></div>${r.candidates.length?`<form id="drawing-review"><label>选择文字候选<select name="candidate_id">${r.candidates.map(c=>`<option value="${c.candidate_id}">${esc(c.candidate_id+' · '+c.text)}</option>`).join('')}</select></label><div id="drawing-candidate"></div><label>复核决定<select name="decision"><option value="unreadable">无法辨认，保持未知</option><option value="confirmed">逐字核对一致</option><option value="corrected">人工更正转录</option><option value="rejected">拒绝该候选</option></select></label><label>更正文字（仅人工更正时填写）<textarea name="corrected_text" maxlength="2000" disabled></textarea></label><label>复核依据（至少10字）<textarea name="basis" minlength="10" maxlength="2000" required placeholder="说明在原件哪一处核对，哪些内容仍不确定"></textarea></label><button class="primary">保存复核版本</button></form>`:''}<p>人工转录不是实测或工程认证；这里不会自动推算单位、比例尺、墙体和缺失尺寸。</p><ul>${r.limitations.map(t=>'<li>'+esc(t)+'</li>').join('')}</ul>${geometryMarkup(record,base)}<form id="drawing-reprocess">${processingControls()}<button>从保留的原件新建处理版本</button></form>`;
}

export function candidateMarkup(candidate,review){
  return `<p><strong>模型原文：</strong>${esc(candidate.text)}</p><p>模型识别分数 ${fmt(candidate.recognition_score,5)}（不是正确概率） · AI候选。</p><p>当前人工状态：${esc(({confirmed:'核对一致',corrected:'人工更正',rejected:'已拒绝',unreadable:'无法辨认'})[review?.decision]||'尚未复核')}；人工转录：${esc(review?.effective_text??'—')}</p>${review?`<p>依据：${esc(review.basis)}<br>复核时间：${esc(review.reviewed_at)}</p>`:''}`;
}

export async function drawingWorkspace(state,host,action){
  const base='/projects/'+state.project.project_id;
  host.innerHTML=`<div class="view-heading"><div><h1>图纸整理与尺度核验</h1><p>保留原图，比较处理版本；核对文字、尺寸来源和尺度冲突。</p></div></div><form id="drawing-upload"><label>图纸文件（PNG / JPEG / PDF，最大10 MiB）<input type="file" name="file" accept=".png,.jpg,.jpeg,.pdf" required></label><label>PDF页码（图片填1）<input name="page" type="number" min="1" max="200" value="1" required></label>${processingControls()}<button class="primary">保留原件并生成处理与文字候选</button></form><p>PDF逐页按150 dpi光栅化；最大1200万像素、边长6000。复杂扫描图纸可能漏检，暂不提供墙线补全或结构推断。</p><div id="drawing-upload-source"></div><label>历史识别记录<select id="drawing-record"></select></label><div id="drawing-result" aria-live="polite"></div><div id="drawing-links"></div><button id="drawing-history" hidden>查看复核历史</button><div id="drawing-history-result"></div>`;
  let current=null,requestSequence=0;
  async function show(id,selectedCandidate){
    const sequence=++requestSequence;current=null;
    host.querySelector('#drawing-result').innerHTML='<p>正在读取所选记录…</p>';
    host.querySelector('#drawing-links').innerHTML='';host.querySelector('#drawing-history-result').innerHTML='';
    host.querySelector('#drawing-history').hidden=true;
    const record=await request(base+'/drawings/'+id);if(!host.isConnected||sequence!==requestSequence)return;
    current=record;
    const historyOption=Array.from(host.querySelector('#drawing-record').options).find(o=>o.value===id);
    if(historyOption)historyOption.textContent=record.source.name+' · '+record.created_at+' · v'+record.revision;
    host.querySelector('#drawing-result').innerHTML=drawingResult(record,base);
    host.querySelector('#drawing-links').innerHTML=`<p>原件SHA256：<code>${esc(record.source.hash)}</code></p><p><a href="/api${base}/files/${record.source.file_id}" target="_blank" rel="noopener">下载原图</a> · <a href="/api${base}/drawings/${id}" target="_blank" rel="noopener">导出识别及复核JSON</a></p>`;
    host.querySelector('#drawing-history').hidden=false;
    host.querySelector('#drawing-history-result').innerHTML='';
    await attachGeometry(host,record,base,action);
    const reprocess=host.querySelector('#drawing-reprocess');
    if(reprocess)reprocess.onsubmit=e=>{e.preventDefault();const processing=processingInput(new FormData(reprocess));action(async()=>{const next=await post(base+'/drawings',{file_id:record.source.file_id,page:record.input.page,processing});await history(next.drawing_id);},e.submitter);};
    const form=host.querySelector('#drawing-review');if(!form)return;
    const candidate=form.elements.candidate_id,decision=form.elements.decision,correction=form.elements.corrected_text;
    function select(){
      const c=record.result.candidates.find(x=>x.candidate_id===candidate.value);
      host.querySelector('#drawing-candidate').innerHTML=candidateMarkup(c,record.reviews[c.candidate_id]);
      for(const polygon of host.querySelectorAll('[data-text-id]'))polygon.classList.toggle('selected',polygon.dataset.textId===c.candidate_id);
      decision.value='unreadable';correction.value='';correction.disabled=true;correction.required=false;form.elements.basis.value='';
    }
    if(selectedCandidate&&record.result.candidates.some(c=>c.candidate_id===selectedCandidate))candidate.value=selectedCandidate;
    candidate.onchange=select;select();
    decision.onchange=()=>{correction.disabled=decision.value!=='corrected';correction.required=!correction.disabled;if(correction.disabled)correction.value='';};
    for(const polygon of host.querySelectorAll('[data-text-id]'))polygon.onclick=()=>{candidate.value=polygon.dataset.textId;select();};
    form.onsubmit=e=>{e.preventDefault();const f=new FormData(form);const input={expected_revision:record.revision,candidate_id:f.get('candidate_id'),decision:f.get('decision'),basis:f.get('basis'),corrected_text:f.get('decision')==='corrected'?f.get('corrected_text'):null};action(async()=>{await post(base+'/drawings/'+id+'/review',input);await show(id,input.candidate_id);},e.submitter);};
  }
  async function history(selected){
    const records=await request(base+'/drawings');if(!host.isConnected)return;
    const select=host.querySelector('#drawing-record');select.innerHTML=records.map(r=>`<option value="${r.drawing_id}">${esc(r.source.name)} · ${esc(r.created_at)} · v${r.revision}</option>`).join('');
    select.disabled=!records.length;if(records.length){select.value=selected||records[0].drawing_id;await show(select.value);}else host.querySelector('#drawing-result').innerHTML='<p>尚无识别记录。</p>';
  }
  host.querySelector('#drawing-record').onchange=e=>action(()=>show(e.target.value));
  host.querySelector('#drawing-upload').onsubmit=e=>{e.preventDefault();const form=new FormData(e.currentTarget),file=form.get('file'),page=Number(form.get('page'));action(async()=>{
    if(file.size>10*1024*1024)throw Error('文件超过10 MiB。');
    const body=new FormData();body.append('file',file);const source=await request(base+'/files',{method:'POST',body});
    host.querySelector('#drawing-upload-source').innerHTML=`<p>原件已保留：${esc(source.name)}。识别失败也不覆盖原文件。</p>`;
    const record=await post(base+'/drawings',{file_id:source.file_id,page,processing:processingInput(form)});await history(record.drawing_id);
  },e.submitter);};
  host.querySelector('#drawing-history').onclick=()=>action(async()=>{if(!current)return;const selected=current,sequence=requestSequence;const rows=await request(base+'/drawings/'+selected.drawing_id+'/history');if(!host.isConnected||sequence!==requestSequence)return;host.querySelector('#drawing-history-result').innerHTML=`<pre>${esc(JSON.stringify(rows,null,2))}</pre>`;});
  await history();
}
