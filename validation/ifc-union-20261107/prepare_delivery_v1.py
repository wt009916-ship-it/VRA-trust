import hashlib,json,shutil
from pathlib import Path
repo=Path.cwd();out=repo/'validation/ifc-union-20261107'
assert '1182 passed, 31 skipped' in (out/'backend-full-v1.log').read_text(encoding='utf-8')
assert '1191 passed, 22 skipped' in (out/'linux-backend-v2.log').read_text(encoding='utf-8')
p=repo/'docs/IFC_SELECTED_UNION_DELIVERY.md';s=p.read_text(encoding='utf-8').replace('最终完整回归及发布结果以本批日志和release-receipt.json为准。','最终Windows1182通过/31跳过、Linux1191通过/22跳过，均6子测试通过、2个既有警告；每平台6项年度参考依赖检查跳过，其余主要为跨平台专用检查。发布以release-receipt.json为准。')
p.write_text(s,encoding='utf-8',newline='\n')
summary='2026-11-07选定IFC并集更新：显式2–64构件、体积和/并集/重复扣除、隔离执行、JSON/HTML及来源失效撤下已实现。Windows1182/Linux1191及各6子测试、100前端通过；双平台8基础数值/1边接触拒绝、6扩展及6公开对独立核验。大坐标旋转精度修复，圆柱近似误差约0.011m³保留；浏览器3文件/原件/390px/失效自动撤下通过。Linux首轮进程回收测试竞态已保留修复。开发复评77，下一批先普通CAD全页失效刷新，再材料计量与Agent/长稳；训练/全局视觉后置。详[交付](IFC_SELECTED_UNION_DELIVERY.md)、[交叉验证](IFC_SELECTED_UNION_CROSSCHECK.md)、[复评](RESCORE_20261107_IFC_UNION.md)。发布以回执为准。\n\n'
for name in ['CURRENT_STATE_AUDIT.md','IMPLEMENTATION_STATUS.md']:
 p=repo/'docs'/name;p.write_text(summary+p.read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
p=repo/'.gitattributes';p.write_text(p.read_text()+'validation/ifc-union-20261107/** -text\n',newline='\n')
for name in ['ifc-union-overlap.png','ifc-union-stale.png']:shutil.copyfile(repo/'output/playwright'/name,out/name)
exclude=('runtime-context','ui-runtime','ui-server','source-preservation','pr-body','release-')
files=[p for p in out.iterdir() if p.is_file() and p.suffix in {'.py','.js','.json','.log','.txt','.ifc','.png','.md'} and not p.name.startswith(exclude)]
pub=[repo/'docs'/n for n in ['IFC_SELECTED_UNION_DELIVERY.md','IFC_SELECTED_UNION_CROSSCHECK.md','RESCORE_20261107_IFC_UNION.md']]
def entry(p):return {'path':p.relative_to(repo).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
index={'scope':'Synthetic and public IFC only; no material certification or real-building calibration','score':77,
'evidence_files':[entry(p) for p in sorted(files)],'publications':[entry(p) for p in pub]}
(repo/'docs/IFC_SELECTED_UNION_EVIDENCE.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'evidence_files':len(files),'bytes':sum(p.stat().st_size for p in files)}))
