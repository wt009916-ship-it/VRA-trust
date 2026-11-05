import {request,post,escape as esc} from './api.js';

const units=['kg','t','m','cm','mm','m2','m3','item'];
const input=(name,label,extra='')=>`<label>${label}<input name="${name}" ${extra}></label>`;
const select=(name,label,options)=>`<label>${label}<select name="${name}">${Object.entries(options).map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></label>`;
const unitOptions=Object.fromEntries(units.map(x=>[x,x]));
const numeric='type="number" min="0" step="any"';
const value=(scope,key)=>scope.querySelector(`[name="${key}"]`).value;
const number=(scope,key)=>value(scope,key)===''?null:Number(value(scope,key));
const text=v=>esc(v??'—');
const quantityText=v=>text(v===null?null:String(v).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, ''));
const statuses={calculated:'材料成本已计算',incomplete:'资料不完整',stale:'来源或计算器已变更'};

export async function materialCostWorkspace(state,host,action){
  const base='/projects/'+state.project.project_id;
  let importId=null;
  host.innerHTML=`<div class="view-heading"><div><h1>工程量与材料成本</h1><p>从数量、损耗和报价逐项复算。当前合计仅覆盖材料清单，不自动加入人工、机械、运输或税额。</p></div></div>
    <div class="actions"><label>导入清单 JSON（保留原件）<input id="cost-import" type="file" accept=".json"></label><button id="cost-export" type="button">导出输入草稿</button></div><p id="cost-import-note" role="status"></p>
    <form id="cost-form"><h2>范围与价格口径</h2><div class="form-grid">${input('name','清单名称','required maxlength="160"')}${input('as_of','估价日期','type="date" required')}${select('currency','报价币种',{CNY:'人民币 CNY',USD:'美元 USD',EUR:'欧元 EUR'})}${select('tax_basis','所有报价的含税口径',{excluded:'报价不含税（不自动计算税额）',included:'报价已含税（不重复加税）'})}</div>
    <p>项目地区：${esc(state.project.building.region)}。报价地区须与项目一致，不自动换汇。</p><label>功能范围与数量口径<textarea name="functional_scope" required minlength="10" placeholder="说明同一改造范围、材料功能与计量条件；不把不同功能方案直接当作等效替代。"></textarea></label><label>明确排除的费用（每行一项）<textarea name="exclusions" required placeholder="例如人工、机械、运输、管理费用；逐项核对后填写。"></textarea></label>
    <h2>材料清单</h2><p>未知数值留空。已确认无损耗、无扣减时填写0；按件采购在计入损耗后逐行向上取整。</p><div id="cost-lines"></div><div class="actions"><button type="button" id="cost-add">添加材料</button><button class="primary" type="submit">计算并保存清单</button></div></form>
    <div id="cost-result" aria-live="polite"></div><h2>历史清单与替换比较</h2><div id="cost-history"></div><label>比较基准<select id="cost-baseline"></select></label><button id="cost-compare">比较选中清单</button><div id="cost-comparison" aria-live="polite"></div>`;
  const form=host.querySelector('#cost-form'),lines=host.querySelector('#cost-lines');
  function add(data){
    const row=document.createElement('fieldset');row.dataset.lineId=data?.line_id||'line-'+crypto.randomUUID();
    row.innerHTML=`<legend>材料及计量</legend><div class="form-grid">${input('material_id','材料标识（相同材料用同一标识）','required maxlength="100"')}${input('line_name','材料名称','required maxlength="200"')}${select('mode','数量取得方式',{direct:'直接录入净数量',rectangle:'矩形面积（扣除洞口等）',cuboid:'长方体体积（扣除空洞等）'})}${select('measure_unit','工程量单位',unitOptions)}</div><div data-direct>${input('quantity','净数量',numeric)}</div><div data-geometry hidden><div class="form-grid">${input('length','长度',numeric)}${input('width','宽度',numeric)}<div data-height>${input('height','高度 / 厚度',numeric)}</div>${select('dimension_unit','几何尺寸单位',{m:'m',cm:'cm',mm:'mm'})}${input('count','相同构件数量','type="number" min="1" step="1"')}${input('deduction','合计扣减（面积用m²，体积用m³）',numeric)}</div></div>
      <div class="form-grid">${input('waste_ratio','损耗比例（如0.05表示5%）',numeric+' max="1"')}${input('waste_basis','损耗依据','required minlength="5"')}</div>${input('quantity_source','数量来源与定位','required minlength="5"')}
      <h3>报价</h3><div class="form-grid">${input('quote_id','报价编号','required maxlength="100"')}${input('unit_price','每计价单位单价',numeric)}${select('quote_unit','计价单位',unitOptions)}${input('version','报价版本','required maxlength="100"')}${input('valid_from','报价有效起日','type="date" required')}${input('valid_until','报价有效止日','type="date" required')}</div>${input('price_source','报价来源与定位','required minlength="5"')}
      <div data-density hidden><p>质量与体积换算需要有来源的密度；空缺时不计算本项金额。</p><div class="form-grid">${input('density_kg_m3','密度 kg/m³',numeric)}${input('density_source','密度来源','minlength="5"')}</div></div>
      <details><summary>绑定数量、报价或密度的来源证据</summary>${state.evidence.map(e=>`<label class="check-option"><input name="evidence_ids" type="checkbox" value="${e.evidence_id}">${esc(e.name)} · v${e.revision} · ${esc(e.review_state)}</label>`).join('')||'<p>尚无项目证据。来源将按用户声明保留。</p>'}</details><button type="button" data-remove>移除此项</button>`;
    lines.append(row);row.querySelector('[data-remove]').onclick=()=>row.remove();
    function densityNeeded(){const a=value(row,'measure_unit'),b=value(row,'quote_unit');return (a==='m3'&&['kg','t'].includes(b))||(b==='m3'&&['kg','t'].includes(a));}
    function setActive(selector,active){const group=row.querySelector(selector);group.hidden=!active;group.querySelectorAll('input,select').forEach(el=>el.disabled=!active);}
    function updateDensity(){setActive('[data-density]',densityNeeded());}
    function mode(){const m=value(row,'mode');setActive('[data-direct]',m==='direct');setActive('[data-geometry]',m!=='direct');setActive('[data-height]',m==='cuboid');const u=row.querySelector('[name=measure_unit]');u.disabled=m!=='direct';if(m!=='direct')u.value=m==='rectangle'?'m2':'m3';updateDensity();}
    row.querySelector('[name=mode]').onchange=mode;row.querySelector('[name=measure_unit]').onchange=updateDensity;row.querySelector('[name=quote_unit]').onchange=updateDensity;
    row.read=()=>{
      const m=value(row,'mode');const measure={mode:m,unit:value(row,'measure_unit'),source:value(row,'quantity_source')};
      if(m==='direct')measure.quantity=number(row,'quantity');
      else Object.assign(measure,{length:number(row,'length'),width:number(row,'width'),dimension_unit:value(row,'dimension_unit'),count:number(row,'count'),deduction:number(row,'deduction')},m==='cuboid'?{height:number(row,'height')}:{});
      return {line_id:row.dataset.lineId,material_id:value(row,'material_id'),name:value(row,'line_name'),measure,waste_ratio:number(row,'waste_ratio'),waste_basis:value(row,'waste_basis'),
        ...(densityNeeded()?{density_kg_m3:number(row,'density_kg_m3'),density_source:value(row,'density_source')||null}:{}),
        evidence_ids:[...row.querySelectorAll('[name=evidence_ids]:checked')].map(el=>el.value),
        quote:{quote_id:value(row,'quote_id'),unit_price:number(row,'unit_price'),per_unit:value(row,'quote_unit'),version:value(row,'version'),valid_from:value(row,'valid_from'),valid_until:value(row,'valid_until'),source:value(row,'price_source'),region:state.project.building.region,currency:value(form,'currency'),tax_basis:value(form,'tax_basis')}};
    };
    if(data){
      const v={...data,...data.measure,...data.quote,line_name:data.name,mode:data.measure.mode,measure_unit:data.measure.unit,quote_unit:data.quote.per_unit,quantity_source:data.measure.source,price_source:data.quote.source};
      for(const el of row.querySelectorAll('input:not([type=checkbox]),select'))if(el.name in v)el.value=v[el.name]??'';
      row.querySelectorAll('[name=evidence_ids]').forEach(el=>el.checked=data.evidence_ids?.includes(el.value));
    }
    mode();
  }
  function draft(){return {name:value(form,'name'),as_of:value(form,'as_of'),currency:value(form,'currency'),tax_basis:value(form,'tax_basis'),region:state.project.building.region,functional_scope:value(form,'functional_scope'),exclusions:value(form,'exclusions').split('\n').map(s=>s.trim()).filter(Boolean),import_file_id:importId,lines:[...lines.children].map(row=>row.read())};}
  function populate(b){for(const key of ['name','as_of','currency','tax_basis','functional_scope'])form.elements[key].value=b[key];form.elements.exclusions.value=b.exclusions.join('\n');importId=b.import_file_id||null;lines.innerHTML='';b.lines.forEach(add);}
  function render(record){
    if(!host.isConnected)return;const r=record.result;
    host.querySelector('#cost-result').innerHTML=`<h2>${esc(record.input.name)} · ${statuses[record.status]}</h2>${r?`<p>材料清单合计：<strong>${text(r.material_total)} ${esc(r.currency)}</strong> · ${r.tax_basis==='included'?'报价已含税':'报价不含税'}</p><p>${r.material_total===null?'存在缺项，不能给出完整总价。':'仅覆盖声明材料范围；来源为用户声明，非正式工程总报价。'}</p><div class="table-scroll"><table><tr><th>材料</th><th>净量</th><th>损耗后用量</th><th>计价数量</th><th>金额</th></tr>${r.rows.map(x=>`<tr><td>${esc(x.name)}</td><td>${quantityText(x.net_quantity)} ${esc(x.unit)}</td><td>${quantityText(x.purchase_quantity)} ${esc(x.unit)}</td><td>${quantityText(x.quantity_in_quote_unit)} ${esc(x.quote_unit)}</td><td>${text(x.amount)}</td></tr>`).join('')}</table></div>${r.missing_lines.length?'<p>缺项：'+r.missing_lines.map(esc).join('、')+'</p>':''}<details><summary>材料汇总、舍入规则和计算过程</summary><p>${esc(r.rounding)}</p><pre>${esc(JSON.stringify({materials:r.materials,rows:r.rows},null,2))}</pre></details><ul>${r.limitations.map(x=>'<li>'+esc(x)+'</li>').join('')}</ul>`:'<p>来源、项目或计算器已变更，旧结果不用于当前决策。</p>'}<p><a href="/api${base}/material-costs/${record.cost_id}" target="_blank" rel="noopener">完整JSON</a> · <a href="/api${base}/material-costs/${record.cost_id}/report.html" target="_blank" rel="noopener">打印清单报告</a></p>`;
  }
  async function history(){
    const records=await request(base+'/material-costs');if(!host.isConnected)return;
    host.querySelector('#cost-history').innerHTML=records.map(r=>`<p><label class="check-option"><input type="checkbox" value="${r.cost_id}" ${r.status==='calculated'?'':'disabled'}>${esc(r.input.name)} · ${statuses[r.status]} · ${text(r.result?.material_total)} ${esc(r.input.currency)}</label><button data-show-cost="${r.cost_id}">查看</button><button data-copy-cost="${r.cost_id}">复制为替换方案</button></p>`).join('')||'<p>尚无材料清单。</p>';
    host.querySelector('#cost-baseline').innerHTML='<option value="">请选择基准清单</option>'+records.filter(r=>r.status==='calculated').map(r=>`<option value="${r.cost_id}">${esc(r.input.name)}</option>`).join('');
    host.querySelectorAll('[data-show-cost]').forEach(b=>b.onclick=()=>action(async()=>render(await request(base+'/material-costs/'+b.dataset.showCost))));
    host.querySelectorAll('[data-copy-cost]').forEach(b=>b.onclick=()=>action(async()=>{const r=await request(base+'/material-costs/'+b.dataset.copyCost);if(host.isConnected)populate({...r.input,name:r.input.name+' · 替换方案'});}));
  }
  host.querySelector('#cost-add').onclick=()=>add();
  form.onsubmit=e=>{e.preventDefault();action(async()=>{const r=await post(base+'/material-costs',draft());render(r);await history();if(host.isConnected)host.querySelector('#cost-result').scrollIntoView({block:'start'});},e.submitter);};
  host.querySelector('#cost-import').onchange=e=>action(async()=>{const f=e.target.files[0];if(!f)return;if(f.size>2*1024*1024)throw Error('清单超过2 MiB');const checked=await post(base+'/material-cost-validation',JSON.parse(await f.text()));if(checked.region!==state.project.building.region)throw Error('清单地区与项目不一致');const data=new FormData();data.append('file',f);const file=await request(base+'/files',{method:'POST',body:data});if(host.isConnected){populate({...checked,import_file_id:file.file_id});host.querySelector('#cost-import-note').textContent='清单已按字段格式校验，原文件已保留；请复核后计算保存。';}});
  host.querySelector('#cost-export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(draft(),null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='material-cost-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  host.querySelector('#cost-compare').onclick=e=>action(async()=>{const selected=[...host.querySelectorAll('#cost-history input:checked')].map(el=>el.value),baseline=host.querySelector('#cost-baseline').value;if(!selected.includes(baseline))throw Error('请在选中清单中指定基准');const r=await post(base+'/material-cost-comparisons',{cost_ids:[baseline,...selected.filter(id=>id!==baseline)]});if(host.isConnected)host.querySelector('#cost-comparison').innerHTML=`<p>${esc(r.note)}</p><table><tr><th>方案</th><th>材料总额 ${esc(r.currency)}</th><th>相对基准差额</th><th>下降比例%</th></tr>${r.results.map(x=>`<tr><td>${esc(x.name)}</td><td>${text(x.material_total)}</td><td>${text(x.difference_from_baseline)}</td><td>${text(x.reduction_pct)}</td></tr>`).join('')}</table>`;},e.currentTarget);
  await history();
}
