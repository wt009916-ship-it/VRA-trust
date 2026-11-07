import {request,post,escape as esc} from './api.js';

const issues={scope_missing:'缺少比对范围',scope_conflict:'比对范围不同',ambiguous_occurrences:'编号重复或一段文字含多个编号',
 dimensions_missing:'没有明确属性与单位',dimension_unknown:'尺寸缺失、单位不明或无法解析',dimension_conflict:'尺寸标注互相矛盾',
 transcription_unreviewed:'原文尚未逐字复核',source_position_uncertain:'原图位置尚不确定'};
const roles={width:'宽度',height:'高度',length:'长度',thickness:'厚度'};
const decisions={association_confirmed:'已人工确认标注关联',rejected:'已拒绝该关联',unresolved:'仍待核实'};

export function associationMarkup(record,base){
 if(record.status==='stale'||!record.result)return '<p role="status">来源或方法已变化，旧关联、尺寸及复核结果已撤下，请基于当前图纸另建分析。</p>';
 const names=new Map(record.sources.map(s=>[s.drawing_id,`${s.source_name} · 第${s.page}页`]));
 return `<p>${esc(record.notice)}</p><p><a href="/api${base}/drawing-associations/${record.drawingassociation_id}/report.html" target="_blank" rel="noopener">打开当前报告</a> · <a href="/api${base}/drawing-associations/${record.drawingassociation_id}" target="_blank" rel="noopener">导出当前JSON</a></p>${record.result.relations.length?record.result.relations.map(r=>`<article><h3>${esc(r.mark)}</h3><p>${esc(r.issues.length?r.issues.map(x=>issues[x]||x).join('；'):'所选标注一致，仍不证明实体同一性')}</p>${r.observations.map(o=>`<details><summary>${esc(names.get(o.drawing_id)||o.drawing_id)} · ${esc(o.annotation.text)}</summary><p>范围：${esc(o.scope_label||'未知')}（用户声明）</p><p>文字来源：${o.annotation.transcription_reviewed?'人工转录复核':'AI候选，待复核'}；OCR分数 ${esc(o.annotation.recognition_score)}，不是正确概率。</p><p>原文：${esc(o.annotation.original_text)}</p><p>原图位置：${esc(o.annotation.polygon_source_px.map(p=>p.join(', ')).join(' / '))} px</p><a href="/api${base}/drawings/${o.drawing_id}/preview.png" target="_blank" rel="noopener">对照处理图</a> · <a href="/api${base}/files/${o.source_file_id}" target="_blank" rel="noopener">打开保留原件</a></details>`).join('')}<table><thead><tr><th>标注属性</th><th>各图换算值（m）</th><th>对照</th></tr></thead><tbody>${r.comparisons.map(c=>`<tr><td>${esc(roles[c.role]||c.role)}</td><td>${c.values_m.map(v=>esc(v??'—')).join(' / ')}</td><td>${esc(({consistent:'标注一致',conflict:'标注冲突',unknown:'未知，不能判定'})[c.state])}</td></tr>`).join('')}</tbody></table><p>当前复核：${esc(decisions[record.reviews[r.relation_id]?.decision]||'尚未复核')}</p><form data-association-review="${r.relation_id}"><label>关联决定<select name="decision"><option value="unresolved">保持待核实</option><option value="rejected">拒绝该关联</option><option value="association_confirmed" ${r.state==='consistent_annotations'?'':'disabled'}>确认标注关联（不合并构件）</option></select></label><label>依据<textarea name="basis" minlength="10" maxlength="2000" required></textarea></label><button>保存复核版本</button></form></article>`).join(''):'<p>未发现跨图编号候选，不代表图纸之间没有关联。当前规则只识别有限字母数字编号。</p>'}<details><summary>覆盖范围与未识别文字</summary>${record.result.coverage.map(c=>`<p>${esc(names.get(c.drawing_id))}：选取${c.selected_text_count}个文字候选，提取${c.mark_occurrence_count}处标记；${c.unrecognized_candidate_ids.length}处未识别为标记。</p>`).join('')}</details><ul>${record.result.limitations.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`;
}

export function createAssociationReader({fetchRecord,onRecord,onUnknown,onChecked,timeoutMs=4000}){
 let id=null,generation=0,active=null,stopped=false,signature=null;
 function invalidate(reason='核验状态未知，已撤下旧结果'){
  generation++;active?.abort();active=null;signature=null;if(!stopped)onUnknown(reason);
 }
 async function refresh(){
  if(stopped||!id)return;
  const selected=id,ticket=++generation;active?.abort();const controller=new AbortController();active=controller;
  const live=()=>!stopped&&ticket===generation;let timer;
  try{
   const record=await Promise.race([fetchRecord(selected,controller.signal),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('核验超时')),timeoutMs);})]);
   if(!live())return;
   if(record.drawingassociation_id!==selected||!['stale','review_required','no_cross_sheet_candidates'].includes(record.status)||
      !/^[a-f0-9]{64}$/.test(record.hash)|| (record.status==='stale'?record.result!==null:!Array.isArray(record.result?.relations)))throw Error('核验结果不完整');
   const next=record.hash+'|'+record.status+'|'+JSON.stringify(record.stale_reasons);
   if(next!==signature){signature=next;onRecord(record);}onChecked?.();
  }catch(error){if(live()){invalidate(error.message||'核验失败');}}
  finally{clearTimeout(timer);if(active===controller)active=null;controller.abort();}
 }
 return {refresh,invalidate,select(value){id=value;invalidate('正在核验所选关联…');return refresh();},
  stop(){stopped=true;generation++;active?.abort();active=null;signature=null;}};
}

function sourceEditor(record){
 const options=record.result.candidates.map(c=>`<option value="${c.candidate_id}">${esc(c.candidate_id+' · '+c.text)}</option>`).join('');
 return `<fieldset data-association-sheet="${record.drawing_id}"><legend>${esc(record.source.name)} · 第${record.input.page}页</legend><label>比对范围（如一层东区，或全楼某门型）<input name="scope_label" maxlength="120"></label><label>范围依据（填写范围时至少10字）<textarea name="scope_basis" maxlength="1000"></textarea></label><details><summary>限定文字或关联分开的尺寸标注</summary><label>限定候选（不选则分析全部文字）<select name="candidate_ids" multiple size="5">${options}</select></label><p>仅支持明确 WIDTH / HEIGHT / LENGTH / THICKNESS（或宽、高、长、厚）及长度单位。两个未命名数字不自动当作宽高；分开的尺寸可在下方声明对应关系。</p><div data-quantity-links></div><button type="button" data-add-quantity>关联一处独立尺寸文字</button></details><template data-quantity-template><div data-quantity-row><label>编号文字<select name="mark_candidate_id">${options}</select></label><label>尺寸文字<select name="value_candidate_id">${options}</select></label><label>属性<select name="role">${Object.entries(roles).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label><label>对应关系依据<textarea name="basis" minlength="10" maxlength="1000" required></textarea></label><button type="button" data-remove-quantity>移除此对应关系</button></div></template></fieldset>`;
}

export async function attachAssociations(host,base,action){
 const section=document.createElement('section');section.id='drawing-associations';host.append(section);
 section.innerHTML=`<h2>跨图标注关联与矛盾检查</h2><p>选择2–8张已识别图页，核对编号和明确标注。相同编号不证明是同一构件，不用于去重算量。</p><button data-refresh-sources>刷新图页列表</button><form data-association-create><label>分析名称<input name="name" maxlength="120" value="跨图标注核对" required></label><label>选择图页（可多选）<select data-association-sheets multiple size="5"></select></label><button type="button" data-load-sheets>读取所选图页并重新填写范围</button><div data-sheet-editors></div><button data-create-button disabled>生成关联候选与尺寸对照</button></form><label>历史关联分析<select data-association-history></select></label><button data-refresh-current>核验当前来源</button><p data-association-checked>仅显示已读取状态；可见时每10秒重新核验，失败会撤下旧结果。</p><div data-association-result aria-live="polite"></div>`;
 const target=section.querySelector('[data-association-result]'),select=section.querySelector('[data-association-sheets]'),history=section.querySelector('[data-association-history]'),editors=section.querySelector('[data-sheet-editors]'),create=section.querySelector('[data-association-create]');
 const alive=()=>section.isConnected&&host.contains(section),visible=()=>alive()&&!host.hidden&&!document.hidden;
 let drafts=[],selectionTicket=0,current=null;
 const reader=createAssociationReader({fetchRecord:(id,signal)=>request(base+'/drawing-associations/'+id,{signal}),
  onUnknown:message=>{current=null;if(alive())target.innerHTML='<p role="status">'+esc(message)+'</p>';},
  onChecked:()=>{if(alive())section.querySelector('[data-association-checked]').textContent='最近核验：'+new Date().toLocaleString('zh-CN')+'；每10秒更新，非持续实时保证。';},
  onRecord:record=>{if(!alive())return;current=record;target.innerHTML=associationMarkup(record,base);
   for(const form of target.querySelectorAll('[data-association-review]'))form.onsubmit=e=>{e.preventDefault();const input=new FormData(form);action(async()=>{
    if(!current||current.drawingassociation_id!==record.drawingassociation_id||current.revision!==record.revision)throw Error('记录已变化，请重新核验');
    await post(base+'/drawing-associations/'+record.drawingassociation_id+'/review',{expected_revision:record.revision,relation_id:form.dataset.associationReview,decision:input.get('decision'),basis:input.get('basis')});
    reader.invalidate('正在读取新复核版本…');await reader.refresh();
   },e.submitter);};}});
 async function refreshSources(){
  const selected=new Set(Array.from(select.selectedOptions).map(x=>x.value));const rows=await request(base+'/drawings');if(!alive())return;
  select.innerHTML=rows.map(r=>`<option value="${r.drawing_id}" ${selected.has(r.drawing_id)?'selected':''}>${esc(r.source.name)} · 第${r.page??'?'}页 · v${r.revision}</option>`).join('');
 }
 async function refreshHistory(selected){
  const rows=await request(base+'/drawing-associations');if(!alive())return;
  history.innerHTML=rows.map(r=>`<option value="${r.drawingassociation_id}">${esc(r.name)} · v${r.revision}</option>`).join('');
  history.disabled=!rows.length;if(rows.length){history.value=selected||rows[0].drawingassociation_id;await reader.select(history.value);}
 }
 section.querySelector('[data-load-sheets]').onclick=e=>action(async()=>{
  const ticket=++selectionTicket,ids=Array.from(select.selectedOptions).map(x=>x.value);drafts=[];editors.innerHTML='';create.querySelector('[data-create-button]').disabled=true;
  if(ids.length<2||ids.length>8)throw Error('请选择2–8张不同图页。');
  const records=await Promise.all(ids.map(id=>request(base+'/drawings/'+id)));if(!alive()||ticket!==selectionTicket)return;
  if(records.some(r=>r.status==='stale'||!r.result))throw Error('所选图页存在失效记录，请先重新识别或核对来源。');
  drafts=records;editors.innerHTML=records.map(sourceEditor).join('');create.querySelector('[data-create-button]').disabled=false;
  for(const field of editors.querySelectorAll('fieldset'))field.querySelector('[data-add-quantity]').onclick=()=>{
   const list=field.querySelector('[data-quantity-links]');if(list.children.length>=50)throw Error('每图最多50处声明对应。');
   const row=field.querySelector('template').content.cloneNode(true);row.querySelector('[data-remove-quantity]').onclick=e=>e.target.closest('[data-quantity-row]').remove();list.append(row);
  };
 },e.currentTarget);
 select.onchange=()=>{selectionTicket++;drafts=[];editors.innerHTML='';create.querySelector('[data-create-button]').disabled=true;};
 create.onsubmit=e=>{e.preventDefault();action(async()=>{
  if(drafts.length<2)throw Error('先读取所选图页。');
  const sheets=drafts.map(r=>{const field=editors.querySelector('[data-association-sheet="'+r.drawing_id+'"]');const picked=Array.from(field.querySelector('[name=candidate_ids]').selectedOptions).map(x=>x.value);
   return {drawing_id:r.drawing_id,drawing_hash:r.hash,scope_label:field.querySelector('[name=scope_label]').value,scope_basis:field.querySelector('[name=scope_basis]').value,candidate_ids:picked.length?picked:null,
    quantity_links:Array.from(field.querySelectorAll('[data-quantity-row]')).map(row=>Object.fromEntries(['mark_candidate_id','value_candidate_id','role','basis'].map(k=>[k,row.querySelector('[name='+k+']').value])))};});
  const record=await post(base+'/drawing-associations',{name:new FormData(create).get('name'),sheets});await refreshHistory(record.drawingassociation_id);
 },e.submitter);};
 history.onchange=()=>action(()=>reader.select(history.value));
 section.querySelector('[data-refresh-sources]').onclick=()=>action(refreshSources);
 section.querySelector('[data-refresh-current]').onclick=()=>{reader.invalidate('正在核验…');void reader.refresh();};
 const visibility=()=>{if(alive()){reader.invalidate(visible()?'重新核验来源…':'页面隐藏，撤下旧结果');if(visible())void reader.refresh();}};
 const observer=new MutationObserver(visibility);observer.observe(host,{attributes:true,attributeFilter:['hidden']});
 document.addEventListener('visibilitychange',visibility);window.addEventListener('focus',visibility);
 const timer=setInterval(()=>{if(!alive()){clearInterval(timer);reader.stop();observer.disconnect();document.removeEventListener('visibilitychange',visibility);window.removeEventListener('focus',visibility);}else if(visible())void reader.refresh();},10000);
 await refreshSources();await refreshHistory();
 return {refreshSources,refreshCurrent(){reader.invalidate('原图复核已变化，重新核验关联…');return reader.refresh();}};
}
