import {escape as esc, number as fmt, request, post} from './api.js';

const reasons={operand_geometry_unavailable:'至少一个构件未取得可核验几何量',union_topology_unverified:'并集网格尚未通过拓扑核验',
 input_triangle_budget_exceeded:'输入网格超过本次计算预算',output_triangle_budget_exceeded:'并集网格超过输出预算',
 unsupported_relative_placement:'构件位置关系暂不支持或有循环',relative_coordinate_range_exceeded:'相对坐标跨度过大',
 boolean_result_unavailable:'几何运算未取得有效并集',boolean_operation_failed:'几何运算失败',
 union_volume_consistency_failed:'两种体积核算结果不一致',operand_world_volume_mismatch:'构件位置变换前后体积不一致',
 boolean_operand_rejected:'几何运算库拒绝该构件',negative_overlap_deduction:'重叠扣除量校验失败'};

export const unionQuantity=value=>typeof value==='number'&&Number.isFinite(value)&&value!==0&&Math.abs(value)<1e-6?value.toExponential(6):fmt(value,8);

export function unionRecordMarkup(record,base){
 const r=record.result,valid=record.status==='measured'&&r?.status==='measured';
 const reason=record.status==='stale'?'来源或计算版本已变化，旧数量已撤下':reasons[r?.reason]||r?.reason||'尚未完成核验';
 const url=base+'/ifc-unions/'+record.union_id;
 return `<article class="ifc-union-record"><h3>${valid?'已核验所选网格并集':'几何并集未知'}</h3>
 <p>构件 ${record.product_ids.map(id=>'#'+esc(id)).join('、')} · ${esc(record.source.name)}</p>
 ${valid?`<dl><dt>构件体积之和</dt><dd>${unionQuantity(r.sum_operand_volume_m3)} m³</dd><dt>几何并集体积</dt><dd>${unionQuantity(r.union_volume_m3)} m³</dd><dt>重叠重复扣除量</dt><dd>${unionQuantity(r.overlap_deduction_m3)} m³</dd></dl>`:`<p role="status">${esc(reason)}；数量 —。</p>`}
 <p>仅覆盖这些构件；不是材料净用量、计价工程量或合规认证。不同材料交叠的归属未分配。</p>
 <details><summary>来源与计算依据</summary><p>原件 SHA256：<code>${esc(record.source.hash)}</code></p><p>读取记录：${esc(record.cad_id)}；计算版本：${esc(record.parser_hash)}</p>
 ${r?`<p>采用原模型开洞；不额外套用专业扣减规则。计算内核 ${esc(r.library_version)}；数值一致性容差 ${esc(r.numeric_consistency_tolerance_m3??'—')} m³。容差不是原图精度保证。</p>`:''}</details>
 <p><a target="_blank" rel="noopener" href="/api${esc(url)}">完整 JSON</a> · <a target="_blank" rel="noopener" href="/api${esc(url)}/report.html">核验报告</a></p></article>`;
}

export function unionWorkspaceMarkup(records){
 const options=records.filter(r=>r.status==='parsed'&&r.result?.format==='IFC');
 return `<section aria-label="选定构件几何并集"><h2>选定构件几何并集</h2>
 <p>选择同一 IFC 中的 2–64 个实体，比较体积之和与去除重叠后的几何并集。洞口不单独计入。</p>
 <form data-union-form><label>来源 IFC 读取记录<select name="cad" required><option value="">请选择已读取 IFC</option>${options.map(r=>`<option value="${esc(r.cad_id)}">${esc(r.source.name)} · ${esc(r.cad_id.slice(-8))}</option>`).join('')}</select></label>
 <label>参与并集的构件（可多选）<select name="products" multiple size="7" required aria-describedby="union-selection-help"></select></label>
 <p id="union-selection-help">Windows 可按 Ctrl 或 Shift 多选；只计算明确选中的构件。</p>
 <p data-union-selection>尚未选择构件。</p><button class="primary" disabled>核算几何并集</button></form>
 <p data-union-status role="status"></p><div data-union-history aria-live="polite"></div></section>`;
}

export function mountUnionWorkspace(records,host,base,action){
 host.innerHTML=unionWorkspaceMarkup(records);
 const form=host.querySelector('[data-union-form]'),source=form.elements.cad,products=form.elements.products;
 const status=host.querySelector('[data-union-status]'),history=host.querySelector('[data-union-history]');
 let closed=false,epoch=0,busy=false,sourceCurrent=true;
 function selection(){
  const ids=[...products.selectedOptions].map(o=>Number(o.value));
  host.querySelector('[data-union-selection]').textContent=ids.length?'已选 '+ids.length+' 个构件：'+ids.map(x=>'#'+x).join('、'):'尚未选择构件。';
  form.querySelector('button').disabled=busy||!sourceCurrent||ids.length<2||ids.length>64;
  return ids;
 }
 source.onchange=()=>{
  epoch++;sourceCurrent=true;status.textContent='';
  const record=records.find(r=>r.cad_id===source.value);
  products.innerHTML=(record?.result?.objects||[]).filter(p=>p.eligible_for_union).map(p=>`<option value="${p.id}">#${p.id} · ${esc(p.name||p.type)} · ${esc(p.type)}</option>`).join('');
  selection();void refresh();
 };
 products.onchange=()=>{selection();};
 async function refresh(){
  const ticket=++epoch,cadId=source.value;
  try{
   const [saved,current]=await Promise.all([request(base+'/ifc-unions'),cadId?request(base+'/cad-inspections/'+cadId):Promise.resolve(null)]);
   if(closed||!host.isConnected||ticket!==epoch)return;
   sourceCurrent=!current||current.status==='parsed';selection();
   if(!sourceCurrent)status.textContent='所选来源已失效，请重新读取原文件后计算。';
   history.innerHTML=saved.map(r=>unionRecordMarkup(r,base)).join('')||'<p>尚无已保存的并集核验。</p>';
  }catch(error){
   if(closed||!host.isConnected||ticket!==epoch)return;
   sourceCurrent=false;selection();history.innerHTML='<p>当前状态无法核验，历史数量暂不展示。</p>';status.textContent=error.message;
  }
 }
 form.onsubmit=event=>{
  event.preventDefault();const ids=selection(),cadId=source.value;
  if(busy||!sourceCurrent||ids.length<2||ids.length>64)return;
  busy=true;epoch++;selection();status.textContent='正在核验所选构件及并集网格…';
  action(async()=>{
   try{
    const saved=await post(base+'/ifc-unions',{cad_id:cadId,product_ids:ids});
    if(closed||!host.isConnected)return;
    status.textContent=saved.status==='measured'?'核验已保存。下方记录列明本次实际参与的构件。':'核验已保存，但未取得可交付的并集量，请查看原因。';
    await refresh();
   }catch(error){
    if(!closed&&host.isConnected){status.textContent='本次计算失败：'+error.message;await refresh();}
    throw error;
   }finally{busy=false;if(!closed&&host.isConnected)selection();}
  });
 };
 void refresh();
 const timer=setInterval(()=>{if(!host.isConnected){closed=true;clearInterval(timer);}else if(!busy)void refresh();},5000);
 return ()=>{closed=true;epoch++;clearInterval(timer);};
}
