import hashlib,json,shutil,subprocess
from pathlib import Path
repo=Path.cwd();out=repo/'validation/ifc-net-20261107'
summary='2026-11-07 IFC开洞更新：修复全覆盖洞口错误返回毛体积，空网格保持未知；重复/多宿主/孤立开洞关系拒绝交付几何量并保留实体定位。Windows1152/Linux1161通过，各6子测试；96前端通过。双平台8合成案例含6数值与2拒绝，公开模型109个独立量核对；真实无头浏览器3文件、原件哈希/匿名401/390px通过，GUI启动及局部标题遮挡仍开放。跨构件净量未实现，评分76保持。详[交付](IFC_OPENINGS_DELIVERY.md)、[交叉验证](IFC_OPENINGS_CROSSCHECK.md)、[复评](RESCORE_20261107_IFC_OPENINGS.md)。发布以本批release回执为准；训练及整体视觉后置。\n\n'
for name in ['CURRENT_STATE_AUDIT.md','IMPLEMENTATION_STATUS.md']:
 p=repo/'docs'/name;p.write_text(summary+p.read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
p=repo/'.gitattributes';p.write_text(p.read_text()+'validation/ifc-net-20261107/** -text\n',newline='\n')
selected=[]
for p in out.iterdir():
 if p.is_file() and p.suffix in ['.ifc','.py','.js','.log','.json','.txt','.md']:
  if p.name.startswith(('WORKING_STATE','ui-runtime','ui-server','npm-runtime','browser-open-help','playwright-version')):continue
  selected.append(p)
for name in ['public-windows-v1','public-linux-v2']:
 for file in ['api.json','independent.json']:selected.append(out/name/file)
for name in ['ifc-host_fully_removed.png','ifc-duplicate_void_relation.png']:
 target=out/name;shutil.copyfile(repo/'output/playwright'/name,target);selected.append(target)
pub=[repo/'docs'/name for name in ['IFC_OPENINGS_DELIVERY.md','IFC_OPENINGS_CROSSCHECK.md','RESCORE_20261107_IFC_OPENINGS.md']]
def row(p):return {'path':p.relative_to(repo).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
index={'scope':'Public reference and synthetic IFC; no real-building certification','score':76,'evidence_files':[row(p) for p in sorted(selected)],'publications':[row(p) for p in pub]}
(repo/'docs/IFC_OPENINGS_EVIDENCE.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
# Adapt release helpers without rewriting previous receipts.
old=repo/'validation/design-inputs-20261107'
for name in ['verify_git_source_v1.py','capture_remote_v1.py','merge_release_v1.py']:
 s=(old/name).read_text(encoding='utf-8').replace('design-inputs-20261107','ifc-net-20261107').replace('DESIGN_INPUTS_EVIDENCE','IFC_OPENINGS_EVIDENCE')
 if name=='merge_release_v1.py':s=s.replace('35b74510f21a0fb536a7f38ae0bb9ed197b70e8f','396bda09ae9e95a31fbb493ab0f518a2fd38b5ff')
 (out/name).write_text(s,encoding='utf-8',newline='\n')
context=json.loads((old/'runtime-context-v1.json').read_text());context['base_commit']='396bda09ae9e95a31fbb493ab0f518a2fd38b5ff'
(out/'runtime-context-v1.json').write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copyfile(old/'source-preservation-v1.json',out/'source-preservation-v1.json')
print(json.dumps({'evidence_files':len(selected),'bytes':sum(p.stat().st_size for p in selected)}))
