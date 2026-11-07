from pathlib import Path
p=Path('frontend/src/cad-ui.js');s=p.read_text(encoding='utf-8')
s="import {createCadMonitor} from './cad-current.js';\n"+s
start=s.index('records.map(r=>`<article>');end=s.index("`).join('')||",start)
template=s[start+len('records.map(r=>`'):end]
template=template.replace('<article>','<article data-cad-record="${esc(r.cad_id)}">',1)
template=template.replace("${r.status==='parsed'?'已读取 · 待工程复核':'已失效'}","${r.status==='parsed'?'已读取 · 待工程复核':r.status==='stale'?'已失效':'当前状态待核验'}")
template=template.replace('${r.result?','${r.status===\'parsed\'&&r.result?')
template=template.replace(":'<p>来源或解析器已变化，请新建读取记录。</p>'",':\'<p role="status">\'+esc(cadStateReason(r.stale_reasons?.[0]))+\'；数量暂不展示。请核验状态，来源或版本变化时新建读取记录。</p>\'')
template=template.replace('<p>来源 SHA256：','<p data-cad-check>正在核验当前状态…</p><p>读取时来源 SHA256：')
template=template.replace('下载原文件</a>','下载原文件（服务器重新核验）</a>')
functions="""
const cadStateReasons={unchecked:'尚未核验',checking:'正在重新核验',parser_changed:'解析器版本已变化',
 parser_unavailable:'解析器当前不可用',source_unavailable:'原件缺失或校验失败',source_binding_changed:'原件与读取时的哈希不一致',
 verification_timeout:'当前状态核验超时',verification_unavailable:'当前状态无法核验',
 source_changed_during_refresh:'读取详情时来源发生变化',page_hidden:'页面已切至后台，需要重新核验'};
export const cadStateReason=reason=>cadStateReasons[reason]||'当前状态无法核验';
export function cadRecordMarkup(r,base){
 return `"""+template+"""`;
}
function bindCadSelection(article,record){
 for(const select of article.querySelectorAll('[data-ifc-record]')){
  select.onchange=()=>{
   if(record.status!=='parsed'||!record.result)return;
   const id=Number(select.value),product=record.result.objects.find(p=>p.id===id);
   const geometry=record.result.ifc_geometry.objects.find(p=>p.id===id);
   select.closest('section').querySelector('[data-ifc-detail]').innerHTML=ifcObjectMarkup(product,geometry);
  };
 }
}

"""
head=s[:s.index('export async function cadWorkspace')]
workspace="""
export async function cadWorkspace(state,host,action) {
 const base='/projects/'+state.project.project_id;
 let disposeUnion=()=>{},monitor=null,catalog=[],page=0,historyTicket=0;
 host.innerHTML=`<div class="view-heading"><div><h1>CAD / BIM 文件核验</h1><p>只读解析原文件，保留来源和缺口。实体统计不等于建筑工程量。</p></div></div><form id="cad-upload"><label>选择 DXF / IFC（最大10 MiB）<input name="file" type="file" accept=".dxf,.ifc" required></label><button class="primary">上传并读取</button></form><p>DXF支持限定块展开和几何量；IFC支持类型/实例属性、声明数量与限定网格测量。扫描图片/PDF文字可在“图纸识别”页处理。DWG转换、几何修复和合规认证尚不支持。</p><div id="cad-source"></div><div id="cad-union"></div><div id="cad-pager"><button data-cad-prev>上一页</button><span data-cad-page></span><button data-cad-next>下一页</button><button data-cad-refresh>立即核验状态</button></div><p>每页最多20条，每5秒核验可见记录；核验失败或超时会撤下数量。最近核验时间不代表持续实时保证。</p><div id="cad-results" aria-live="polite"></div>`;
 const list=host.querySelector('#cad-results'),pager=host.querySelector('#cad-pager'),pageSize=20;
 const alive=()=>host.isConnected&&host.contains(list);
 function renderPage(){
  monitor?.stop();
  const visible=catalog.slice(page*pageSize,(page+1)*pageSize);
  pager.querySelector('[data-cad-prev]').disabled=page===0;
  pager.querySelector('[data-cad-next]').disabled=(page+1)*pageSize>=catalog.length;
  pager.querySelector('[data-cad-page]').textContent=catalog.length?`${page*pageSize+1}–${page*pageSize+visible.length} / ${catalog.length}条`:'0条';
  list.innerHTML=visible.map(r=>cadRecordMarkup({...r,status:'unverified',result:null,stale_reasons:['unchecked']},base)).join('')||'<p>尚无文件读取记录。</p>';
  function replace(record){
   if(!alive())return;
   const previous=list.querySelector('[data-cad-record="'+record.cad_id+'"]');if(!previous)return;
   previous.outerHTML=cadRecordMarkup(record,base);
   bindCadSelection(list.querySelector('[data-cad-record="'+record.cad_id+'"]'),record);
  }
  monitor=createCadMonitor({
   ids:visible.map(r=>r.cad_id),
   fetchStates:(ids,signal)=>request(base+'/cad-current-states',{method:'POST',body:JSON.stringify({cad_ids:ids}),signal}),
   fetchRecord:(id,signal)=>request(base+'/cad-inspections/'+id,{signal}),
   onRecord:replace,
   onUnknown:(id,reason)=>{const row=visible.find(r=>r.cad_id===id);if(row)replace({...row,status:['parser_changed','source_unavailable','source_binding_changed'].includes(reason)?'stale':'unverified',result:null,stale_reasons:[reason]});},
   onChecked:(id,when)=>{const label=list.querySelector('[data-cad-record="'+id+'"] [data-cad-check]');if(label)label.textContent='最近核验：'+new Date(when).toLocaleString('zh-CN');}
  });
  void monitor.refresh();
 }
 async function history(){
  const ticket=++historyTicket,records=await request(base+'/cad-inspections');
  if(!alive()||ticket!==historyTicket)return;
  disposeUnion();disposeUnion=mountUnionWorkspace(records,host.querySelector('#cad-union'),base,action);
  catalog=records.map(({cad_id,source,hash})=>({cad_id,source,hash}));page=0;renderPage();
 }
 pager.querySelector('[data-cad-prev]').onclick=()=>{if(page>0){page--;renderPage();}};
 pager.querySelector('[data-cad-next]').onclick=()=>{if((page+1)*pageSize<catalog.length){page++;renderPage();}};
 pager.querySelector('[data-cad-refresh]').onclick=()=>{monitor?.invalidate('checking');void monitor?.refresh();};
 host.querySelector('#cad-upload').onsubmit=e=>{e.preventDefault();const body=new FormData(e.currentTarget);action(async()=>{
  const file=body.get('file');if(file.size>10*1024*1024)throw Error('文件超过10 MiB，请先提供范围更小的副本。');
  const source=await request(base+'/files',{method:'POST',body});
  if(alive())host.querySelector('#cad-source').innerHTML=`<p>原件已保留：<a target="_blank" rel="noopener" href="/api${base}/files/${source.file_id}">${esc(source.name)}</a>。读取失败也不会覆盖原件。</p>`;
  await post(base+'/cad-inspections',{file_id:source.file_id});await history();
 },e.submitter);};
 const visibility=()=>{if(alive()){monitor?.invalidate('page_hidden');if(!document.hidden)void monitor?.refresh();}};
 document.addEventListener('visibilitychange',visibility);
 const timer=setInterval(()=>{
  if(!alive()){monitor?.stop();disposeUnion();clearInterval(timer);document.removeEventListener('visibilitychange',visibility);}
  else if(!document.hidden)void monitor?.refresh();
 },5000);
 await history();
}
"""
p.write_text(head+functions+workspace,encoding='utf-8',newline='\n')
