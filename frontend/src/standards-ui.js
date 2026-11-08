import {request,post,escape as esc} from './api.js';
import {attachStandardOCR} from './standard-ocr.js';
import {standardQueryBody,standardResultMarkup,createStandardMonitor} from './standard-results.js';

const input=(name,label,type='text',extra='')=>`<label>${label}<input name="${name}" type="${type}" ${extra}></label>`;
const states={pending:'待复核',confirmed:'人工已复核',rejected:'已撤回'};

export async function standardsWorkspace(state,host,action){
  const base='/projects/'+state.project.project_id;
  let fileId=null, preview=null, catalog=[], uploadTicket=0;
  host.innerHTML=`<div class="view-heading"><div><h1>规范资料与条款</h1><p>查询返回原文摘录和页码。未命中不代表规范不存在；人工复核和检索结果均不替代合规判断。</p></div></div>
    <form id="norm-search"><label>查询方式<select name="mode"><option value="single">关键词或单条精确查询</option><option value="batch">多规范 / 多条款精确对照</option></select></label><div class="form-grid" id="norm-single-fields">${input('text','检索关键词或问题')}${input('standard_code','规范编号（不含年份，可选）')}${input('edition','版本年份（可选）')}${input('clause_id','精确条款号（可选）')}</div><div id="norm-target-panel" hidden><p>每条独立指定规范、版次及条款，最多8条。缺失和版本冲突逐项显示。</p><div id="norm-targets"></div><button id="norm-target-add" type="button">添加查询条款</button></div>${input('as_of','查询适用日期','date','required')}<button class="primary" type="submit">检索已复核条款</button></form><div id="norm-result" aria-live="polite"></div>
    <h2>项目规范资料库</h2><div id="norm-catalog"></div>
    <details><summary>复核或撤回一份资料</summary><form id="norm-review"><label>资料版本<select name="standard_id" id="norm-review-choice" required></select></label><label>复核结论<select name="state"><option value="confirmed">人工已复核</option><option value="rejected">撤回该版本</option></select></label><label>核验依据<textarea name="basis" required minlength="10" placeholder="记录原件、条款编号、摘录范围、页码、有效日期和适用范围的核对依据。"></textarea></label><p>确认是当前账号的人工声明；软件未自动验证发布机构、最新版本或扫描文字正确性。</p><button type="submit">保存复核记录</button></form></details>
    <details id="norm-import-panel"><summary>登记 PDF 与条款摘录</summary><p>保留原始PDF。文字层摘录校验所在页和条款编号；扫描页可选页OCR辅助摘录，候选和人工修订分别留痕。每份最多500条，每项目最多50份。</p>
    <label>原始规范 PDF（最大20 MiB）<input id="norm-pdf" type="file" accept=".pdf"></label><p id="norm-pdf-status" role="status"></p>
    <details><summary>查看提取的文字层</summary><label>PDF页码<select id="norm-preview-page"></select></label><label>该页文字层<textarea id="norm-preview-text" rows="8" readonly></textarea></label></details>
    <div id="norm-ocr"></div>
    <form id="norm-add"><div class="form-grid">${input('standard_code','规范编号','text','required')}${input('edition','版本年份','text','required')}${input('title','规范名称','text','required')}${input('publisher','发布机构','text','required')}${input('source_url','原件公开链接','url','required')}${input('jurisdiction','适用地区或管辖范围','text','required')}${input('effective_from','生效日期','date','required')}${input('retired_on','废止日期（未知留空）','date')}${input('status_checked_on','状态核验截至日期','date','required')}</div>
    <label>资料使用授权或公开依据<textarea name="permission" minlength="5" required></textarea></label><label>规范适用范围<textarea name="scope" minlength="5" required></textarea></label><label>版本状态核验依据<textarea name="status_basis" minlength="10" required></textarea></label>
    <h3>条款摘录</h3><div id="norm-clauses"></div><button id="norm-add-clause" type="button">添加条款摘录</button><button class="primary" type="submit">登记为待复核资料</button></form></details>`;
  const search=host.querySelector('#norm-search'), form=host.querySelector('#norm-add'), clauses=host.querySelector('#norm-clauses');
  const targets=host.querySelector('#norm-targets'), resultHost=host.querySelector('#norm-result');
  let searchTicket=0;
  const active=()=>host.isConnected&&state.project.project_id===base.split('/').at(-1)&&!document.hidden;
  const monitor=createStandardMonitor({isActive:active,fetchQuery:(id,signal)=>request(base+'/standard-queries/'+id,{signal}),
    paint:(r,message)=>{if(!host.isConnected)return;resultHost.innerHTML=r?standardResultMarkup(r.result,state.project.project_id)+`<p><a href="/api${base}/standard-queries/${encodeURIComponent(r.normquery_id)}" target="_blank" rel="noopener">保存的查询与来源快照</a></p>`:'<p role="status">'+esc(message||'当前查询未核验')+'</p>';}});
  function addTarget(){
    if(targets.children.length>=8)return;
    const row=document.createElement('fieldset');row.innerHTML='<legend>精确查询条款</legend><div class="form-grid">'+input('target_code','规范编号','text','required')+input('target_edition','版本年份（可选）')+input('target_clause','条款号','text','required')+'</div><button type="button">移除查询条款</button>';
    row.querySelector('button').onclick=()=>{row.remove();};targets.append(row);
  }
  addTarget();addTarget();host.querySelector('#norm-target-add').onclick=addTarget;
  function mode(){const batch=search.elements.mode.value==='batch';host.querySelector('#norm-target-panel').hidden=!batch;host.querySelector('#norm-single-fields').hidden=batch;
    for(const e of targets.querySelectorAll('input'))e.disabled=!batch;
    for(const e of host.querySelectorAll('#norm-single-fields input'))e.disabled=batch;}
  search.elements.mode.onchange=mode;mode();
  const timer=setInterval(()=>{if(!host.isConnected){clearInterval(timer);monitor.stop();return;}if(!active()){monitor.invalidate('页面未处于活动状态，返回后重新核验引文。');return;}monitor.refresh();},5000);
  const today=new Date(); search.elements.as_of.value=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  function addClause(candidate=null){
    const row=document.createElement('fieldset');
    row.innerHTML=`<legend>条款与原文位置</legend><div class="form-grid">${input('clause_id','条款编号','text','required')}${input('pdf_page','PDF文件页码','number','required min="1" max="500"')}${input('printed_page','原书印刷页码','text','required')}${input('topic','检索主题','text','required')}</div><label>摘录方式<select name="transcription"><option value="text_layer">来自文字层（自动核对位置）</option><option value="manual_scan">扫描页人工摘录</option>${candidate?'<option value="ocr_assisted">OCR辅助、人工修订（保留来源）</option>':''}</select></label><label>摘录范围<select name="coverage"><option value="excerpt">仅为片段</option><option value="whole_clause">人工声明为完整条款</option></select></label><label>原文摘录<textarea name="text" rows="4" minlength="8" required></textarea></label><button type="button">移除此条</button>`;
    row.querySelector('button').onclick=()=>row.remove(); clauses.append(row);
    if(candidate){
      row.ocrReference={ocr_id:candidate.ocr_id,candidate_ids:candidate.candidate_ids};
      for(const k of ['text','transcription','pdf_page'])row.querySelector('[name='+k+']').value=candidate[k];
      row.querySelector('[name=transcription]').disabled=true;
      row.querySelector('[name=pdf_page]').readOnly=true;
      const label=document.createElement('label');label.textContent='对照原页的修订与核验依据';
      const basis=document.createElement('textarea');basis.name='transcription_basis';basis.required=true;basis.minLength=10;label.append(basis);row.append(label);
    }
  }
  addClause(); host.querySelector('#norm-add-clause').onclick=()=>addClause();
  const ocr=attachStandardOCR(host.querySelector('#norm-ocr'),base,()=>({file_id:fileId,page:Number(host.querySelector('#norm-preview-page').value)}),addClause,action);
  async function refresh(){
    catalog=await request(base+'/standards'); if(!host.isConnected)return;
    host.querySelector('#norm-catalog').innerHTML=catalog.map(r=>`<article><h3>${esc(r.input.standard_code)}-${esc(r.input.edition)} · ${esc(r.input.title)}</h3><p>${states[r.review.state]} · ${r.source_status==='intact'?'原件哈希一致':'来源已失效'} · 已索引${r.input.clauses.length}条（非全文覆盖）</p><p>声明生效 ${esc(r.input.effective_from)}；状态核验截至 ${esc(r.input.status_checked_on)}；适用范围 ${esc(r.input.scope)}</p><p><a href="/api${base}/standards/${r.standard_id}/source.pdf" target="_blank" rel="noopener">查看原始PDF</a> · <a href="/api${base}/standards/${r.standard_id}" target="_blank" rel="noopener">来源与复核记录</a></p></article>`).join('')||'<p>尚未登记规范。上传合法取得的PDF、定位条款并复核后，可进行检索。</p>';
    host.querySelector('#norm-review-choice').innerHTML='<option value="">选择资料版本</option>'+catalog.map(r=>`<option value="${r.standard_id}">${esc(r.input.standard_code)}-${esc(r.input.edition)} · ${esc(r.input.title)} · ${states[r.review.state]}</option>`).join('');
  }
  const showPage=()=>{const index=Number(host.querySelector('#norm-preview-page').value);host.querySelector('#norm-preview-text').value=preview?.pages[index-1]?.text||'本页没有可提取文字层；本次没有执行OCR。';};
  host.querySelector('#norm-preview-page').onchange=()=>{ocr.invalidate();showPage();};
  host.querySelector('#norm-pdf').onchange=e=>action(async()=>{
    const ticket=++uploadTicket;fileId=null;preview=null;ocr.invalidate();host.querySelector('#norm-preview-text').value='';host.querySelector('#norm-preview-page').replaceChildren();host.querySelector('#norm-pdf-status').textContent='';const file=e.target.files[0];if(!file)return;if(file.size>20*1024*1024)throw Error('PDF超过20 MiB');
    const data=new FormData();data.append('file',file);const uploaded=await request(base+'/files',{method:'POST',body:data});
    const parsed=await post(base+'/standards-preview',{file_id:uploaded.file_id});if(!host.isConnected||ticket!==uploadTicket)return;fileId=uploaded.file_id;preview=parsed;
    host.querySelector('#norm-pdf-status').textContent=`原件已保留：${parsed.page_count}页，其中${parsed.text_pages}页有文字层；其中${parsed.pages.filter(p=>p.text_layer_assessment==='known_watermark_only').length}页仅检测到已知水印。文字层不等于可用正文，尚未执行OCR。`;
    host.querySelector('#norm-preview-page').innerHTML=parsed.pages.map(p=>`<option value="${p.pdf_page}">第${p.pdf_page}页</option>`).join('');showPage();
  });
  form.onsubmit=e=>{e.preventDefault();action(async()=>{
    if(!fileId)throw Error('请先上传并检查PDF');const b=Object.fromEntries(new FormData(form));
    const fields=['standard_code','edition','title','publisher','source_url','jurisdiction','effective_from','retired_on','status_checked_on','permission','scope','status_basis'];
    const input=Object.fromEntries(fields.map(k=>[k,b[k]]));input.file_id=fileId;input.retired_on=input.retired_on||null;
    input.clauses=[...clauses.children].map(row=>({...Object.fromEntries(['clause_id','pdf_page','printed_page','topic','transcription','coverage','text'].map(k=>[k,k==='pdf_page'?Number(row.querySelector('[name='+k+']').value):row.querySelector('[name='+k+']').value])),...(row.ocrReference?{...row.ocrReference,transcription_basis:row.querySelector('[name=transcription_basis]').value}:{})}));
    searchTicket++;monitor.select(null);await post(base+'/standards',input);await refresh();host.querySelector('#norm-result').textContent='资料已登记为待复核；复核前不会作为检索依据。';host.querySelector('#norm-import-panel').open=false;
  },e.submitter);};
  host.querySelector('#norm-review').onsubmit=e=>{e.preventDefault();action(async()=>{
    const values=Object.fromEntries(new FormData(e.target)),r=catalog.find(x=>x.standard_id===values.standard_id);if(!r)throw Error('请选择资料版本');
    searchTicket++;monitor.select(null);await post(base+'/standards/'+r.standard_id+'/review',{expected_revision:r.revision,state:values.state,basis:values.basis});await refresh();host.querySelector('#norm-result').textContent='复核状态已更新。旧检索快照不再用于当前判断，请重新检索。';
  },e.submitter);};
  search.onsubmit=e=>{e.preventDefault();action(async()=>{
    const ticket=++searchTicket;monitor.select(null);
    const values=Object.fromEntries(new FormData(search));
    const rows=[...targets.children].map(row=>({standard_code:row.querySelector('[name=target_code]').value,edition:row.querySelector('[name=target_edition]').value,clause_id:row.querySelector('[name=target_clause]').value}));
    const r=await post(base+'/standard-queries',standardQueryBody(values,rows));
    if(ticket!==searchTicket||!host.isConnected)return;
    monitor.select(r.normquery_id);await monitor.refresh();
  },e.submitter);};
  await refresh();
}
