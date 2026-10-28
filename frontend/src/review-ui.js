import {request,post,escape as esc} from './api.js';

const kinds={BLOCKER:'待补齐输入',ASSUMPTION:'显式假设',EVIDENCE_GAP:'外推依据待补'};
const decisions={needs_information:'要求补证',accepted_scenario:'接受本情景假设',rejected:'不接受此情景'};
const categories={geometry:'几何',use:'用途与计面积',display:'名称',source_and_boundary:'来源与边界',thermal:'热工与工况',equipment:'设备',sources:'源文件',scope_exclusions:'排除范围',reviewed:'复核状态',review_note:'复核说明',name:'模型名称',space_added:'新增空间',space_removed:'移除空间'};

export function filterFindings(findings,{kind='',query='',pending=false}={}){
  const q=query.trim().toLocaleLowerCase();
  return findings.filter(f=>(!kind||f.kind===kind)&&(!pending||!f.review)&&(!q||[f.title,f.action,f.locator,...f.room_ids,...f.ifc_global_ids,...(f.source_element_ids||[])].filter(Boolean).join(' ').toLocaleLowerCase().includes(q)));
}

export function findingMarkup(f){
  return `<article class="review-finding" data-finding="${esc(f.finding_id)}"><header><span class="review-kind ${esc(f.kind.toLowerCase())}">${esc(kinds[f.kind])}</span><span class="subtle">${f.review?'已记录处置 · 未解除工程要求':f.prior_review_stale?'旧复核已失效 · 当前版本待复核':'当前版本待复核'}</span></header><h3>${esc(f.title)}</h3><p>${esc(f.action)}</p>${f.room_ids.length?`<p class="review-location">空间 ${f.room_ids.slice(0,8).map(esc).join('、')}${f.room_ids.length>8?' 等'+f.room_ids.length+'个':''} <button data-focus-room="${esc(f.room_ids[0])}">定位空间</button></p>`:''}${f.locator?'<p class="review-location">定位：'+esc(f.locator)+'</p>':''}<details><summary>源标识与记录依据</summary><pre>${esc(JSON.stringify({ifc_global_ids:f.ifc_global_ids,storey_ids:f.storey_ids,source_element_ids:f.source_element_ids,basis:f.basis},null,2))}</pre></details>${f.review?`<blockquote>${esc(f.review.note)}<small>${esc(decisions[f.review.decision])} · ${esc(f.review.actor)} · ${esc(f.review.recorded_at)}</small></blockquote>`:''}<footer><button data-review-finding="${esc(f.finding_id)}">${f.review?'修订处置记录':'记录复核处置'}</button><button data-review-history="${esc(f.finding_id)}">历史</button></footer></article>`;
}

export async function engineeringReviewWorkspace(state,host,action,modal,openRoom){
  host.classList.add('engineering-review-view');
  const pid=state.project.project_id,base='/projects/'+pid+'/engineering-review';let data=null;
  host.innerHTML='<div class="view-heading"><div><span class="eyebrow">ENGINEERING REVIEW</span><h1>工程复核与交接</h1><p>把输入缺口、假设与版本变化交给下一位工程师。</p></div><button data-review-refresh>刷新核对</button></div><div data-review-body role="status">正在读取来源和当前模型版本…</div>';
  const refresh=async()=>{
    const next=await request(base);if(!host.isConnected||state.project?.project_id!==pid)return;data=next;
    const diff=data.changes;
    host.querySelector('[data-review-body]').innerHTML=`<div class="review-summary">${Object.entries(kinds).map(([key,label])=>`<div><span>${label}</span><strong>${data.counts[key]||0}</strong></div>`).join('')}<div><span>当前处置记录</span><strong>${data.current_dispositions}<small> / ${data.findings.length}</small></strong></div></div><section class="review-boundary"><strong>资料复核快照 · 工程成果未签署</strong><p>处置不会解除计算阻断或把假设升级为实测；本页不代替几何校验、现场校准与工程签署。</p><small>模型 ${data.model?'v'+data.model.revision+' · '+data.model.rooms+'空间':'未建立'} · 核对时间 ${esc(new Date(data.generated_at).toLocaleString('zh-CN',{hour12:false}))}</small><details><summary>适用范围、版本与来源</summary><ul>${data.limitations.map(text=>'<li>'+esc(text)+'</li>').join('')}</ul><code>${esc(data.snapshot_hash)}</code>${data.sources.map(s=>`<p>${esc(s.name)} · ${s.valid?'原件哈希匹配':'来源无效'}<code>${esc(s.expected_sha256)}</code></p>`).join('')||'<p>尚无模型/证据源文件。</p>'}</details></section><div class="review-actions"><a href="/api${base}" target="_blank" rel="noopener">JSON快照</a><a href="/api${base}/comparison-inputs.json" target="_blank" rel="noopener">同题输入清单</a><a href="/api${base}/report.html" target="_blank" rel="noopener">交接报告</a><a href="/api${base}/issues.bcfzip" download>BCF问题清单</a><a href="/api${base}/handoff.zip" download>下载交接包</a></div><p class="subtle">导出时重新核验当前资料；包内包含JSON、HTML、BCF问题、同题输入协议及哈希清单，不含项目原件、相机视点或工程签名。</p><details class="review-diff"><summary>模型版本变化 ${diff.from_revision?'v'+diff.from_revision+' → v'+diff.to_revision:'· 暂无前版'}</summary><p>${esc(diff.basis)}</p>${diff.changes.length?`<div class="table-wrap"><table><thead><tr><th>范围</th><th>字段 / 空间</th><th>之前</th><th>之后</th></tr></thead><tbody>${diff.changes.map(c=>`<tr><td>${esc(categories[c.category]||c.category)}</td><td>${esc(c.field)} ${esc(c.room_id||'全局')}</td><td>${esc(JSON.stringify(c.before))}</td><td>${esc(JSON.stringify(c.after))}</td></tr>`).join('')}</tbody></table></div>`:'<p>暂无字段变化记录。</p>'}<p class="subtle">${esc(data.limitations[2])}</p></details><div class="review-filters"><label>筛选性质<select data-review-kind><option value="">全部性质</option>${Object.entries(kinds).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label><label>搜索问题或源ID<input type="search" data-review-query placeholder="楼层、空间、IFC GlobalId"></label><label class="check-option"><input type="checkbox" data-review-pending>仅当前版本待复核</label></div><p data-review-count></p><div class="review-findings" data-review-list></div>`;
    const paint=()=>{
      const rows=filterFindings(data.findings,{kind:host.querySelector('[data-review-kind]').value,query:host.querySelector('[data-review-query]').value,pending:host.querySelector('[data-review-pending]').checked});
      host.querySelector('[data-review-count]').textContent=`当前显示 ${rows.length} / ${data.findings.length} 项`;
      host.querySelector('[data-review-list]').innerHTML=rows.map(findingMarkup).join('')||'<p class="empty">当前筛选没有复核项。可调整筛选；空列表不表示工程已可签发。</p>';
      host.querySelectorAll('[data-focus-room]').forEach(b=>b.onclick=()=>openRoom(b.dataset.focusRoom));
      host.querySelectorAll('[data-review-history]').forEach(b=>b.onclick=()=>action(async()=>{const records=await request(base+'/findings/'+b.dataset.reviewHistory+'/history');modal('复核处置历史',records.length?records.map(r=>`<article><h3>v${r.revision} · ${esc(decisions[r.decision])}</h3><p>${esc(r.note)}</p><small>${esc(r.actor)} · ${esc(r.recorded_at)}</small><code>${esc(r.snapshot_hash)}</code></article>`).join(''):'<p>尚无处置记录。</p>');},b));
      host.querySelectorAll('[data-review-finding]').forEach(b=>b.onclick=()=>{
        const item=data.findings.find(f=>f.finding_id===b.dataset.reviewFinding),snapshot=data.snapshot_hash;
        const dialog=modal('记录复核处置',`<p>${esc(item.title)}</p><p class="form-note">处置绑定当前资料快照，不解除阻断、不作为工程签署；修改来源或模型后重新核对。</p><form data-review-form><label>处置<select name="decision"><option value="needs_information">要求补证</option>${item.kind==='ASSUMPTION'?'<option value="accepted_scenario">接受本情景假设</option>':''}<option value="rejected">不接受此情景</option></select></label><label>复核依据 · 必填<textarea name="note" required minlength="10" maxlength="2000" placeholder="说明核对范围、原件依据与仍需补充的资料">${esc(item.review?.note||'')}</textarea></label><button class="primary" type="submit">保存到此版本</button></form>`);
        const form=dialog.querySelector('form');form.onsubmit=e=>{e.preventDefault();action(async()=>{const f=new FormData(form);await post(base+'/dispositions',{snapshot_hash:snapshot,finding_id:item.finding_id,expected_revision:item.review_revision,decision:f.get('decision'),note:f.get('note')});dialog.close();await refresh();},e.submitter);};
      });
    };
    host.querySelectorAll('[data-review-kind],[data-review-query],[data-review-pending]').forEach(el=>el.oninput=paint);paint();
  };
  host.querySelector('[data-review-refresh]').onclick=e=>action(refresh,e.currentTarget);await refresh();
}
