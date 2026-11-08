import {escape as esc,request} from './api.js';
import {mountMaterialScenario} from './material-scenarios-ui.js';
import {mountUnionWorkspace, unionQuantity} from './ifc-union-ui.js';

const reasons={cross_material_overlap_ownership_unresolved:'不同材料占用了同一空间，归属尚未解决，不能生成材料汇总量',
 selected_layer_geometry_unavailable:'至少一面所选墙的材料层或几何未通过核验',
 material_union_geometry_unverified:'材料并集未通过几何与体积核验',
 input_triangle_budget_exceeded:'所选材料层网格超过计算预算',layer_budget_exceeded:'所选材料层数量超过本次预算'};

export function materialCollectionMarkup(record,base){
 const r=record.result,valid=record.status==='measured'&&r?.status==='measured';
 const url=base+'/ifc-material-collections/'+record.materialset_id;
 return `<article><h3>${valid?'材料包络去重结果':'材料包络量未知'}</h3>
 <p>所选构件：${record.product_ids.map(id=>'#'+esc(id)).join('、')} · ${esc(record.source.name)}</p>
 ${valid?`<div class="table-scroll"><table><thead><tr><th>模型材料实体</th><th>构件层体积和 m³</th><th>重复扣除 m³</th><th>去重包络 m³</th></tr></thead><tbody>${r.materials.map(m=>`<tr><td>#${esc(m.material_id)} ${esc(m.material_name||'未命名')}</td><td>${unionQuantity(m.source_sum_m3)}</td><td>${unionQuantity(m.overlap_deduction_m3)}</td><td>${unionQuantity(m.union_envelope_m3)}</td></tr>`).join('')}</tbody></table></div>`:`<p role="status">${esc(record.status==='stale'?'来源或计算版本变化，旧数量已撤下':reasons[r?.reason]||'当前无法取得可核验的材料汇总量')}；数量 —。</p>`}
 <p>仅覆盖所选分层构件。同一IFC材料实体去重，同名的不同实体分开保留。材料包络可能含空腔或龙骨间隙，不能直接当作采购净量或计价工程量。</p>
 ${valid?`<button type="button" data-collection-scenario="${esc(record.materialset_id)}">用去重材料比较两套方案</button>`:''}
 <p><a target="_blank" rel="noopener" href="/api${esc(url)}/report.html">材料计量与来源报告</a> · <a target="_blank" rel="noopener" href="/api${esc(url)}">导出JSON</a></p></article>`;
}

export function mountMaterialCollections(records,host,base,action,scenarioHost,historyHost){
 host.onclick=event=>{
  const button=event.target.closest('[data-collection-scenario]');
  if(!button||!host.contains(button)||!scenarioHost)return;
  const ident=button.dataset.collectionScenario;
  action(async()=>{
   const current=await request(base+'/ifc-material-collections/'+encodeURIComponent(ident));
   if(host.isConnected)await mountMaterialScenario(scenarioHost,base,current,historyHost);
  },button);
 };
 return mountUnionWorkspace(records,host,base,action,{
  endpoint:'/ifc-material-collections',maxSelection:16,heading:'多构件材料包络计量',
  description:'选择同一 IFC 中的 2–16 个分层墙、楼板、屋面板或板材，扣除同材料重叠；不同材料交叠时停止汇总并报告冲突。',
  buttonLabel:'核算材料包络',helpId:'material-collection-selection-help',
  productFilter:p=>['IfcWall','IfcWallStandardCase','IfcSlab','IfcSlabStandardCase','IfcPlate','IfcPlateStandardCase'].includes(p.type),recordMarkup:materialCollectionMarkup,
  emptyMessage:'尚无已保存的多构件材料计量。'
 });
}
