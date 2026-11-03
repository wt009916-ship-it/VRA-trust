import { post, escape as esc } from './api.js';

const methods = {ocr:'本地 OCR',text:'PDF 文字层',failed:'识别失败',skipped:'未执行 OCR'};

export function reviewDocument(host, batch, source, onSaved) {
  const pages=source.analysis.facts.document_pages;
  const dialog=document.createElement('dialog');dialog.className='document-review';host.append(dialog);
  let selected=pages[0].page, saving=false;
  dialog.addEventListener('close',()=>dialog.remove());
  function paint(){
    const page=pages.find(p=>p.page===selected), changes=source.corrections||[];
    const latest=changes.filter(c=>c.page===selected).at(-1);
    const editable=batch.status==='review';
    dialog.innerHTML=`<header class="dialog-heading"><div><span class="eyebrow">SOURCE REVIEW / 原件核对</span><h2>${esc(source.name)}</h2></div><button id="doc-close" aria-label="关闭">×</button></header>
      <div class="document-toolbar"><label>页码 <select id="doc-page">${pages.map(p=>`<option value="${p.page}" ${p.page===selected?'selected':''}>第 ${p.page} 页 · ${methods[p.method]}</option>`).join('')}</select></label><span>原件 SHA256 ${esc(source.hash.slice(0,16))}…</span><a href="/api/intakes/${encodeURIComponent(batch.id)}/files/${encodeURIComponent(source.file_id)}/pages/${selected}" target="_blank" rel="noopener">打开原图大图 ↗</a></div>
      <div class="document-columns"><section><h3>原图与文字位置</h3><p class="subtle">${page.method==='ocr'?'点击右侧识别行，可定位到图中对应位置。':'对照原图检查文字、单位与页码。'} OCR 置信度不是工程准确率。</p>
      <div class="document-image"><img id="doc-image" alt="第 ${selected} 页原件预览" src="/api/intakes/${encodeURIComponent(batch.id)}/files/${encodeURIComponent(source.file_id)}/pages/${selected}">${page.width?`<svg id="doc-boxes" viewBox="0 0 ${page.width} ${page.height}" aria-hidden="true">${(page.lines||[]).map((l,i)=>`<polygon data-line="${i}" points="${l.box.map(p=>p.join(',')).join(' ')}"/>`).join('')}</svg>`:''}</div><p id="doc-preview-error" class="error-text" role="alert"></p></section>
      <section><h3>${latest?'已校正文字 · v'+latest.revision:'提取文字 · 待人工核对'}</h3>${page.error?`<p class="error-text">${esc(page.error)}</p>`:''}
      <form id="doc-form"><label>第 ${selected} 页文字<textarea name="text" rows="12" maxlength="30000" ${editable?'':'readonly'}>${esc(latest?.text??page.text)}</textarea></label><p class="subtle">识别错误可直接修改；项目字段须明确写成“项目名称：…”、“总建筑面积：… m²”等。原识别结果始终保留。</p>
      ${editable?'<label>校正原因 <span class="required-mark">必填</span><input name="reason" required minlength="3" maxlength="500" placeholder="如：按原图修正面积小数点"></label><button class="primary">保存校正并重新整理项目字段</button>':'<p>已归档记录只读；新增证据请在项目中补充资料。</p>'}<p id="doc-error" role="alert" class="error-text"></p></form>
      <details><summary>原始识别结果 · ${(page.lines||[]).length} 行</summary>${page.lines?.length?'<ol class="ocr-lines">'+page.lines.map((l,i)=>`<li><button type="button" data-focus-line="${i}"><span>${esc(l.text)}</span><small class="${l.confidence<.85?'ocr-low':''}">${(l.confidence*100).toFixed(1)}%</small></button></li>`).join('')+'</ol>':'<pre>'+esc(page.text)+'</pre>'}</details>
      ${page.native_text?'<details><summary>PDF 原始文字层（独立保留）</summary><pre>'+esc(page.native_text)+'</pre></details>':''}
      <details><summary>人工校正历史 · ${changes.filter(c=>c.page===selected).length} 次</summary>${changes.filter(c=>c.page===selected).map(c=>`<article><strong>v${c.revision} · ${esc(c.timestamp)}</strong><p>${esc(c.reason)} · ${esc(c.actor)}</p><pre>${esc(c.text)}</pre></article>`).join('')||'<p>暂无人工校正</p>'}</details></section></div>`;
    dialog.querySelector('#doc-close').onclick=()=>dialog.close();
    dialog.querySelector('#doc-page').onchange=e=>{if(saving)return;selected=Number(e.target.value);paint();};
    dialog.querySelector('#doc-image').onerror=()=>{dialog.querySelector('#doc-preview-error').textContent='原件预览加载失败，请重试；仍需核对原文件后再保存校正。';};
    dialog.querySelectorAll('[data-focus-line]').forEach(b=>b.onclick=()=>{dialog.querySelectorAll('[data-line]').forEach(p=>p.classList.toggle('selected',p.dataset.line===b.dataset.focusLine));dialog.querySelector('#doc-image').scrollIntoView({block:'nearest'});});
    dialog.querySelector('#doc-form').onsubmit=async e=>{
      e.preventDefault();if(saving||!editable)return;
      const data=new FormData(e.currentTarget);saving=true;e.submitter.disabled=true;dialog.querySelector('#doc-page').disabled=true;
      try{
        const updated=await post(`/intakes/${batch.id}/files/${source.file_id}/corrections`,{expected_revision:changes.length,page:selected,text:data.get('text'),reason:data.get('reason')});
        await onSaved(updated);dialog.close();
      }catch(err){dialog.querySelector('#doc-error').textContent=err.message;e.submitter.disabled=false;dialog.querySelector('#doc-page').disabled=false;}
      finally{saving=false;}
    };
  }
  paint();dialog.showModal();
}
