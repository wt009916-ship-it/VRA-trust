import {mountMaterialCollections} from './material-collection-ui.js';
import {createCadMonitor} from './cad-current.js';
import {mountMaterialScenario,refreshScenarioHistory} from './material-scenarios-ui.js';
import {mountUnionWorkspace} from './ifc-union-ui.js';
import {ifcMarkup,ifcObjectMarkup} from './ifc-ui.js';
import {request,post,escape as esc,number as fmt} from './api.js';

export function dxfProjection(geometry){
  const shapes=geometry.objects.filter(r=>r.preview_points?.length>1&&!r.preview_truncated).slice(0,300);
  const points=shapes.flatMap(r=>r.preview_points);
  if(!points.length)return '<p>当前实体没有可展示的限定投影；以原件和缺口为准。</p>';
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys),span=Math.max(maxX-minX,maxY-minY);
  if(!Number.isFinite(span)||span<=0)return '<p>XY投影退化，不能据此判断三维长度。</p>';
  // One scale for X/Y keeps geometry proportions intact.
  const scale=420/span,xy=p=>[30+(p[0]-minX)*scale,470-(p[1]-minY)*scale];
  return `<figure class="cad-projection"><figcaption>WCS XY投影 · 原图坐标单位 · ${shapes.length}个实体（最多300） · 曲线为采样预览，非完整图纸渲染</figcaption><svg viewBox="0 0 720 500" role="img" aria-label="DXF几何XY投影">${shapes.map(r=>`<polyline points="${r.preview_points.map(p=>xy(p).join(',')).join(' ')}" fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke"><title>${esc(r.type+' · '+r.path.join(' / '))}</title></polyline>`).join('')}</svg></figure>`;
}

export function geometryMarkup(geometry){
  if(!geometry)return '';
  return `<section class="cad-geometry"><h3>块展开与几何测量</h3><p>展开叶实体 ${geometry.objects.length}；遍历节点 ${geometry.visited_entities}；缺口 ${geometry.issue_count}。${geometry.coverage==='partial'?'部分信息未取得，请查看缺口。':'已提取支持实体；不代表工程图完整或合规。'}</p><p>${Object.entries(geometry.expanded_counts).map(([k,v])=>esc(k)+' '+v).join(' · ')}</p>${dxfProjection(geometry)}<div class="table-scroll"><table><thead><tr><th>原句柄 / 实例路径</th><th>类型 / 图层</th><th>几何长度 m</th><th>边界面积 m²</th><th>面积口径 / 缺口</th></tr></thead><tbody>${geometry.objects.slice(0,300).map(r=>`<tr><td>${esc(r.path.join(' / '))}</td><td>${esc(r.type)} / ${esc(r.layer)}</td><td>${fmt(r.length_m,6)}</td><td>${fmt(r.area_m2,6)}</td><td>${esc(r.area_status||r.geometry_status)}</td></tr>`).join('')}</tbody></table></div><p>表格最多300行；完整实体见JSON。几何量不直接作为墙体/建筑面积或材料净用量，不自动去重叠、扣洞或识别构件语义。</p><ul>${geometry.limitations.map(t=>'<li>'+esc(t)+'</li>').join('')}</ul><details><summary>未提取实体及面积缺口${geometry.issues_truncated?'（明细截断）':''}</summary><pre>${esc(JSON.stringify(geometry.issues,null,2))}</pre></details></section>`;
}


const cadStateReasons={converter_unavailable:'本地转换器未配置或校验失败',converter_changed:'转换器版本已变化',converted_file_changed:'转换副本校验失败',converted_file_unavailable:'转换副本缺失',unchecked:'尚未核验',checking:'正在重新核验',parser_changed:'解析器版本已变化',
 parser_unavailable:'解析器当前不可用',source_unavailable:'原件缺失或校验失败',source_binding_changed:'原件与读取时的哈希不一致',
 verification_timeout:'当前状态核验超时',verification_unavailable:'当前状态无法核验',
 source_changed_during_refresh:'读取详情时来源发生变化',page_hidden:'页面已切至后台，需要重新核验'};
export const cadStateReason=reason=>cadStateReasons[reason]||'当前状态无法核验';
export function conversionMarkup(r,base){
 if(!r.conversion)return '';
 const notes=r.conversion.notifications||[];
 return `<section class="cad-conversion"><h3>DWG转换副本 · 部分信息</h3><p>${esc(r.conversion.engine)}；${notes.length}条告警/通知。未承诺无损转换；不支持的对象、样式和其他信息可能遗漏。原件保留，转换副本不能代替原始工程图。</p><details><summary>查看转换通知</summary><ul>${notes.map(n=>`<li>${esc(n.phase)} / ${esc(n.type)}：${esc(n.message)}</li>`).join('')}</ul></details>${r.status==='parsed'&&r.result?`<p><a target="_blank" rel="noopener" href="/api${base}/cad-inspections/${esc(r.cad_id)}/converted.dxf">下载部分信息 DXF 副本（重新核验来源）</a></p>`:'<p>当前来源或转换器未通过核验，转换结果与下载已撤下。</p>'}</section>`;
}
export function cadRecordMarkup(r,base){
 return `<article data-cad-record="${esc(r.cad_id)}"><h2>${esc(r.source.name)} · ${r.status==='parsed'?'已读取 · 待工程复核':r.status==='stale'?'已失效':'当前状态待核验'}</h2><p data-cad-check>正在核验当前状态…</p><p>读取时来源 SHA256：<code>${esc(r.source.hash)}</code></p>${conversionMarkup(r,base)}${r.status==='parsed'&&r.result?`<p>${esc(r.result.parser)} · ${esc(r.result.version)} · 长度换算至米：${r.result.length_scale_to_m??'未知，禁止默认换算'}</p><table><tr><th>${r.conversion?'转换副本顶层类别':'原文件顶层类别（IFC为产品类别）'}</th><th>数量</th></tr>${Object.entries(r.result.counts).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join('')}</table>${geometryMarkup(r.result.geometry)}${ifcMarkup(r.result,r.cad_id)}<ul>${r.result.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>${r.result.format==='IFC'?'':`<details><summary>顶层实体、属性、空间归属与缺口</summary><pre>${esc(JSON.stringify({objects:r.result.objects,issues:r.result.issues||[]},null,2))}</pre></details>`}`:'<p role="status">'+esc(cadStateReason(r.stale_reasons?.[0]))+'；数量暂不展示。请核验状态，来源或版本变化时新建读取记录。</p>'}<p><a target="_blank" rel="noopener" href="/api${base}/files/${r.source.file_id}">下载原文件（服务器重新核验）</a> · <a target="_blank" rel="noopener" href="/api${base}/cad-inspections/${r.cad_id}">导出完整JSON</a></p></article>`;
}
function bindCadSelection(article,record,scenarioHost,scenarioHistory){
 article.addEventListener('click',async event=>{
  const button=event.target.closest('[data-layer-product]');
  if(!button||!article.contains(button))return;
  const target=button.nextElementSibling,base='/projects/'+record.project_id;
  button.disabled=true;target.textContent='正在核验材料层与模型几何…';
  try{
   const takeoff=await post(base+'/ifc-layer-takeoffs',{cad_id:record.cad_id,product_id:Number(button.dataset.layerProduct)});
   if(!target.isConnected||!article.contains(target))return;
   target.innerHTML=`<p>已保存本次分层计量回执。打开报告时会重新核验来源和计算规则；材料层包络不能直接当作采购材料量。</p><p><a target="_blank" rel="noopener" href="/api${base}/ifc-layer-takeoffs/${takeoff.takeoff_id}/report.html">查看当前计量结果、口径与来源</a></p>`;
   if(takeoff.status==='measured'){
    const launch=document.createElement('button');launch.type='button';launch.textContent='用此计量比较两套材料方案';
    launch.onclick=()=>mountMaterialScenario(scenarioHost,base,takeoff,scenarioHistory).catch(error=>{scenarioHost.textContent=error.message;});
    target.append(launch);
   }
  }catch(error){if(target.isConnected)target.innerHTML='<p role="status">'+esc(error.message)+'</p>';}
  finally{if(button.isConnected)button.disabled=false;}
 });
 for(const select of article.querySelectorAll('[data-ifc-record]')){
  select.onchange=()=>{
   if(record.status!=='parsed'||!record.result)return;
   const id=Number(select.value),product=record.result.objects.find(p=>p.id===id);
   const geometry=record.result.ifc_geometry.objects.find(p=>p.id===id);
   select.closest('section').querySelector('[data-ifc-detail]').innerHTML=ifcObjectMarkup(product,geometry);
  };
 }
}


export async function cadWorkspace(state,host,action) {
 const base='/projects/'+state.project.project_id;
 let disposeUnion=()=>{},disposeMaterials=()=>{},monitor=null,catalog=[],page=0,historyTicket=0;
 host.innerHTML=`<div class="view-heading"><div><h1>CAD / BIM 文件核验</h1><p>只读解析原文件，保留来源和缺口。实体统计不等于建筑工程量。</p></div></div><form id="cad-upload"><label>选择 DXF / IFC / DWG（最大10 MiB）<input name="file" type="file" accept=".dxf,.ifc,.dwg" required></label><button class="primary">上传并读取</button></form><p>DXF支持限定块展开和几何量；IFC支持类型/实例属性、声明数量与限定网格测量。扫描图片/PDF文字可在“图纸识别”页处理。DWG需管理员配置本地转换器，仅提供部分信息副本，严格检查失败时拒绝输出。几何修复和合规认证尚不支持。</p><div id="cad-source"></div><div id="cad-union"></div><div id="cad-material-collections"></div><section id="cad-collection-scenario-history" aria-live="polite"></section><div id="cad-material-scenarios"></div><section id="cad-material-history" aria-live="polite"></section><div id="cad-pager"><button data-cad-prev>上一页</button><span data-cad-page></span><button data-cad-next>下一页</button><button data-cad-refresh>立即核验状态</button></div><p>每页最多20条，每5秒核验可见记录；核验失败或超时会撤下数量。最近核验时间不代表持续实时保证。</p><div id="cad-results" aria-live="polite"></div>`;
 const list=host.querySelector('#cad-results'),pager=host.querySelector('#cad-pager'),pageSize=20;
 const alive=()=>host.isConnected&&host.contains(list);
 const visible=()=>alive()&&!host.hidden&&!document.hidden;
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
   bindCadSelection(list.querySelector('[data-cad-record="'+record.cad_id+'"]'),record,host.querySelector('#cad-material-scenarios'),host.querySelector('#cad-material-history'));
  }
  monitor=createCadMonitor({
   ids:visible.map(r=>r.cad_id),
   fetchStates:(ids,signal)=>request(base+'/cad-current-states',{method:'POST',body:JSON.stringify({cad_ids:ids}),signal}),
   fetchRecord:(id,signal)=>request(base+'/cad-inspections/'+id,{signal}),
   onRecord:replace,
   onUnknown:(id,reason)=>{const row=visible.find(r=>r.cad_id===id);if(row)replace({...row,status:['parser_changed','source_unavailable','source_binding_changed'].includes(reason)?'stale':'unverified',result:null,stale_reasons:[reason]});},
   onChecked:(id,when)=>{const label=list.querySelector('[data-cad-record="'+id+'"] [data-cad-check]');if(label)label.textContent='最近核验：'+new Date(when).toLocaleString('zh-CN');}
  });
  if(!host.hidden&&!document.hidden)void monitor.refresh();
 }
 async function history(){
  const ticket=++historyTicket,records=await request(base+'/cad-inspections');
  if(!alive()||ticket!==historyTicket)return;
  disposeUnion();disposeUnion=mountUnionWorkspace(records,host.querySelector('#cad-union'),base,action);
  disposeMaterials();disposeMaterials=mountMaterialCollections(records,host.querySelector('#cad-material-collections'),base,action,host.querySelector('#cad-material-scenarios'),host.querySelector('#cad-collection-scenario-history'));
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
 const visibility=()=>{if(alive()){monitor?.invalidate(visible()?'checking':'page_hidden');if(visible())void monitor?.refresh();}};
 const observer=new MutationObserver(visibility);observer.observe(host,{attributes:true,attributeFilter:['hidden']});
 document.addEventListener('visibilitychange',visibility);
 const timer=setInterval(()=>{
  if(!alive()){monitor?.stop();disposeUnion();disposeMaterials();clearInterval(timer);document.removeEventListener('visibilitychange',visibility);observer.disconnect();}
  else if(visible())void monitor?.refresh();
 },5000);
 await history();
 await refreshScenarioHistory(host.querySelector('#cad-material-history'),base);
 await refreshScenarioHistory(host.querySelector('#cad-collection-scenario-history'),base,true);
}
