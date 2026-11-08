import {request,post,escape as esc} from './api.js';

// The candidate set is a source reference, never a confirmed quotation.
export function assistedClause(record,ids){
  if(record?.status!=='review_required'||!record.result||!ids.length||new Set(ids).size!==ids.length)throw Error('请选择当前页的候选行');
  const selected=ids.map(id=>record.result.candidates.find(c=>c.candidate_id===id));
  if(selected.some(c=>!c))throw Error('候选不存在，请重新识别');
  return {ocr_id:record.normocr_id,candidate_ids:ids,pdf_page:record.input.page,
    transcription:'ocr_assisted',text:selected.map(c=>c.text).join('\n')};
}

export function attachStandardOCR(host,base,getSelection,addClause,action){
  host.innerHTML='<button type="button" id="norm-ocr-run">识别选定页（离线 OCR）</button><p role="status" id="norm-ocr-state">只识别当前页。识别分数不是正确概率；候选须对照原页并逐字修订。</p><div id="norm-ocr-output"></div>';
  const output=host.querySelector('#norm-ocr-output'),status=host.querySelector('#norm-ocr-state'),run=host.querySelector('#norm-ocr-run');
  let generation=0,record=null;
  const invalidate=()=>{generation++;record=null;output.replaceChildren();status.textContent='选择原始 PDF 页后可识别；尚无可用 OCR 候选。';};
  const same=(s,t)=>t===generation&&host.isConnected&&JSON.stringify(getSelection())===JSON.stringify(s);
  run.onclick=e=>action(async()=>{
    invalidate();const selection=getSelection();if(!selection.file_id||!selection.page)throw Error('请先上传PDF并选择页码');
    const ticket=generation;status.textContent='正在隔离环境中提取选定页并识别，请稍候…';
    try{
      const result=await post(base+'/standard-ocr',selection);if(!same(selection,ticket))return;
      record=result;
      if(record.status!=='review_required'||!record.result)throw Error('来源已变化，请重新识别');
      status.textContent=`PDF第${record.input.page}页：${record.result.candidates.length}个未复核候选。勾选同一条款的行，然后对照原图修订。`;
      const url='/api'+base+'/standard-ocr/'+encodeURIComponent(record.normocr_id);
      output.innerHTML=`<p><a href="${url}/selected.pdf" target="_blank" rel="noopener">打开选定页 PDF（派生副本）</a></p><div class="norm-ocr-grid"><div><p>候选框以原页栅格像素定位；不表示工程长度。</p><svg role="img" aria-label="文字候选框" viewBox="0 0 ${record.result.width} ${record.result.height}" style="display:block;width:100%;height:auto;max-height:600px"><image href="${url}/preview.png" width="${record.result.width}" height="${record.result.height}"/>${record.result.candidates.map(c=>`<polygon points="${c.polygon_px.map(p=>p.join(',')).join(' ')}" fill="transparent" stroke="#c35416" stroke-width="2"><title>${esc(c.candidate_id+': '+c.text)}</title></polygon>`).join('')}</svg></div><div class="norm-ocr-lines"><fieldset><legend>选择条款候选行</legend>${record.result.candidates.map(c=>`<label><input type="checkbox" value="${c.candidate_id}">${esc(c.text)} <small>识别分数 ${c.recognition_score.toFixed(3)}</small></label>`).join('')}</fieldset><button type="button" id="norm-ocr-copy">将所选行放入待修订摘录</button></div></div>`;
      output.querySelector('#norm-ocr-copy').onclick=event=>action(async()=>{
        const ids=[...output.querySelectorAll('input:checked')].map(c=>c.value),currentId=record.normocr_id;
        const fresh=await request(base+'/standard-ocr/'+encodeURIComponent(currentId));
        if(!same(selection,ticket))return;
        if(fresh.hash!==record.hash||fresh.status!=='review_required'){invalidate();throw Error('候选来源已失效');}
        addClause(assistedClause(fresh,ids));status.textContent='已添加待修订摘录。请填写条款号、印刷页码、主题和核对依据；登记后仍须复核。';
      },event.currentTarget);
    }catch(error){if(same(selection,ticket)){invalidate();status.textContent='本次识别失败，未保留可提交候选。';}throw error;}
  },e.currentTarget);
  return {invalidate};
}
