import {request,post,escape as esc} from './api.js';
import {carbonBoundaryMarkup,carbonEditorsMarkup,readCarbonEditors,bindCarbonEditors,evidenceSelect} from './material-carbon-ui.js';

const numeric=(data,key)=>{const value=String(data.get(key)??'').trim();return value===''?null:Number(value);};
const text=(data,key)=>String(data.get(key)??'').trim();
const input=(name,label,type='text',extra='',value='')=>`<label>${esc(label)}<input name="${esc(name)}" type="${type}" ${extra} value="${esc(value)}"></label>`;
const select=(name,label,options)=>`<label>${esc(label)}<select name="${esc(name)}">${options.map(([value,label])=>`<option value="${value}">${label}</option>`).join('')}</select></label>`;


export function scenarioSourceShape(source){
 const collection=Boolean(source.materialset_id);
 return collection?{collection:true,rows:'materials',rowId:'material_id',inputId:'source_material_id',sourceId:'materialset_id',excluded:'excluded_materials',endpoint:'/collection-scenarios',recordId:'collectionscenario_id',label:'material'}:
 {collection:false,rows:'layers',rowId:'layer_id',inputId:'layer_id',sourceId:'takeoff_id',excluded:'excluded_layers',endpoint:'/material-scenarios',recordId:'scenario_id',label:'layer'};
}

export function scenarioFormMarkup(takeoff,project,evidence=[]){
 const shape=scenarioSourceShape(takeoff),layers=takeoff.result[shape.rows];
 const alternative=(row,i)=>{
  const p=`a${i}_${row[shape.rowId]}_`;
  return `<fieldset><legend>方案${i+1} · ${esc(row.material_name||'未命名材料')}</legend><div class="scenario-fields">${input(p+'name','拟用材料名称','text','required',row.material_name||'')}${input(p+'solid_fraction','实体比例（0至1，未知留空）','number','min="0.000001" max="1" step="any"')}${input(p+'waste_ratio','采购损耗比例（未知留空）','number','min="0" max="1" step="any"')}${input(p+'density','密度 kg/m³（按质量计价/计碳时需提供）','number','min="0.000001" max="100000" step="any"')}${input(p+'price','单价（未知留空）','number','min="0" step="any"')}${select(p+'quote_unit','计价单位',[['m3','每 m³'],['kg','每 kg'],['t','每 t']])}${input(p+'factor','生产排放因子 kgCO₂e/单位（未知留空）','number','min="0" step="any"')}${select(p+'factor_unit','排放因子分母',[['m3','m³'],['kg','kg'],['t','t']])}</div><details><summary>填写比例、价格和因子来源（必填）</summary><div class="scenario-fields">${input(p+'fraction_source','实体比例依据','text','required minlength="5"')}${input(p+'waste_basis','损耗依据','text','required minlength="5"')}${input(p+'density_source','密度来源（填写密度时必填）')}${input(p+'quote_source','报价来源','text','required minlength="5"')}${input(p+'quote_version','报价版本','text','required')}${input(p+'valid_from','报价有效期起','date','required')}${input(p+'valid_until','报价有效期止','date','required')}${input(p+'factor_source','排放因子来源','text','required minlength="5"')}${input(p+'publisher','因子发布方','text','required minlength="2"')}${input(p+'factor_version','因子版本','text','required')}${input(p+'factor_year','因子年份','number','required min="1900" max="2100"')}${evidenceSelect(p+'source_evidence','绑定材料映射来源证据（可多选）',evidence,true)}${evidenceSelect(p+'factor_evidence','绑定生产因子证据',evidence)}</div></details></fieldset>`;
 };
 return `<section class="material-scenario-workspace" aria-label="材料方案比较"><h2>${shape.collection?'从多墙去重材料建立两套方案':'从本构件建立两套材料方案'}</h2><p>${shape.collection?'去重材料包络体积由服务器读取；同一材料仅映射一次。':'层体积由服务器读取计量记录；'}下方填写的是材料映射及来源。材料生产量来自计量映射；运输、施工、运行和寿命末期按下方明确选择的边界与活动核算。材料替换的结构、耐火和节能等效性需另行复核。</p><form data-material-scenario novalidate><div class="scenario-fields">${input('baseline_name','方案一名称','text','required','方案一')}${input('alternative_name','方案二名称','text','required','方案二')}${input('functional_scope','相同功能范围与比较条件','text','required minlength="10"')}${input('region','地区','text','required',project.building.region)}${select('currency','币种',[['CNY','人民币 CNY'],['USD','美元 USD'],['EUR','欧元 EUR']])}${select('tax_basis','报价税口径',[['excluded','不含税'],['included','含税']])}${input('as_of','计价日期','date','required')}${input('study_years','声明评估期（年）','number','required min="1" max="200"')}${input('method','碳核算方法（须与因子一致）','text','required minlength="3"')}${input('exclusions','材料费用不含内容','text','required','人工、机械、运输等未列入材料报价的费用')}</div>${carbonBoundaryMarkup()}${layers.map(row=>`<details open data-scenario-layer="${row[shape.rowId]}"><summary>${shape.collection?'来源材料实体':'来源层'} #${row[shape.rowId]} · ${esc(row.material_name||'未命名')}（量由服务核验，不可手改）</summary><label><input type="checkbox" name="include_${row[shape.rowId]}" checked>纳入两个方案</label>${input('exclude_'+row[shape.rowId],'若不纳入，填写共同排除理由')}<div data-layer-inputs class="scenario-alternatives">${alternative(row,0)}${alternative(row,1)}</div></details>`).join('')}${carbonEditorsMarkup()}<p>空白数值保持未知；来源文字为用户声明，不自动成为核证资料。</p><button class="primary" type="submit">核验来源并生成两方案报告</button><button type="button" data-close-scenario>收起方案表单</button><p data-scenario-status role="status"></p></form><div data-scenario-links></div></section>`;
}

export function scenarioPayload(data,takeoff){
 const shape=scenarioSourceShape(takeoff);
 const region=text(data,'region'),method=text(data,'method'),currency=text(data,'currency'),tax=text(data,'tax_basis');
 const included=takeoff.result[shape.rows].filter(r=>data.has('include_'+r[shape.rowId]));
 const carbon=readCarbonEditors(data,shape.collection);
 return {[shape.sourceId]:takeoff[shape.sourceId],functional_scope:text(data,'functional_scope'),region,currency,tax_basis:tax,
  as_of:text(data,'as_of'),study_years:numeric(data,'study_years'),method,exclusions:[text(data,'exclusions')],
  [shape.excluded]:takeoff.result[shape.rows].filter(r=>!data.has('include_'+r[shape.rowId])).map(r=>({[shape.inputId]:r[shape.rowId],reason:text(data,'exclude_'+r[shape.rowId])})),
  boundaries:carbon.boundaries,
  alternatives:[0,1].map(i=>({...carbon.alternatives[i],name:text(data,i?'alternative_name':'baseline_name'),[shape.rows]:included.map(row=>{
   const p=`a${i}_${row[shape.rowId]}_`,density=numeric(data,p+'density'),densitySource=text(data,p+'density_source');
   return {[shape.inputId]:row[shape.rowId],material_id:`alternative_${i}_${shape.label}_${row[shape.rowId]}`,name:text(data,p+'name'),
    solid_fraction:numeric(data,p+'solid_fraction'),fraction_source:text(data,p+'fraction_source'),
    waste_ratio:numeric(data,p+'waste_ratio'),waste_basis:text(data,p+'waste_basis'),
    density_kg_m3:density,density_source:densitySource||null,evidence_ids:data.getAll(p+'source_evidence'),
    quote:{quote_id:`quote_${i}_${row[shape.rowId]}`,unit_price:numeric(data,p+'price'),per_unit:text(data,p+'quote_unit'),currency,tax_basis:tax,region,
     valid_from:text(data,p+'valid_from'),valid_until:text(data,p+'valid_until'),source:text(data,p+'quote_source'),version:text(data,p+'quote_version')},
    factor:{factor_id:`factor_${i}_${row[shape.rowId]}`,value:numeric(data,p+'factor'),denominator:text(data,p+'factor_unit'),stage:'production',
     source:text(data,p+'factor_source'),publisher:text(data,p+'publisher'),version:text(data,p+'factor_version'),
     year:numeric(data,p+'factor_year'),region,method,evidence_id:text(data,p+'factor_evidence')||null}};
  })}))};
}

export async function refreshScenarioHistory(host,base,collection=false){
 const shape=scenarioSourceShape(collection?{materialset_id:true}:{});
 if(!host)return;
 try{
  const records=await request(base+shape.endpoint);
  if(!host.isConnected)return;
  host.innerHTML='<h2>'+ (collection?'已保存的多墙材料方案':'已保存的材料方案')+'</h2>'+(records.length?'<ul>'+records.map(r=>`<li><a target="_blank" rel="noopener" href="/api${base}${shape.endpoint}/${encodeURIComponent(r[shape.recordId])}/report.html">${r.names.map(esc).join(' / ')}</a> · ${esc(r.created_at)}</li>`).join('')+'</ul><p>打开报告时核验当前来源；历史记录保留。</p>':'<p>尚无材料方案。先选择构件并完成材料层计量。</p>');
 }catch(error){if(host.isConnected)host.textContent='材料方案历史暂不可读：'+error.message;}
}

export async function mountMaterialScenario(host,base,takeoff,historyHost){
 const shape=scenarioSourceShape(takeoff);
 if(takeoff.status!=='measured'){host.textContent='材料层尚未取得有效计量，不能建立来源绑定方案。';return;}
 const ticket={};host.scenarioTicket=ticket;
 const [project,evidence]=await Promise.all([request(base),request(base+'/evidence')]);
 if(!host.isConnected||host.scenarioTicket!==ticket)return;
 host.innerHTML=scenarioFormMarkup(takeoff,project,evidence);
 const form=host.querySelector('form'),status=host.querySelector('[data-scenario-status]'),links=host.querySelector('[data-scenario-links]');
 bindCarbonEditors(form,takeoff,evidence);
 host.querySelector('[data-close-scenario]').onclick=()=>{host.scenarioTicket=null;host.replaceChildren();};
 for(const layer of form.querySelectorAll('[data-scenario-layer]')){
  const checkbox=layer.querySelector('input[type=checkbox]'),reason=layer.querySelector(`[name="exclude_${layer.dataset.scenarioLayer}"]`);
  checkbox.onchange=()=>{
   for(const control of layer.querySelectorAll('[data-layer-inputs] input,[data-layer-inputs] select'))control.disabled=!checkbox.checked;
   reason.required=!checkbox.checked;reason.minLength=5;
   layer.querySelector('[data-layer-inputs]').hidden=!checkbox.checked;
  };
 }
 form.addEventListener('invalid',event=>{let parent=event.target.parentElement;while(parent&&parent!==form){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}},true);
 form.onsubmit=async event=>{
  event.preventDefault();if(!form.reportValidity())return;
  const button=event.submitter;button.disabled=true;links.replaceChildren();status.textContent='正在核验原件、计量和方案来源…';
  try{
   const record=await post(base+shape.endpoint,scenarioPayload(new FormData(form),takeoff));
   if(!host.isConnected||host.scenarioTicket!==ticket)return;
   status.textContent=record.status==='calculated'?'两方案已计算。报告打开时会重新核验来源。':record.status==='incomplete'?'存在缺失数据，不能形成完整比较。报告会列出缺项。':'来源发生变化，结果不可用。';
   void refreshScenarioHistory(historyHost,base,shape.collection);
   if(record.status!=='stale')links.innerHTML=`<p><a target="_blank" rel="noopener" href="/api${base}${shape.endpoint}/${record[shape.recordId]}/report.html">打开两方案报告</a> · <a target="_blank" rel="noopener" href="/api${base}${shape.endpoint}/${record[shape.recordId]}">导出输入与逐层计算 JSON</a></p>`;
  }catch(error){if(host.scenarioTicket===ticket)status.textContent=error.message;}
  finally{if(button.isConnected)button.disabled=false;}
 };
 host.scrollIntoView({block:'start',behavior:'smooth'});
}
