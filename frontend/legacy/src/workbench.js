import './workbench.css'
import {escapeHTML as esc,fmt} from './safety.js'
import {comparisonToDashboard} from './apiAdapter.js'
import {loadDashboard,loadRunResult} from './jsonLoader.js'
import {state} from './config.js'
import {updateRunStatusUI} from './runStatus.js'
let cases=[],runs=[],busy=false,current=null
const $=id=>document.getElementById(id)
async function api(path,body){
  const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{cache:'no-store'})
  const data=await r.json();if(!r.ok)throw new Error(data.error || r.statusText);return data
}
const message=(s,error=false)=>{ $('vra-message').textContent=s;$('vra-message').style.color=error?'#b42318':'#1f654f' }
const chosenCase=()=>cases.find(c=>c.case_id===$('vra-case').value)
const profile=()=>$('vra-factor').value
function clearComparison(){current=null;$('vra-results').textContent='请运行或选择有效的基准与改造结果，再生成比较。';$('vra-report').disabled=true;$('vra-view').disabled=true;state.validatedComparison=null;loadRunResult({status:'queued',run_id:'awaiting_comparison'})}
async function refresh(){
  const data=await api('/api/runs');runs=data.runs
  if(current && current.ids.some(id=>!runs.some(r=>r.run_id===id&&r.status==='succeeded')))clearComparison()
  const caseId=$('vra-case').value
  $('vra-history').innerHTML='<table><thead><tr><th>方案／运行</th><th>状态</th><th>证据</th></tr></thead><tbody>'+[...runs].reverse().map(r=>`<tr><td>${esc(r.scheme_id || '')}<br><small>${esc(r.run_id)}</small></td><td>${esc(r.status)}${r.error?'<br>'+esc(r.error.message):''}</td><td><a href="/api/runs/${encodeURIComponent(r.run_id)}/evidence">下载</a></td></tr>`).join('')+'</tbody></table>'
  $('vra-select-runs').innerHTML=(chosenCase()?.schemes||[]).map(s=>{
    const valid=runs.filter(r=>r.case_id===caseId&&r.scheme_id===s.scheme_id&&r.status==='succeeded'&&r.carbon?.profile_id===profile()).sort((a,b)=>String(b.finished_at).localeCompare(String(a.finished_at)))
    return `<label>${esc(s.name)} <select data-run-scheme="${esc(s.scheme_id)}"><option value="">不选择</option>${valid.map((r,i)=>`<option value="${esc(r.run_id)}" ${i===0?'selected':''}>${esc(r.run_id)}</option>`).join('')}</select></label>`
  }).join('')
  document.querySelectorAll('[data-run-scheme]').forEach(el=>{el.onchange=clearComparison})
}
async function compare(){
  const ids=[...document.querySelectorAll('[data-run-scheme]')].map(s=>s.value).filter(Boolean)
  const data=await api('/api/compare?runs='+ids.map(encodeURIComponent).join(','))
  current={data,ids};state.validatedComparison=current
  $('vra-report').disabled=false;$('vra-view').disabled=false
  $('vra-results').innerHTML='<div class="vra-scroll"><table><thead><tr><th>方案</th><th>年场地能耗 kWh</th><th>EUI</th><th>节能率</th><th>运行碳 tCO₂</th><th>碳口径</th></tr></thead><tbody>'+data.results.map(r=>`<tr><td>${esc(r.scheme_name)}</td><td>${fmt(r.metrics.annual_energy_kwh)}</td><td>${fmt(r.metrics.eui_kwh_m2a)}</td><td>${fmt(r.saving_rate_pct)}%</td><td>${fmt(r.carbon.operating_carbon_kg==null?null:r.carbon.operating_carbon_kg/1000)}</td><td>${esc(r.carbon.status)}${r.carbon.scenario?'／因子为教学假设':''}</td></tr>`).join('')+'</tbody></table></div><p>'+esc(data.recommendation)+'</p><p class="muted">'+esc(data.ccer_note)+' 造价未提供，不参与排序。建筑外观为历史示意，不能当作该IDF的几何复原。</p>'
  $('vra-cost-run').innerHTML=data.results.map(r=>`<option value="${esc(r.run_id)}">${esc(r.scheme_name)}</option>`).join('')
  const dashboard=comparisonToDashboard(data,chosenCase())
  state.dataMode='live';state.runMeta={status:'succeeded',run_id:data.baseline_run_id,source:'参考算例真实仿真；碳口径见工作台；外观为示意'}
  loadDashboard(dashboard,'baseline');updateRunStatusUI(state.runMeta)
  message('比较已核验。每个数字均可沿run_id下载输入、SQL、日志与计算明细。')
}
async function runAll(){
  if(busy)return;busy=true;$('vra-compare').disabled=true;$('vra-run').disabled=true;$('vra-case').disabled=true;$('vra-factor').disabled=true;clearComparison()
  try{
    for(const s of chosenCase().schemes){
      const job=await api('/api/runs',{case_id:chosenCase().case_id,scheme_id:s.scheme_id,profile_id:profile()})
      message('运行 '+s.name+'，'+job.run_id)
      let result
      for(let i=0;i<360;i++){
        await new Promise(r=>setTimeout(r,1000));result=await api('/api/runs/'+job.run_id)
        if(!['queued','running'].includes(result.status))break
      }
      if(result?.status!=='succeeded')throw new Error(result?.error?.message||'任务未成功或等待超时，请刷新历史记录')
      await refresh()
    }
    await compare()
  }catch(e){message(e.message,true);loadRunResult({status:'failed',run_id:'batch_failed',error:{message:e.message}})}
  finally{busy=false;$('vra-compare').disabled=false;$('vra-run').disabled=false;$('vra-case').disabled=false;$('vra-factor').disabled=false;await refresh().catch(()=>{})}
}
function guard(fn){return async()=>{try{await fn()}catch(e){message(e.message,true)}}}
export function mountWorkbench(){
  const launch=document.createElement('button');launch.id='vra-launch';launch.textContent='计算与证据工作台';document.body.appendChild(launch)
  const pane=document.createElement('main');pane.id='vra-workbench';pane.hidden=true
  pane.innerHTML=`<button class="vra-close" id="vra-close">返回三维展示</button><h1>稀土智暖 · 集成工作台</h1><p>资料与模型 → 真实仿真 → 成本与碳评价 → 方案比较 → 可复核交付</p><div class="vra-notice">本版包含官方工程参考算例，不是南昌实测建筑。保留原三维展示；自动残图识别、完整生命周期核算、正式碳信用开发仍待完成。</div>
  <section class="vra-section"><h2>1. 运行与比较</h2><div class="vra-controls"><select id="vra-case" aria-label="选择案例"></select><select id="vra-factor" aria-label="选择碳因子"></select><button id="vra-run">重新运行三方案</button><button id="vra-refresh">刷新运行记录</button></div><div id="vra-message" role="status"></div><div id="vra-select-runs"></div><div class="vra-controls"><button id="vra-compare">比较所选运行</button><button id="vra-report" disabled>打开可打印报告</button><button id="vra-view" disabled>查看三维与构造</button></div><div id="vra-results"></div></section>
  <div class="vra-grid"><section class="vra-section"><h2>2. 成本情景</h2><p class="muted">费用单独计算，不混入没有报价依据的综合推荐。能源价格均为元/kWh；天然气不是元/m³。</p><label>方案 <select id="vra-cost-run"></select></label><label>电价 <input id="vra-elec" type="number" min="0" step="0.01" placeholder="元/kWh"></label><label>燃气热值口径价格 <input id="vra-gas" type="number" min="0" step="0.01" placeholder="元/kWh"></label><label>初投资 <input id="vra-invest" type="number" min="0" placeholder="元"></label><label>年限 <input id="vra-years" type="number" min="1" max="100" value="20"></label><label>折现率 <input id="vra-discount" type="number" min="0" max="1" step="0.01" value="0.03"></label><button id="vra-calc-cost">计算费用情景</button><pre id="vra-cost-out">尚未计算</pre></section>
  <section class="vra-section"><h2>3. 碳资产潜力与收益情景</h2><p>参考算例正式开发资格未评估。工程减排量不自动等于可签发量；此处只做明确假设的经济情景。</p><label>假设可开发数量（吨）<input id="vra-quantity" type="number" min="0"></label><label>价格情景（元/吨）<input id="vra-price" type="number" min="0"></label><label>开发费用（元）<input id="vra-devcost" type="number" min="0"></label><label>监测核验费用（元）<input id="vra-monitorcost" type="number" min="0"></label><label>资格与数量假设依据<textarea id="vra-eligibility" rows="2" placeholder="仅教学假设，或说明实际依据与尚未满足的条件"></textarea></label><button id="vra-calc-value">计算假设收益</button><pre id="vra-value-out">无正式碳信用或收益承诺</pre></section></div>
  <div class="vra-grid"><section class="vra-section"><h2>4. 残缺资料与补充清单</h2><p class="muted">本阶段为人工确认入口，不是自动识图。status可取documented、measured、assumed、missing；有据参数须填写source。</p><textarea id="vra-gaps" rows="7"></textarea><button id="vra-check-gaps">生成资料缺口清单</button><pre id="vra-gaps-out">待确认</pre><h3>稀土材料候选</h3><p>保留候选与验证支线。暂无合格实测参数的稀土材料不参与当前数值排序。</p></section><section class="vra-section"><h2>5. 因子更新与历史证据</h2><p class="muted">对所选费用方案复用完整能耗证据，仅重算当前选择的因子配置。生成新run_id，不覆盖原始运行。</p><button id="vra-recarbon">仅重算所选方案的碳</button><div id="vra-history" class="vra-history"></div></section></div>`
  document.body.appendChild(pane)
  $('vra-gaps').value=JSON.stringify([{name:'外墙材料参数',status:'missing',decision_sensitive:true,next_action:'查询竣工资料或确认现场测量方案'},{name:'建筑面积',status:'documented',source:'参考模型SQL Building Area；真实项目需另核'}],null,2)
  const numeric=id=>{if($(id).value.trim()==='')throw new Error('请填写 '+id.replace('vra-',''));const n=Number($(id).value);if(!Number.isFinite(n))throw new Error('数值不合法');return n}
  launch.onclick=guard(async()=>{pane.hidden=!pane.hidden;if(!pane.hidden){if(!cases.length){const d=await api('/api/cases');cases=d.cases;$('vra-case').innerHTML=cases.map(c=>`<option value="${esc(c.case_id)}">${esc(c.name)}</option>`).join('');$('vra-factor').innerHTML=Object.values(d.carbon_profiles).map(p=>`<option value="${esc(p.profile_id)}">${esc(p.name)}</option>`).join('');$('vra-factor').value='reference_scenario'}await refresh();const h=await api('/api/health');message(h.engine_available?'引擎可用。可核对已有运行或启动独立仿真。':h.engine_error,!h.engine_available)}})
  $('vra-close').onclick=()=>pane.hidden=true
  $('vra-case').onchange=$('vra-factor').onchange=guard(async()=>{clearComparison();await refresh()})
  $('vra-run').onclick=runAll;$('vra-refresh').onclick=guard(refresh);$('vra-compare').onclick=guard(compare)
  $('vra-report').onclick=()=>current&&window.open('/api/report?runs='+current.ids.join(','),'_blank','noopener')
  $('vra-view').onclick=()=>{if(!current)return;pane.hidden=true;$('start-screen')?.remove();window.navigateToDetail('baseline')}
  $('vra-calc-cost').onclick=guard(async()=>{$('vra-cost-out').textContent=JSON.stringify(await api('/api/cost',{run_id:$('vra-cost-run').value,tariffs:{Electricity:numeric('vra-elec'),'Natural Gas':numeric('vra-gas')},investment:numeric('vra-invest'),horizon:numeric('vra-years'),discount:numeric('vra-discount')}),null,2)})
  $('vra-calc-value').onclick=guard(async()=>{$('vra-value-out').textContent=JSON.stringify(await api('/api/carbon-value',{quantity_t:numeric('vra-quantity'),price:numeric('vra-price'),development_cost:numeric('vra-devcost'),monitoring_cost:numeric('vra-monitorcost'),eligibility_evidence:$('vra-eligibility').value}),null,2)})
  $('vra-check-gaps').onclick=guard(async()=>{$('vra-gaps-out').textContent=JSON.stringify(await api('/api/evidence-gaps',{items:JSON.parse($('vra-gaps').value)}),null,2)})
  $('vra-recarbon').onclick=guard(async()=>{const d=await api('/api/recalculate',{run_id:$('vra-cost-run').value,profile_id:profile()});await refresh();message('已生成碳复算 '+d.run_id+'；EnergyPlus调用次数为0。请重新选择并比较同一因子口径。')})
}
