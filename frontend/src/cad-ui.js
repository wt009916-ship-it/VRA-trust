import {request,post,escape as esc} from './api.js';

export async function cadWorkspace(state,host,action) {
  const base='/projects/'+state.project.project_id;
  host.innerHTML=`<div class="view-heading"><div><h1>CAD / BIM 文件核验</h1><p>只读解析原文件，保留来源和缺口。实体统计不等于建筑工程量。</p></div></div><form id="cad-upload"><label>选择 DXF / IFC（最大10 MiB）<input name="file" type="file" accept=".dxf,.ifc" required></label><button class="primary">上传并读取</button></form><p>DWG转换、图纸OCR、几何修复和合规认证尚不支持。DXF块未展开；IFC读取构件及属性，不生成几何网格。</p><div id="cad-source"></div><div id="cad-results" aria-live="polite"></div>`;
  async function history(){
    const records=await request(base+'/cad-inspections');if(!host.isConnected)return;
    host.querySelector('#cad-results').innerHTML=records.map(r=>`<article><h2>${esc(r.source.name)} · ${r.status==='parsed'?'已读取 · 待工程复核':'已失效'}</h2><p>来源 SHA256：<code>${esc(r.source.hash)}</code></p>${r.result?`<p>${esc(r.result.parser)} · ${esc(r.result.version)} · 长度换算至米：${r.result.length_scale_to_m??'未知，禁止默认换算'}</p><table><tr><th>原文件类别</th><th>数量</th></tr>${Object.entries(r.result.counts).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join('')}</table><ul>${r.result.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><details><summary>实体、属性、空间归属与缺口</summary><pre>${esc(JSON.stringify({objects:r.result.objects,issues:r.result.issues||[]},null,2))}</pre></details>`:'<p>来源或解析器已变化，请新建读取记录。</p>'}<p><a target="_blank" rel="noopener" href="/api${base}/files/${r.source.file_id}">下载原文件</a> · <a target="_blank" rel="noopener" href="/api${base}/cad-inspections/${r.cad_id}">导出完整JSON</a></p></article>`).join('')||'<p>尚无文件读取记录。</p>';
  }
  host.querySelector('#cad-upload').onsubmit=e=>{e.preventDefault();const body=new FormData(e.currentTarget);action(async()=>{
    const file=body.get('file');if(file.size>10*1024*1024)throw Error('文件超过10 MiB，请先提供范围更小的副本。');
    const source=await request(base+'/files',{method:'POST',body});
    if(host.isConnected)host.querySelector('#cad-source').innerHTML=`<p>原件已保留：<a target="_blank" rel="noopener" href="/api${base}/files/${source.file_id}">${esc(source.name)}</a>。读取失败也不会覆盖原件。</p>`;
    await post(base+'/cad-inspections',{file_id:source.file_id});await history();
  },e.submitter);};
  await history();
}
