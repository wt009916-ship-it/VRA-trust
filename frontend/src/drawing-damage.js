import {escape as esc, number as num} from './api.js';

export function damageMarkup(analysis){
  if(!analysis)return '';
  const d=analysis.deskew, repairs=analysis.repairs||[];
  return `<section class="damage-summary"><h3>老旧图纸分析</h3><p>倾斜校正 ${num(d.applied_degrees,2)}° · ${d.supporting_lines} 条方向依据 · ${repairs.length} 处断线补接候选 · ${(analysis.manual_bridges||[]).length} 条人工补接</p><p>原图与比例保持不变。红色虚线表示补接提议，紫色为有依据的人工补接；可能是门洞、破损或标注，须回源核对。大面积缺页、不可见空间与完整性仍未知。</p><details><summary>图像质量与分析依据</summary><pre>${esc(JSON.stringify({quality:analysis.quality,deskew:d,coordinate_transform:analysis.coordinate_transform,manual_bridges:analysis.manual_bridges,rules_sha256:analysis.rules_sha256},null,2))}</pre></details><details><summary>逐处补接记录 · ${repairs.length}</summary><ul>${repairs.map(r=>`<li><code>${esc(r.id)}</code> · 新增线墨 ${r.added_pixel_count} 像素 · 上限 ${num(r.maximum_requested_gap_m)} m · 待复核</li>`).join('')}</ul></details></section>`;
}

export function damageOverlay(analysis){
  return (analysis?.repairs||[]).map(r=>`<polygon class="plan-damage" points="${r.polygon_px.map(p=>p.join(',')).join(' ')}"><title>${esc(r.id)} · 断线补接提议，非已证实墙体</title></polygon>`).join('')+(analysis?.manual_bridges||[]).map(r=>`<line class="plan-manual-bridge" x1="${r.source_endpoints_px[0][0]}" y1="${r.source_endpoints_px[0][1]}" x2="${r.source_endpoints_px[1][0]}" y2="${r.source_endpoints_px[1][1]}"><title>${esc(r.basis)} · 人工补接假设</title></line>`).join('');
}
