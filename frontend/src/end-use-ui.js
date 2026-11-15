import {request,post,escape as esc,number as num} from './api.js';
const labels={'Electricity':'电力','Natural Gas':'天然气','Additional Fuel':'其他燃料','District Cooling':'区域供冷（热量）','District Heating':'区域供热（热量）'};
export function endUseMarkup(record,base){
 if(record?.status!=='calculated_model_end_uses'||!record.summary)return '<p role="status">来源失效或暂不可核验，数值已撤下。</p>';
 const s=record.summary,cols=Object.keys(s.carrier_totals);
 return `<h3>${esc(record.input.name)}</h3><p>${esc(record.input.purpose)}</p><p>${num(s.hours,0)} 小时 · kWh；逐时计量完整时使用逐时积分，否则显示原表舍入值。电、燃料与冷热量分别列出。</p>${s.model.ideal_systems.length?`<p class="warning">包含理想系统：${s.model.ideal_systems.map(esc).join('、')}。区域冷热量不能据此认定为真实采购量，更不能按猜测COP换算耗电。</p>`:''}<div class="hourly-table"><table><thead><tr><th>用途</th>${cols.map(c=>`<th>${esc(labels[c]||c)}</th>`).join('')}</tr></thead><tbody>${s.rows.map(r=>`<tr><th>${esc(r.label)}</th>${cols.map(c=>{const v=r.carriers[c],exact=Number.isFinite(v.hourly_meter_kwh);return `<td>${num(exact?v.hourly_meter_kwh:v.tabulated.kwh,4)}<br><small>${exact?'逐时核对':'原表舍入'}</small></td>`;}).join('')}</tr>`).join('')}</tbody></table></div><p><a target="_blank" rel="noopener" href="${esc(base+'/'+record.enduse_id+'/report.html')}">同源报告</a> · <a target="_blank" rel="noopener" href="${esc(base+'/'+record.enduse_id)}">JSON与逐项计量来源</a></p><details><summary>原表值、舍入误差及设备变量映射</summary><pre>${esc(JSON.stringify({sources:record.source_run,reconciliation:s.reconciliation,rows:s.rows,limitations:s.limitations},null,2))}</pre></details>`;
}
export function createEndUseReader({load,draw,isCurrent=()=>true,timeoutMs=10000}){
 let epoch=0,active=null;
 function clear(){epoch++;active?.abort();active=null;draw(null);}
 async function read(id){
  clear();const ticket=epoch,controller=new AbortController();active=controller;let timer;
  try{
   const r=await Promise.race([load(id,controller.signal),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('能耗来源核验超时')),timeoutMs);})]);
   if(ticket===epoch&&isCurrent())draw(r);return r;
  }catch(e){if(ticket!==epoch||!isCurrent())return null;controller.abort();draw(null);throw e;}
  finally{clearTimeout(timer);if(active===controller)active=null;}
 }
 return {read,clear,get pending(){return active!==null;}};
}
export async function endUseWorkspace(state,host){
 const pid=state.project.project_id,base='/projects/'+pid+'/end-use-ledgers';let selected=null,epoch=0,busy=false,disposed=false,historyEpoch=0;
 host.innerHTML='<h3>年度设备与用途能耗账</h3><p>从当前有效的原生年度运行读取用途分项。已声明设备参数仍需工程复核；本账不是实测或节能认证。</p><form data-enduse><label>来源运行<select name="run_id" required></select></label><label>账目名称<input name="name" required minlength="2" maxlength="160"></label><label>分析用途<textarea name="purpose" required minlength="15" maxlength="2000"></textarea></label><button type="submit">建立来源绑定的分项账</button></form><button type="button" data-refresh>刷新来源与账目</button><p data-message role="status"></p><div data-result></div><details><summary>历史账目</summary><div data-history></div><button type="button" data-first>回到最新</button><button type="button" data-next hidden>更早账目</button></details>';
 const form=host.querySelector('form'),message=host.querySelector('[data-message]'),result=host.querySelector('[data-result]');
 const alive=()=>!disposed&&host.isConnected&&state.project?.project_id===pid;
 const reader=createEndUseReader({load:(id,signal)=>request(base+'/'+id,{signal}),draw:r=>{result.innerHTML=r?endUseMarkup(r,'/api'+base):'';},isCurrent:alive});
 function fail(e){reader.clear();message.textContent=e.message;}
 async function historyPage(before=null){
  const ticket=++historyEpoch,list=host.querySelector('[data-history]'),next=host.querySelector('[data-next]');list.textContent='正在读取账目名称…';next.hidden=true;
  try{const page=await request(base+(before===null?'':'?before='+before));if(!alive()||ticket!==historyEpoch)return;
   list.innerHTML=page.records.map(r=>`<button type="button" data-ledger="${esc(r.enduse_id)}">${esc(r.name)} · 点击核验当前来源</button>`).join('')||'<p>尚无账目。</p>';
   list.querySelectorAll('[data-ledger]').forEach(b=>b.onclick=async()=>{epoch++;selected=b.dataset.ledger;try{await reader.read(selected);}catch(e){fail(e);}});
   next.hidden=page.next_before===null;next.onclick=()=>{void historyPage(page.next_before);};
  }catch(e){if(alive()&&ticket===historyEpoch){list.textContent=e.message;next.hidden=true;}}
 }
 async function refresh(){
  const ticket=++epoch;reader.clear();const [runs]=await Promise.all([request('/projects/'+pid+'/runs'),historyPage()]);if(!alive()||ticket!==epoch)return;
  const select=form.querySelector('[name=run_id]'),chosen=select.value;select.innerHTML='<option value="">选择已成功的年度运行</option>'+runs.filter(r=>r.status==='succeeded').map(r=>`<option value="${esc(r.run_id)}"${chosen===r.run_id?' selected':''}>${esc(r.scheme_id)} · ${esc(r.run_id)}</option>`).join('');
  if(selected)await reader.read(selected);
 }
 host.querySelector('[data-first]').onclick=()=>{void historyPage();};
 form.oninput=()=>{epoch++;selected=null;reader.clear();};
 form.onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;const ticket=++epoch;selected=null;reader.clear();const button=form.querySelector('[type=submit]');button.disabled=true;message.textContent='正在核对分项、计量来源与总量…';
  try{const data=Object.fromEntries(new FormData(form)),r=await post(base,data);if(!alive()||ticket!==epoch)return;selected=r.enduse_id;await refresh();if(alive())message.textContent='分项账已保存；来源变化后撤下数值。';}
  catch(error){if(alive()&&ticket===epoch)fail(error);}finally{busy=false;if(alive())button.disabled=false;}
 };
 host.querySelector('[data-refresh]').onclick=()=>{void refresh().catch(fail);};
 const visibility=()=>{reader.clear();if(alive()&&!document.hidden&&selected&&!busy)void reader.read(selected).catch(fail);};document.addEventListener('visibilitychange',visibility);
 const timer=setInterval(()=>{if(!alive()){clearInterval(timer);reader.clear();document.removeEventListener('visibilitychange',visibility);}else if(!document.hidden&&selected&&!busy&&!reader.pending)void reader.read(selected).catch(fail);},5000);
 host.disposeEndUse=()=>{disposed=true;epoch++;historyEpoch++;reader.clear();clearInterval(timer);document.removeEventListener('visibilitychange',visibility);};
 try{await refresh();}catch(e){if(alive())fail(e);}
}
