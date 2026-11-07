import {escape as esc,number as fmt} from './api.js';

const labels={ambiguous_opening_relationships:'开洞关系有歧义，几何量未知',measured_mesh:'已取得近似几何量',partial_mesh:'网格未通过体积核验，体积未知',no_body_representation:'没有Body表示',missing_placement:'缺少位置',missing_or_unsupported_length_unit:'长度单位未知',ambiguous_body_representations:'Body表示冲突',native_geometry_failed:'原生几何转换失败',declared_normalized:'声明值已换算',missing_unit:'缺少对应单位',conflicting_project_units:'项目单位冲突',unit_dimension_mismatch:'单位量纲不符',invalid_quantity_value:'数量值无效',effective_declaration:'当前声明',overridden_by_instance:'被实例覆盖',ambiguous:'来源冲突'};
const label=value=>esc(labels[value]||value||'—');

export function topologyMarkup(topology){
  if(!topology)return '<p>此条结果未提供网格拓扑核验回执。</p>';
  const reasons={open_or_invalid_topology:'存在开边、方向不一致、重复面或退化面',non_manifold_vertex:'顶点邻域不是单一连续面环',triangle_intersection_or_nonlocal_contact:'发现三角面自交、壳间相交或非相邻接触',incompatible_shell_orientation:'内外壳方向与嵌套关系不一致',zero_or_inconsistent_shell_volume:'壳体积退化或嵌套关系不一致',topology_pairs_budget:'三角面检查预算已耗尽',topology_nodes_budget:'空间检索预算已耗尽',topology_ray_tests_budget:'壳包含关系检查预算已耗尽',shell_count_budget:'壳数量超出核验范围',ambiguous_shell_containment_rays:'壳包含关系无法无歧义确定'};
  const checked=topology.status==='checked';
  return `<section aria-label="网格体积核验"><h5>网格体积核验</h5><p>${checked?'通过当前网格检查；仍为近似几何量，需工程复核。':'体积不交付：'+esc(reasons[topology.reason]||topology.reason||'尚未完成核验')+'。'}</p><p>检查同一构件网格的流形、面接触、壳嵌套与方向；不自动修补，也不合并其他构件。</p>${topology.triangle_indices?`<p>问题网格三角面索引（从0开始）：${topology.triangle_indices.map(esc).join('、')}。原件与完整回执保持可追溯。</p>`:''}${topology.shells?.length?`<details><summary>壳关系与诊断积分（${topology.shells.length}壳）</summary><p>正负积分用于核查方向，不是可直接计价的工程量；嵌套深度从外壳0开始。</p><table><thead><tr><th>壳</th><th>嵌套深度</th><th>有向积分 m³</th><th>方向</th></tr></thead><tbody>${topology.shells.slice(0,12).map(s=>`<tr><td>${s.shell}</td><td>${s.depth}</td><td>${fmt(s.signed_volume_m3,6)}</td><td>${s.orientation_consistent?'一致':'冲突'}</td></tr>`).join('')}</tbody></table><p>最多显示12壳，完整回执见导出JSON。</p></details>`:''}</section>`;
}

export function openingMarkup(geometry){
  if(!geometry)return '';
  const check=geometry.opening_relationships;
  const issues={duplicate_void_relationship:'同一洞口与宿主之间存在重复开洞关系',multiple_hosts_for_opening:'同一洞口被绑定到多个宿主',missing_void_relationship:'洞口缺少宿主开洞关系'};
  return (geometry.mesh_status==='empty_mesh'?'<p role="status">开洞处理后未取得可测量网格，体积保持未知；不能将空网格当作已验证的零体积。</p>':'')+
    (check?'<details><summary>洞口与宿主关系</summary>'+
      (check.issues.length?'<p>关系有歧义，暂不交付几何量。</p><ul>'+check.issues.map(v=>'<li>'+esc(issues[v]||v)+'</li>').join('')+'</ul>':'<p>已检查声明关系的唯一性；不代表几何相交或专业扣减规则通过。</p>')+
      '<ul>'+check.relations.slice(0,30).map(r=>'<li>关系 #'+esc(r.relation_id)+'：宿主 #'+esc(r.host_id)+' → 洞口 #'+esc(r.opening_id)+'</li>').join('')+'</ul><p>最多显示30条；完整关系见JSON。</p></details>':'');
}

export function ifcObjectMarkup(product,geometry){
  if(!product)return '<p>未取得该构件。</p>';
  const quantities=product.quantities||[],properties=product.properties||[];
  return `<h4>${esc(product.name||product.type)} · #${product.id}</h4><p>GlobalId：${esc(product.global_id)}；空间包含 #${product.container_id??'未声明'}。</p><p>空间父级关系：${(product.spatial_relations||[]).map(r=>esc(`${r.parent_name||r.parent_type} #${r.parent_id} · ${r.relation_type} #${r.relation_id}`)).join('；')||'未声明'}。</p><p>类型来源：${(product.types||[]).map(t=>esc(`${t.name||t.type} #${t.id}（关系 #${t.relation_id}）`)).join('；')||'未分配'}</p><h5>模型声明工程量</h5><p>这些数值来自原模型，不是下方网格计算的答案。实例与类型来源均保留；存在冲突时不自动挑选。</p>${quantities.length?`<div class="table-scroll"><table><thead><tr><th>数量 / 来源</th><th>原始值</th><th>换算值 / 单位</th><th>单位来源 / 状态</th><th>选用关系</th></tr></thead><tbody>${quantities.slice(0,100).map(q=>`<tr><td>${esc(q.set+' / '+q.path.join(' / '))}<br>#${q.source_id} · ${q.scope==='type'?'类型':'实例'}</td><td>${esc(q.value??'—')}</td><td>${fmt(q.value_si,6)} ${esc(q.si_unit||'')}</td><td>${esc(q.unit_source||'未知')} #${q.unit_id??'—'}<br>${label(q.status)}</td><td>${label(q.selection)}</td></tr>`).join('')}</tbody></table></div>`:'<p>未提供声明数量。</p>'}<h5>近似几何测量</h5><p>${label(geometry?.status)}；网格表面积（三角面之和，非并集面积） ${fmt(geometry?.surface_area_m2,6)} m²；体积 ${fmt(geometry?.volume_m3,6)} m³。表面积不是建筑面积，体积不是材料净用量。</p>${openingMarkup(geometry)}${topologyMarkup(geometry?.topology)}<details><summary>几何表示、位置与网格缺口</summary><pre>${esc(JSON.stringify(geometry||{},null,2))}</pre></details><details><summary>原始属性及类型覆盖（${properties.length}项，最多显示100项）</summary><div class="table-scroll"><table><thead><tr><th>属性</th><th>原值</th><th>来源</th><th>选用关系</th></tr></thead><tbody>${properties.slice(0,100).map(p=>`<tr><td>${esc(p.set+' / '+p.path.join(' / '))}</td><td>${esc(p.value??'—')} ${esc(p.explicit_unit||'')}</td><td>#${p.source_id} · ${p.scope==='type'?'类型':'实例'}</td><td>${label(p.selection)}</td></tr>`).join('')}</tbody></table></div></details><p>完整属性、公式及单位定义可从本条记录JSON导出。${(product.declaration_issues||[]).map(label).join('；')}</p>`;
}

export function ifcMarkup(result,recordId){
  const geometry=result.ifc_geometry;if(!geometry)return '';
  const rows=geometry.objects;
  const measured=rows.filter(r=>r.status==='measured_mesh').length;
  return `<section class="cad-geometry"><h3>IFC构件与工程量来源</h3><p>${rows.length}个产品 · ${measured}个取得经网格检查的近似量 · ${rows.length-measured}个存在几何缺口。不同构件可能重叠；不相加为建筑总量。</p><label>查看构件来源、数量与属性<select data-ifc-record="${esc(recordId)}">${result.objects.map(p=>`<option value="${p.id}">#${p.id} · ${esc(p.type)} · ${esc(p.name||'未命名')}</option>`).join('')}</select></label><div data-ifc-detail="${esc(recordId)}">${ifcObjectMarkup(result.objects[0],rows.find(r=>r.id===result.objects[0]?.id))}</div><details><summary>全部构件几何摘要（最多300项）</summary><div class="table-scroll"><table><thead><tr><th>构件</th><th>表面积 m²</th><th>体积 m³</th><th>状态</th></tr></thead><tbody>${rows.slice(0,300).map(r=>`<tr><td>#${r.id} ${esc(r.type)}<br>${esc(r.name||'')}</td><td>${fmt(r.surface_area_m2,6)}</td><td>${fmt(r.volume_m3,6)}</td><td>${label(r.status)}</td></tr>`).join('')}</tbody></table></div></details><ul>${geometry.limitations.map(x=>'<li>'+esc(x)+'</li>').join('')}</ul></section>`;
}
