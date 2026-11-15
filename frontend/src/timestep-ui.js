import {request,post,escape as esc} from './api.js';
const steps=[1,2,3,4,5,6,10,12,15,20,30,60];
const verdicts={within_declared_threshold:'声明阈值内',exceeds_declared_threshold:'存在超限小时'};
const number=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('zh-CN',{maximumFractionDigits:6}):'—';

export function timestepMarkup(record,base){
  if(record?.status!=='assessed_model_sensitivity'||!record.summary)return '<p role="status">当前检查不可用或来源已失效，数值已撤下。</p>';
  const s=record.summary;
  return `<h3>${esc(record.input.name)} · ${esc(verdicts[s.verdict]||s.verdict)}</h3><p>${esc(record.input.purpose)}</p><p>覆盖${esc(s.hours)}个原生小时。阈值由你声明；不是规范限值或精度认证。</p>${s.pairs.map(pair=>`<details><summary>每小时${esc(pair.coarse_steps_per_hour)}步 → ${esc(pair.fine_steps_per_hour)}步：${esc(verdicts[pair.verdict]||pair.verdict)}</summary><div class="hourly-table"><table><thead><tr><th>范围 / 对象 / 指标</th><th>最大差</th><th>超限小时</th><th>期间积分差 kWh</th></tr></thead><tbody>${pair.results.map(r=>`<tr><th>${esc(r.scope)} / ${esc(r.entity)} / ${esc(r.metric)}</th><td>${number(r.maximum_absolute_difference)} ${esc(r.difference_unit)}</td><td>${esc(r.hours_exceeding_threshold)}</td><td>${number(r.energy_difference_kWh)}</td></tr>`).join('')}</tbody></table></div></details>`).join('')}<p><a target="_blank" rel="noopener" href="${esc(base+'/'+record.timestep_id+'/report.html')}">打开同源报告</a> · <a target="_blank" rel="noopener" href="${esc(base+'/'+record.timestep_id)}">完整JSON与峰值时刻</a></p><details><summary>阈值、来源与适用范围</summary><pre>${esc(JSON.stringify({thresholds:record.input.thresholds,sources:record.source_runs,limitations:s.limitations},null,2))}</pre></details>`;
}

export function createStudyReader({load,draw,isCurrent=()=>true}){
  let generation=0;
  return {clear(){generation++;draw(null);},async read(id){const token=++generation;draw(null);try{const r=await load(id);if(token===generation&&isCurrent())draw(r);return r;}catch(e){if(token!==generation||!isCurrent())return null;draw(null);throw e;}}};
}

export async function timestepWorkspace(state,host){
  const pid=state.project.project_id,base='/projects/'+pid+'/timestep-studies';
  const idfs=state.evidence.filter(e=>e.type==='idf');
  host.innerHTML=`<h3>检查时间步对结果的影响</h3><p>先下载只改变时间步的副本，核对后上传并审查，再运行。建议使用独立检查项目，将原模型与两份副本分别登记到三个方案位置；步长变化不代表节能改造。</p><div class="form-grid"><label>源IDF<select data-model><option value="">请选择来源</option>${idfs.map(e=>`<option value="${esc(e.source_file)}">${esc(e.name)} · ${esc(e.scheme_id)}</option>`).join('')}</select></label><label>每小时步数<select data-steps><option value="">请选择</option>${steps.map(n=>`<option value="${n}">${n}步（${60/n}分钟）</option>`).join('')}</select></label></div><p><a data-download aria-disabled="true">下载时间步副本</a>（原文件保留，仍需人工审查）</p><button type="button" data-refresh>刷新可选运行与当前结果</button><form data-study><label>检查名称<input name="name" required minlength="2" maxlength="160"></label><label>用途及阈值依据<textarea name="purpose" required minlength="15" maxlength="2000"></textarea></label><fieldset><legend>选择2或3次已成功运行</legend><div data-runs></div></fieldset><div class="form-grid">${[['temperature_absolute_K','温度绝对差限 K','0'],['load_absolute_W','负荷绝对差限 W','0'],['load_relative_pct','负荷相对差限 %','0'],['near_zero_W','相对差停用分母阈值 W','0.000001']].map(([name,label,min])=>`<label>${label}<input name="${name}" type="number" step="any" min="${min}" required></label>`).join('')}</div><label><input name="include_ideal" type="checkbox">同时比较完整理想空调显潜热/新风/回收热率（两边均须具备输出）</label><p>负荷逐时采用绝对限与相对限中的较大者；接近零时仅用绝对限。没有预填规范阈值。</p><button type="submit">创建来源绑定的检查</button></form><p data-message role="status"></p><div data-result></div><details><summary>已保存的检查</summary><div data-history></div></details>`;
  const form=host.querySelector('[data-study]'),result=host.querySelector('[data-result]'),message=host.querySelector('[data-message]');let selected=null,busy=false,timer=null,disposed=false,intent=0;
  const alive=()=>!disposed&&host.isConnected&&state.project?.project_id===pid;
  const reader=createStudyReader({load:id=>request(base+'/'+id),draw:r=>{result.innerHTML=r?timestepMarkup(r,'/api'+base):'';},isCurrent:alive});
  const fail=e=>{reader.clear();message.textContent=e.message;};
  function download(){const e=idfs.find(e=>e.source_file===host.querySelector('[data-model]').value),n=Number(host.querySelector('[data-steps]').value),a=host.querySelector('[data-download]');a.removeAttribute('href');a.setAttribute('aria-disabled','true');if(e&&steps.includes(n)){a.href='/api/projects/'+encodeURIComponent(pid)+'/files/'+encodeURIComponent(e.source_file)+'/timestep.idf?steps='+n+'&expected_source_hash='+encodeURIComponent(e.hash);a.setAttribute('aria-disabled','false');}}
  host.querySelector('[data-model]').onchange=download;host.querySelector('[data-steps]').onchange=download;
  async function refresh(){
    const [runs,history]=await Promise.all([request('/projects/'+pid+'/runs'),request(base)]);if(!alive())return;
    const chosen=new Set([...form.querySelectorAll('[name=run_ids]:checked')].map(x=>x.value));
    host.querySelector('[data-runs]').innerHTML=runs.filter(r=>r.status==='succeeded').map(r=>`<label><input name="run_ids" type="checkbox" value="${esc(r.run_id)}"${chosen.has(r.run_id)?' checked':''}>${esc(r.scheme_id)} · ${esc(r.run_id)}</label>`).join('')||'<p>尚无当前有效的成功运行。</p>';
    host.querySelector('[data-history]').innerHTML=history.map(r=>`<button type="button" data-study-id="${esc(r.timestep_id)}">${esc(r.input.name)} · ${esc(r.status)}</button>`).join('')||'<p>尚无检查。</p>';
    host.querySelectorAll('[data-study-id]').forEach(b=>b.onclick=async()=>{intent++;selected=b.dataset.studyId;try{await reader.read(selected);}catch(e){fail(e);}});
    if(selected)await reader.read(selected);
  }
  form.oninput=()=>{intent++;selected=null;reader.clear();};
  form.onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;const ticket=++intent;const button=form.querySelector('[type=submit]');button.disabled=true;selected=null;reader.clear();message.textContent='正在核对真实来源与完整逐时数据…';
    try{const data=new FormData(form),ids=data.getAll('run_ids');if(ids.length<2||ids.length>3)throw Error('请选择2或3次不同运行。');const thresholds=Object.fromEntries(['temperature_absolute_K','load_absolute_W','load_relative_pct','near_zero_W'].map(k=>[k,Number(data.get(k))]));const r=await post(base,{name:data.get('name'),purpose:data.get('purpose'),run_ids:ids,include_ideal:data.get('include_ideal')==='on',thresholds});if(!alive()||ticket!==intent)return;selected=r.timestep_id;await reader.read(selected);if(!alive()||ticket!==intent)return;message.textContent='检查已保存；这不等于一般收敛或实楼精度证明。';await refresh();}catch(error){if(alive()&&ticket===intent)fail(error);}finally{busy=false;if(alive())button.disabled=false;}};
  host.querySelector('[data-refresh]').onclick=async()=>{intent++;reader.clear();try{await refresh();message.textContent='已核对当前来源。';}catch(e){fail(e);}};
  async function poll(){if(!alive())return;try{if(selected&&!busy)await reader.read(selected);}catch(e){if(alive())fail(e);}finally{if(alive())timer=setTimeout(poll,5000);}}
  host.disposeTimestep=()=>{disposed=true;intent++;clearTimeout(timer);reader.clear();};
  try{await refresh();}catch(e){fail(e);}if(alive())timer=setTimeout(poll,5000);
}