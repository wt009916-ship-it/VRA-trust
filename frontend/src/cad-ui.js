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

export async function cadWorkspace(state,host,action) {
  const base='/projects/'+state.project.project_id;
  host.innerHTML=`<div class="view-heading"><div><h1>CAD / BIM 文件核验</h1><p>只读解析原文件，保留来源和缺口。实体统计不等于建筑工程量。</p></div></div><form id="cad-upload"><label>选择 DXF / IFC（最大10 MiB）<input name="file" type="file" accept=".dxf,.ifc" required></label><button class="primary">上传并读取</button></form><p>DXF支持限定块展开和几何量；IFC支持类型/实例属性、声明数量与限定网格测量。DWG转换、图纸OCR、几何修复和合规认证尚不支持。</p><div id="cad-source"></div><div id="cad-results" aria-live="polite"></div>`;
  async function history(){
    const records=await request(base+'/cad-inspections');if(!host.isConnected)return;
    host.querySelector('#cad-results').innerHTML=records.map(r=>`<article><h2>${esc(r.source.name)} · ${r.status==='parsed'?'已读取 · 待工程复核':'已失效'}</h2><p>来源 SHA256：<code>${esc(r.source.hash)}</code></p>${r.result?`<p>${esc(r.result.parser)} · ${esc(r.result.version)} · 长度换算至米：${r.result.length_scale_to_m??'未知，禁止默认换算'}</p><table><tr><th>原文件顶层类别（IFC为产品类别）</th><th>数量</th></tr>${Object.entries(r.result.counts).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join('')}</table>${geometryMarkup(r.result.geometry)}${ifcMarkup(r.result,r.cad_id)}<ul>${r.result.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>${r.result.format==='IFC'?'':`<details><summary>顶层实体、属性、空间归属与缺口</summary><pre>${esc(JSON.stringify({objects:r.result.objects,issues:r.result.issues||[]},null,2))}</pre></details>`}`:'<p>来源或解析器已变化，请新建读取记录。</p>'}<p><a target="_blank" rel="noopener" href="/api${base}/files/${r.source.file_id}">下载原文件</a> · <a target="_blank" rel="noopener" href="/api${base}/cad-inspections/${r.cad_id}">导出完整JSON</a></p></article>`).join('')||'<p>尚无文件读取记录。</p>';
    for(const select of host.querySelectorAll('[data-ifc-record]')){
      const record=records.find(r=>r.cad_id===select.dataset.ifcRecord);
      select.onchange=()=>{
        const id=Number(select.value),product=record.result.objects.find(p=>p.id===id);
        const geometry=record.result.ifc_geometry.objects.find(p=>p.id===id);
        select.closest('section').querySelector('[data-ifc-detail]').innerHTML=ifcObjectMarkup(product,geometry);
      };
    }
  }
  host.querySelector('#cad-upload').onsubmit=e=>{e.preventDefault();const body=new FormData(e.currentTarget);action(async()=>{
    const file=body.get('file');if(file.size>10*1024*1024)throw Error('文件超过10 MiB，请先提供范围更小的副本。');
    const source=await request(base+'/files',{method:'POST',body});
    if(host.isConnected)host.querySelector('#cad-source').innerHTML=`<p>原件已保留：<a target="_blank" rel="noopener" href="/api${base}/files/${source.file_id}">${esc(source.name)}</a>。读取失败也不会覆盖原件。</p>`;
    await post(base+'/cad-inspections',{file_id:source.file_id});await history();
  },e.submitter);};
  await history();
}
