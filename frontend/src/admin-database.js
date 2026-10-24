import { request, post, escape as esc, number as num } from './api.js';

const labels={id:'记录 ID',name:'名称',username:'用户名',display_name:'显示名称',project_id:'项目 ID',revision:'版本',status:'状态',review_state:'复核',disabled:'停用',user_id:'账号 ID',expires:'有效至',revoked:'撤销',scopes:'授权范围',actor:'执行者',target:'对象',timestamp:'时间',error:'错误',owner:'所属账号',updated_at:'更新时间',created_at:'创建时间'};
export function cell(value,key){
  if(value===null||value===undefined)return '—';
  if((key==='expires'||key==='timestamp')&&typeof value==='number')return esc(new Date(value*1000).toLocaleString());
  if(['updated_at','created_at'].includes(key)&&typeof value==='string'&&!Number.isNaN(Date.parse(value)))return esc(new Date(value).toLocaleString());
  if((key==='id'||key.endsWith('_id'))&&typeof value==='string'&&value.length>26)return esc(value.slice(0,12)+'…'+value.slice(-6));
  if(key==='disabled'||key==='revoked')return value?'是':'否';
  return esc(typeof value==='object'?JSON.stringify(value):value);
}

export async function databaseWorkspace(host,{modal,action,notice},initial='projects',operations=false){
  let collection=initial,page=1,pageSize=20,q='',generation=0;
  const meta=await request('/admin/database');
  const collections=operations?meta.collections.filter(c=>['jobs','audit','imports','inbox'].includes(c.id)):meta.collections;
  host.innerHTML=`<div class="admin-section-heading"><div><h2>${operations?'任务与操作审计':'数据库管理'}</h2><p>${operations?'查询任务状态和账号操作记录。':'直接查询持久化数据、复核历史版本，并管理数据库备份。'}</p></div><span class="admin-pill">${esc(meta.engine)} · ${esc(meta.journal_mode)}</span></div>${operations?'':`<div class="admin-db-stats"><div><small>数据库文件</small><strong>${num(meta.size_bytes/1024/1024)} MB</strong></div><div><small>业务历史版本</small><strong>${num(meta.record_revisions,0)}</strong></div><div><small>数据集合</small><strong>${meta.collections.length}</strong></div><button id="check-database">校验数据库完整性</button></div><p id="database-check" role="status"></p>`}<div class="admin-explorer"><aside class="admin-collections" aria-label="数据库集合">${collections.map(c=>`<button data-collection="${c.id}"><span>${esc(c.label)}</span><small>${c.count}</small></button>`).join('')}</aside><section class="admin-panel admin-records"><form id="database-search" class="admin-toolbar"><label>搜索记录<input name="q" type="search" maxlength="120" placeholder="名称、ID 或状态"></label><button>查询</button><label>每页<select id="database-page-size"><option>20</option><option>50</option><option>100</option></select></label></form><p id="database-caption" role="status"></p><div class="admin-table-wrap"><table class="admin-data-table"><thead id="database-columns"></thead><tbody id="database-rows"></tbody></table></div><div class="admin-pagination"><button id="database-previous">上一页</button><span id="database-page"></span><button id="database-next">下一页</button></div></section></div>${operations?'':`<section class="admin-panel"><div class="admin-section-heading"><div><h2>数据库备份</h2><p>${esc(meta.file_scope)}</p></div><button id="create-backup" class="primary">创建数据库备份</button></div><p>备份包含账号凭据哈希与项目索引，下载后请妥善保管。不会自动覆盖当前数据库。</p><div id="database-backups"></div></section>`}`;
  async function load(){
    const token=++generation;
    host.querySelector('#database-caption').textContent='正在读取数据库…';
    host.querySelectorAll('[data-collection]').forEach(b=>b.classList.toggle('selected',b.dataset.collection===collection));
    const result=await request('/admin/database/collections/'+collection+'?'+new URLSearchParams({page,page_size:pageSize,q}));
    if(token!==generation||!host.isConnected)return;
    const columns=[...new Set(result.items.flatMap(item=>Object.keys(item)))].filter(k=>!(collection==='projects'&&k==='project_id'));
    const detail=['projects','files','evidence','models','materials','imports','studies','searches'].includes(collection);
    host.querySelector('#database-caption').textContent=`${collections.find(c=>c.id===collection)?.label||collection} · 共 ${result.total} 条${detail?'当前记录，点击查看历史版本':'记录'}`;
    host.querySelector('#database-columns').innerHTML='<tr>'+columns.map(k=>`<th>${esc(labels[k]||k)}</th>`).join('')+(detail?'<th>详情</th>':'')+'</tr>';
    host.querySelector('#database-rows').innerHTML=result.items.map(item=>'<tr>'+columns.map(k=>`<td data-column="${esc(k)}" title="${esc(item[k]??'')}" ${k==='id'?'class="mono"':''}>${cell(item[k],k)}</td>`).join('')+(detail?`<td><button data-record="${esc(item.id)}">详情与历史</button></td>`:'')+'</tr>').join('')||'<tr><td>没有匹配的记录</td></tr>';
    host.querySelector('#database-page').textContent=`第 ${page} / ${Math.max(1,Math.ceil(result.total/pageSize))} 页`;
    host.querySelector('#database-previous').disabled=page<=1;host.querySelector('#database-next').disabled=page*pageSize>=result.total;
    host.querySelectorAll('[data-record]').forEach(b=>b.onclick=()=>action(async()=>{
      const r=await request('/admin/database/collections/'+collection+'/'+b.dataset.record);
      const d=modal('记录详情与历史版本',`<label>查看版本<select id="record-revision">${r.history.map((v,i)=>`<option value="${i}" ${i===r.history.length-1?'selected':''}>v${v.revision} · ${esc(v.updated_at||v.timestamp||v.created_at||'')}</option>`).join('')}</select></label><p>历史记录保留来源；页面不直接改写计算和证据数据。</p><pre id="record-json" class="admin-record-json"></pre>`);
      const paint=()=>{d.querySelector('#record-json').textContent=JSON.stringify(r.history[Number(d.querySelector('select').value)],null,2);};d.querySelector('select').onchange=paint;paint();
    },b));
  }
  host.querySelectorAll('[data-collection]').forEach(b=>b.onclick=()=>action(async()=>{collection=b.dataset.collection;page=1;q='';host.querySelector('[name=q]').value='';await load();},b));
  host.querySelector('#database-search').onsubmit=e=>{e.preventDefault();q=new FormData(e.currentTarget).get('q');page=1;action(load,e.submitter);};
  host.querySelector('#database-page-size').onchange=e=>{pageSize=Number(e.target.value);page=1;action(load);};
  host.querySelector('#database-previous').onclick=()=>{page--;action(load);};host.querySelector('#database-next').onclick=()=>{page++;action(load);};
  async function backups(){
    const rows=await request('/admin/database/backups');if(!host.isConnected)return;
    host.querySelector('#database-backups').innerHTML=rows.map(r=>`<article class="admin-backup"><div><strong>${esc(new Date(r.created_at).toLocaleString())}</strong><p>${num(r.size_bytes/1024/1024)} MB · 完整性 ${esc(r.integrity)}</p><small class="mono">SHA256 ${esc(r.sha256)}</small></div><a href="/api/admin/database/backups/${esc(r.id)}/download" download>下载备份</a></article>`).join('')||'<p class="subtle">尚未创建后台备份</p>';
  }
  if(!operations){
    host.querySelector('#check-database').onclick=e=>action(async()=>{const r=await post('/admin/database/check',{});host.querySelector('#database-check').textContent=r.passed?'数据库完整性校验通过 · '+new Date(r.checked_at).toLocaleString():'校验未通过：'+r.results.join('；');},e.currentTarget);
    host.querySelector('#create-backup').onclick=()=>{
      const d=modal('创建数据库备份','<form id="backup-form"><p>创建一致的 SQLite 快照并校验完整性。原项目文件不包含在此数据库快照中。</p><label>管理员当前密码<input name="current_password" type="password" autocomplete="current-password" required minlength="10" maxlength="128"></label><p id="backup-error" class="error-text" role="alert"></p><button class="primary">确认创建备份</button></form>');
      d.querySelector('form').onsubmit=e=>{e.preventDefault();const f=Object.fromEntries(new FormData(e.currentTarget));action(async()=>{try{await post('/admin/database/backups',f);d.close();await backups();notice('数据库备份已创建，完整性校验通过。');}catch(err){d.querySelector('#backup-error').textContent=err.message;}},e.submitter);};
    };
    await backups();
  }
  await load();
}
