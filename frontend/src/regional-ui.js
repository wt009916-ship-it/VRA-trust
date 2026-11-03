import {request,escape as esc} from './api.js';

const status={QA_PASSED:'逐时检查通过',QA_BLOCKED:'原件有阻断',FAILED:'获取失败',CATALOGUED:'仅目录',DAILY_REFERENCE:'全年日值 · 非EPW'};
export async function regionalWorkspace(host,base,action){
  host.innerHTML=`<details class="studio-panel"><summary>中国气候与区域地质资料库</summary><p>按来源范围查询典型气象年和区域地层。两类资料均需工程适用性核对。</p><form class="form-grid"><label>资料类型<select name="kind"><option value="weather">气象档案 / EPW</option><option value="geology">区域地层目录</option></select></label><label>关键词<input name="query" maxlength="120" placeholder="站点、名称、岩性或年代"></label><label>区域<input name="region" maxlength="40" placeholder="气象如江西；地层如 Jiangxi"></label><button type="submit">查找资料</button></form><p data-region-summary role="status"></p><div class="table-scroll" data-region-results></div><div class="actions"><button type="button" data-back disabled>上一页</button><button type="button" data-more disabled>下一页</button></div></details>`;
  const form=host.querySelector('form');let page=1,serial=0,filters=new URLSearchParams(new FormData(form));
  const get=async()=>{const ticket=++serial;const params=new URLSearchParams(filters);params.set('page',page);const d=await request(base+'/regional?'+params);if(!host.isConnected||ticket!==serial)return;
    const climate=filters.get('kind')==='weather';host.querySelector('[data-region-summary]').textContent=d.source?`匹配 ${d.total} 条 · 第 ${d.page}/${d.pages||1} 页。${d.scope}`:'区域资料尚未导入。';
    host.querySelector('[data-region-results]').innerHTML=d.items.length?`<table><thead><tr><th>名称</th><th>区域</th><th>${climate?'站点 / 版本':'岩性 / 地质时期'}</th><th>${climate?'质量 / 原始文件':'年代（Ma，原始字段）'}</th></tr></thead><tbody>${d.items.map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(climate?r.region_name:r.province||'—')}</td><td>${esc(climate?r.station+' / '+r.edition:(r.lithology_pattern||'—')+' / '+(r.period||'—'))}</td><td>${climate?`${esc(status[r.status]||r.status)} · ${r.status==='QA_PASSED'?`<a href="/api${base}/regional/${esc(r.id)}.epw">下载已检查 EPW</a>`:`<a href="${esc(r.source_url)}" target="_blank" rel="noopener">原来源</a>`}`:`${esc(r.endAge??'—')} – ${esc(r.begAge??'—')}`}</td></tr>`).join('')}</tbody></table>`:'<p>没有匹配资料。</p>';
    host.querySelector('[data-back]').disabled=page<=1;host.querySelector('[data-more]').disabled=page>=d.pages;};
  form.onsubmit=e=>{e.preventDefault();page=1;filters=new URLSearchParams(new FormData(form));action(get,e.submitter);};
  host.querySelector('[data-back]').onclick=e=>{page--;action(get,e.target);};host.querySelector('[data-more]').onclick=e=>{page++;action(get,e.target);};
  host.querySelector('details').addEventListener('toggle',e=>{if(e.currentTarget.open&&!serial)action(get);});
}
