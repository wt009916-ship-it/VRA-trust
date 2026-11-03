import { request, post, escape as esc, checkUpload } from './api.js';
import { reviewDocument } from './document-review.js';

const names = {name:'项目名称',use:'建筑用途',location:'项目地点',region:'地区代码',area_m2:'总建筑面积（m²）'};
const batchStatuses={collecting:'待添加 / 分析',analyzing:'分析中',review:'待核对',interrupted:'任务中断，可重试'};
const statuses = {uploaded:'已保存',analyzing:'解析中',analyzed:'已提取 · 待复核',failed:'解析失败',unsupported:'仅保留原件'};
function factSummary(analysis) {
  const f=analysis?.facts;if(!f)return '';
  if(f.quality)return `${f.quality.records} 条逐时记录 · ${f.location.name} · 年均温 ${f.annual.temperature_c??'缺失'} °C`;
  if(f.spaces!==undefined)return `${f.spaces} 个空间 · ${f.storeys} 个楼层 · ${f.spaces_with_body} 个空间含 Body 表示`;
  if(f.pages!==undefined)return `${f.pages} 页文档 · ${f.document_pages?.filter(p=>p.method==='ocr').length||0} 页 OCR · ${analysis.candidates.length} 条项目字段`;
  if(f.data_rows!==undefined)return `${f.data_rows} 行数据 · ${f.columns.length} 列`;
  if(f.sheets)return `${f.sheets.length} 张工作表：${f.sheets.map(x=>x.name).join('、')}`;
  if(f.zones!==undefined)return `${f.zones} 个 Zone · ${Object.keys(f.objects).length} 类 IDF 对象`;
  if(f.entities)return `${Object.values(f.entities).reduce((a,b)=>a+b,0)} 个 CAD 图元 · 单位代码 ${f.units_code}`;
  return `${analysis.candidates.length} 条明确标注的项目字段`;
}
const routes = {weather:'气候与天气',spatial:'建模工作区',simulation:'仿真与方案',evidence:'项目资料'};
export async function intakeWorkspace(host, {project = null, openProject, back, initialFiles = [], resume = null, destination = 'evidence', onCommitted = async()=>{}}) {
  let batch = resume ? await request('/intakes/'+resume) : null, busy = false, savingDraft = null;
  host.innerHTML = `<main class="intake-workspace"><header class="view-heading"><div><span class="eyebrow">PROJECT INBOX / 资料收件箱</span><h1>${project?'向项目补充资料':'从项目文件开始'}</h1><p>${project?esc(project.name)+' · 保留现有建筑声明':'先整理资料，再确认缺失信息；不用先填写完整项目表。'}</p></div><button id="inbox-back">返回工作台</button></header>
    <ol class="intake-steps"><li>01 拖入资料</li><li>02 自动分类与提取</li><li>03 核对来源与缺口</li><li>04 进入专项分析</li></ol>
    <div class="intake-drop" id="inbox-drop"><strong>将项目文件拖到这里</strong><span>支持多选：PDF / IFC / DXF / IDF / EPW / CSV / XLSX / JSON / TXT / 图片</span><span>每批最多 12 份、合计 128 MB；原文件只保存在当前服务端。</span><label class="file-select">选择文件<input id="inbox-files" type="file" multiple accept=".pdf,.ifc,.dxf,.dwg,.idf,.epw,.csv,.xlsx,.json,.txt,.png,.jpg,.jpeg"></label></div>
    <p id="inbox-progress" role="status"></p><p id="inbox-error" class="error-text" role="alert" hidden></p><section id="inbox-result"></section><section id="inbox-history"></section></main>`;
  host.querySelector('#inbox-back').onclick = async()=>{try{await saveDraft();back();}catch(e){error('草稿未保存：'+e.message+'。请重试保存后返回。');}};
  const error = message => { const e=host.querySelector('#inbox-error'); e.textContent=message; e.hidden=!message; };
  const progress = message => { host.querySelector('#inbox-progress').textContent=message; };
  async function history() {
    const records=await request('/intakes'); if(!host.querySelector('#inbox-history'))return;
    const pending=records.filter(r=>r.status!=='committed'&&r.id!==batch?.id&&r.project_id===(project?.project_id||null));
    host.querySelector('#inbox-history').innerHTML=pending.length?'<h2>继续未完成的资料批次</h2>'+pending.map(r=>`<button data-resume="${r.id}">${esc(r.created_at.slice(0,16))} · ${r.file_count} 份 · ${esc(batchStatuses[r.status]||r.status)}</button>`).join(''):'';
    host.querySelectorAll('[data-resume]').forEach(b=>b.onclick=async()=>{if(busy)return; batch=await request('/intakes/'+b.dataset.resume);paint();if(batch.status==='analyzing')await poll();});
  }
  function paint() {
    if(!host.querySelector('#inbox-result')||!batch)return;
    const cards=batch.files.map(s=>`<article class="intake-card"><header><span class="file-kind">${esc(s.type.toUpperCase())}</span><strong>${esc(s.name)}</strong><span class="badge">${statuses[s.status]||esc(s.status)}</span></header><small>${(s.size/1024).toFixed(1)} KB · SHA256 ${esc(s.hash.slice(0,16))}…</small>${s.error?`<p class="error-text">${esc(s.error)}</p>`:''}${s.analysis?`<p class="intake-fact">${esc(factSummary(s.analysis))}</p><p>后续工作区：${routes[s.analysis.next_view]}</p>${s.analysis.warnings.map(w=>`<p class="intake-warning">${esc(w)}</p>`).join('')}${s.analysis.facts.document_pages?.length?`<button data-review-document="${esc(s.file_id)}">对照原图 · 核对 / 校正文字${s.corrections?.length?`（${s.corrections.length} 次校正）`:""}</button>`:""}<details><summary>查看实际提取内容与定位</summary><pre>${esc(JSON.stringify(s.analysis.facts,null,2))}</pre></details>`:''}</article>`).join('');
    let review='';
    if(batch.status==='review'){
      const suggestions={...(batch.suggestions||{}),...(batch.draft?.fields||{})};
      const fields=!project&&!batch.project_id?Object.entries(names).map(([key,label])=>`<label>${label} <span class="required-mark">必填</span><input name="${key}" required ${key==='area_m2'?'type="number" min="0.01" max="10000000" step="any"':'maxlength="'+({name:160,use:100,location:200,region:40}[key])+'"'} value="${esc(suggestions[key]??'')}" placeholder="${key==='region'?'如 CN-JX；按项目所在地核对':batch.conflicts?.includes(key)?'资料存在冲突，请核对后填写':'资料中未找到，请补充'}"><small>${Object.hasOwn(batch.draft?.fields||{},key)?'已保存的核对草稿，请继续确认':batch.conflicts?.includes(key)?'存在多种值，未自动选择':suggestions[key]!==undefined?'来自资料提取，请核对':'缺失项，不以猜测值填充'}</small></label>`).join(''):'';
      review=`<section class="intake-review"><h2>确认资料归档${fields?'与建筑声明':''}</h2><p>${fields?'已识别的字段已预填；缺失和冲突项需确认后才能建立项目。':'文件将添加到当前项目；不会修改已有建筑声明。'} 失败和不支持的文件也会保留原件及原因。</p>
      ${batch.candidates?.length?'<details><summary>提取依据 · '+batch.candidates.length+' 条</summary><ul>'+batch.candidates.map(c=>`<li><strong>${names[c.field]}：${esc(c.value)}</strong><br>${esc(c.file_name)} · ${esc(c.locator)}<blockquote>${esc(c.excerpt)}</blockquote></li>`).join('')+'</ul></details>':''}
      <form id="inbox-confirm"><p id="inbox-draft-status" role="status">${batch.draft?'核对草稿已保存 · '+esc(new Date(batch.draft.saved_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})):'核对字段离开输入框后自动保存；尚未归档为项目声明。'}</p><div class="form-grid">${fields}</div><label class="check-option"><input type="checkbox" name="reviewed" required>我已核对本次文件与项目的对应关系${fields?'及上述建筑声明':''}（必选）</label><p class="subtle">此处归档不代替工程复核。模型、天气、参数仍以待审证据进入项目，不会自动确认或启动仿真。</p><button class="primary" type="submit">${batch.project_id?'归档到项目':'建立项目并归档资料'}</button></form></section>`;
    }
    host.querySelector('#inbox-result').innerHTML=`<div class="intake-file-grid">${cards}</div>${['collecting','interrupted'].includes(batch.status)&&batch.files.length?'<button id="inbox-analyze" class="primary">分析已保存的资料</button>':''}${review}${['collecting','review','interrupted'].includes(batch.status)?'<button id="inbox-discard" class="text-button">丢弃此未归档批次</button>':''}${batch.status==='committed'?'<section class="intake-review"><h2>归档完成 · 专项处理结果</h2><p>原文件和提取记录已保存为待审证据。各专项工具结果如下。</p>'+Object.entries(batch.prepared||{}).map(([fid,result])=>'<article class="intake-card"><strong>'+esc(batch.files.find(f=>f.file_id===fid)?.name)+'</strong><p>'+esc(({analyzed:'天气分析已生成',awaiting_review:'空间候选已生成，等待人工复核',failed:'专项处理失败，原件与原因保留',running:'处理中'})[result.status]||result.status)+'</p>'+(result.error?'<p class="error-text">'+esc(result.error)+'</p>':'')+'<button data-intake-view="'+esc(result.view)+'">打开'+routes[result.view]+' →</button></article>').join('')+'<button id="inbox-open" class="primary">打开'+(routes[destination]||'项目资料')+'</button></section>':''}`;
    host.querySelectorAll('[data-review-document]').forEach(b=>b.onclick=()=>reviewDocument(host,batch,batch.files.find(s=>s.file_id===b.dataset.reviewDocument),async updated=>{batch=updated;paint();progress('校正已保存，项目字段及冲突已重新整理。');}));
    host.querySelector('#inbox-discard')?.addEventListener('click',async()=>{if(busy||!confirm('删除此批次尚未归档的文件与解析记录？此操作不能撤销。'))return;try{await request('/intakes/'+batch.id,{method:'DELETE'});batch=null;host.querySelector('#inbox-result').innerHTML='';progress('已丢弃未归档批次。');await history();}catch(e){error(e.message);}});
    host.querySelector('#inbox-analyze')?.addEventListener('click',()=>analyze().catch(e=>error(e.message)));
    host.querySelectorAll('[data-intake-view]').forEach(b=>b.onclick=()=>openProject(batch.project_id,b.dataset.intakeView));
    host.querySelector('#inbox-open')?.addEventListener('click',()=>openProject(batch.project_id,destination));
    host.querySelector('#inbox-confirm')?.addEventListener('change',()=>{saveDraft().catch(()=>{});});
    host.querySelector('#inbox-confirm')?.addEventListener('submit',async e=>{
      e.preventDefault(); const button=e.submitter; button.disabled=true;button.textContent='正在归档并生成天气 / IFC 分析…'; error('');
      try{
        const form=e.currentTarget;await saveDraft();const f=Object.fromEntries(new FormData(form)); const body={reviewed:f.reviewed==='on'};
        if(!batch.project_id){body.project={name:f.name,building:{use:f.use,location:f.location,region:f.region,area_m2:Number(f.area_m2)}};}
        batch=await post('/intakes/'+batch.id+'/commit',body);await onCommitted();paint();progress('资料已归档，专项分析结果见下方。');host.querySelector('#inbox-open')?.scrollIntoView({block:'center'});
      }catch(err){error(err.message);button.disabled=false;button.textContent='重试归档';}
    });
  }
  async function saveDraft() {
    const form=host.querySelector('#inbox-confirm');
    if(!form||!batch||batch.status!=='review'||batch.project_id)return;
    if(savingDraft){await savingDraft;return saveDraft();}
    const fields={};for(const [key,value] of new FormData(form))if(Object.hasOwn(names,key))fields[key]=String(value);
    if(JSON.stringify(fields)===JSON.stringify(batch.draft?.fields||{}))return;
    const current=batch, status=host.querySelector('#inbox-draft-status');
    if(status)status.textContent='正在保存核对草稿…';
    savingDraft=request('/intakes/'+current.id+'/draft',{method:'PUT',body:JSON.stringify({expected_revision:current.draft?.revision||0,fields})});
    try{current.draft=await savingDraft;if(status?.isConnected)status.textContent='核对草稿已保存；勾选确认后才会建立项目。';}
    catch(e){if(status?.isConnected)status.textContent='草稿未保存：'+e.message;throw e;}
    finally{savingDraft=null;}
  }
  async function poll() {
    busy=true;
    try {
      while(host.querySelector('#inbox-result')&&batch.status==='analyzing'){
        await new Promise(resolve=>setTimeout(resolve,900));
        if(!host.querySelector('#inbox-result'))return;
        batch=await request('/intakes/'+batch.id);paint();
        progress(batch.status==='analyzing'?'正在逐份提取，完成状态会保存在数据库中。':'解析已结束，请核对结果与缺项。');
      }
    }finally{busy=false;}
  }
  async function analyze(){
    if(busy)return;
    batch=await post('/intakes/'+batch.id+'/analyze',{});paint(); await poll();
  }
  async function add(files){
    if(busy)return;
    busy=true; error('');
    try{
      const selected=Array.from(files); selected.forEach(checkUpload);
      if(selected.length+(batch?.files.length||0)>12||selected.reduce((n,f)=>n+f.size,0)+(batch?.files.reduce((n,f)=>n+f.size,0)||0)>128*1024*1024)throw new Error('每批最多 12 个文件、合计 128 MB，请分批导入。');
      if(!selected.length)return;
      if(!batch||batch.status==='committed')batch=await post('/intakes',{project_id:project?.project_id||null});
      for(let i=0;i<selected.length;i++){
        progress(`正在上传 ${i+1}/${selected.length}：${selected[i].name}`);
        const form=new FormData();form.append('file',selected[i]);
        batch=await request('/intakes/'+batch.id+'/files',{method:'POST',body:form});paint();
      }
      busy=false;await analyze();
    }catch(err){error(err.message);progress('已上传的文件保留，可继续添加或点击分析。');}
    finally{busy=false;const input=host.querySelector('#inbox-files');if(input)input.value='';}
  }
  host.querySelector('#inbox-files').onchange=e=>add(e.target.files);
  const drop=host.querySelector('#inbox-drop');
  drop.ondragover=e=>{e.preventDefault();drop.classList.add('dragging');};
  drop.ondragleave=()=>drop.classList.remove('dragging');
  drop.ondrop=e=>{e.preventDefault();drop.classList.remove('dragging');add(e.dataTransfer.files);};
  paint(); await history();
  if(initialFiles.length)await add(initialFiles);
  else if(batch?.status==='analyzing')await poll();
}
