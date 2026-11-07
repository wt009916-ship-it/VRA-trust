from pathlib import Path
p=Path('frontend/src/ifc-union-ui.js');s=p.read_text(encoding='utf-8')
marker='export function unionRecordMarkup(record,base){'
s=s.replace(marker,"export const unionQuantity=value=>typeof value==='number'&&Number.isFinite(value)&&value!==0&&Math.abs(value)<1e-6?value.toExponential(6):fmt(value,8);\n\n"+marker)
for name in ['sum_operand_volume_m3','union_volume_m3','overlap_deduction_m3']:s=s.replace('fmt(r.'+name+',8)','unionQuantity(r.'+name+')')
p.write_text(s,encoding='utf-8',newline='\n')
p=Path('frontend/src/style.css');p.write_text(p.read_text(encoding='utf-8')+'\n#cad [data-union-form]{display:grid;gap:14px;max-width:820px;margin:16px 0}#cad [data-union-form] label{display:grid;gap:8px;min-width:0}#cad [data-union-form] select{width:100%;min-width:0;padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--bg)}#cad [data-union-form] select[multiple]{min-height:180px}#cad [data-union-form] button{justify-self:start}.ifc-union-record{overflow-wrap:anywhere}.ifc-union-record dl{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 20px;max-width:560px;margin:16px 0}.ifc-union-record dd{margin:0;font-variant-numeric:tabular-nums;font-weight:600}\n',encoding='utf-8',newline='\n')
