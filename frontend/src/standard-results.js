import {escape as esc} from './api.js';

const outcomes={CITATIONS_FOUND:'找到已复核引文',VERSION_CONFLICT:'版本冲突，未采用引文',NOT_FOUND_IN_REVIEWED_INDEX:'索引中未找到',ALL_TARGETS_FOUND:'全部指定条款已找到',PARTIAL_TARGETS_FOUND:'部分条款未找到或存在冲突',NO_TARGETS_FOUND:'未取得指定条款'};

export function standardQueryBody(values,rows=[]){
 const body={as_of:values.as_of};
 if(values.mode==='batch'){
  if(!rows.length||rows.length>8)throw Error('请填写1至8条精确查询');
  body.targets=rows.map((row,i)=>({key:'target_'+(i+1),standard_code:row.standard_code.trim(),edition:row.edition.trim()||null,clause_id:row.clause_id.trim()}));
  if(body.targets.some(r=>!r.standard_code||!r.clause_id))throw Error('每条查询都需要规范编号和条款号');
 }else{
  for(const key of ['text','standard_code','edition','clause_id'])body[key]=values[key]?.trim()||(key==='text'?'':null);
 }
 return body;
}

export function standardResultMarkup(result,pid){
 if(!result)return '<p role="status">当前查询或来源未通过核验，已撤下引文。请重新检索。</p>';
 const base='/api/projects/'+encodeURIComponent(pid);
 const groups=result.targets||[result];
 return `<section class="standard-results" aria-label="当前规范查询结果"><h2>${esc(outcomes[result.status]||'查询状态未知')}</h2><p>${esc(result.notice)}</p>${groups.map((g,i)=>`<section aria-label="条款查询 ${i+1}"><h3>${g.query.standard_code?esc(g.query.standard_code)+' · ':''}${g.query.edition?esc(g.query.edition)+' · ':''}${esc(g.query.clause_id||'关键词查询')}：${esc(outcomes[g.status]||'未核验')}</h3>${g.conflicts.length?'<p role="alert">冲突编号：'+g.conflicts.map(esc).join('、')+'</p>':''}${g.citations.map(c=>`<article><h4>${esc(c.standard_code)}-${esc(c.edition)} · ${esc(c.clause_id)}</h4><p>${esc(c.title)} · PDF第${esc(c.pdf_page)}页 / 印刷页${esc(c.printed_page)} · ${c.coverage==='excerpt'?'片段摘录':'人工声明完整条款'} · ${c.transcription==='manual_scan'?'扫描件人工摘录':'文字层位置已核对'}</p><blockquote>${esc(c.text)}</blockquote><p>适用范围：${esc(c.scope)}；地区：${esc(c.jurisdiction)}</p><p><a href="${base}/standards/${encodeURIComponent(c.standard_id)}/source.pdf#page=${encodeURIComponent(c.pdf_page)}" target="_blank" rel="noopener">核对原件与上下文</a> · <a href="${esc(c.source_url)}" target="_blank" rel="noopener noreferrer">登记的来源网站</a></p></article>`).join('')}<p>匹配 ${esc(g.total_matches)} 条，显示 ${g.citations.length} 条；排除 ${g.excluded.length} 份资料。</p>${g.excluded.length?'<details><summary>未采用资料的原因</summary><pre>'+esc(JSON.stringify(g.excluded,null,2))+'</pre></details>':''}</section>`).join('')}</section>`;
}

export function standardAgentMarkup(answer){
 const progress=answer.standard_query_progress||[];
 if(!progress.length)return '';
 const current=new Map((answer.checked_standards||[]).map(r=>[r.query_index,r]));
 return `<section aria-label="Agent规范来源核验"><h3>规范查询 · 当前来源核验</h3><p>${esc(answer.standard_query_notice)}</p>${progress.map(p=>{const r=current.get(p.query_index);return p.state==='current'&&r?standardResultMarkup(r.result,r.project_id):'<p role="status">第'+esc(p.query_index)+'次查询来源未通过当前核验，已撤下引文。</p>';}).join('')}</section>`;
}

// A superseded, timed-out, or detached request must never repaint old citations.
export function createStandardMonitor({fetchQuery,paint,isActive,timeoutMs=4000}){
 let id=null,generation=0,controller=null;
 function invalidate(message='正在核验查询来源…'){
  generation++;controller?.abort();controller=null;paint(null,message);
 }
 function select(value){invalidate();id=value;}
 async function refresh(){
  if(!id||!isActive())return;
  const query=id,ticket=++generation;controller?.abort();const active=new AbortController();controller=active;
  const live=()=>generation===ticket&&id===query&&isActive();
  const timer=setTimeout(()=>{if(live()){generation++;active.abort();paint(null,'来源核验超时，已撤下引文。');}},timeoutMs);
  try{const r=await fetchQuery(query,active.signal);if(live())paint(r.status==='current'?r:null,r.status==='current'?null:'来源已变化，旧引文已撤下，请重新检索。');}
  catch{if(live())paint(null,'无法核验当前来源，已撤下引文。');}
  finally{clearTimeout(timer);if(controller===active)controller=null;}
 }
 return {select,refresh,invalidate,stop(){id=null;generation++;controller?.abort();controller=null;}};
}
