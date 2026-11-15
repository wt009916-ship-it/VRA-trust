import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
out=repo/'validation/ifc-composite-materials-20261115'
for path in root.iterdir():
    if path.is_file() and path.suffix in {'.py','.log','.json'}:
        target=out/path.name
        if target.exists():assert target.read_bytes()==path.read_bytes()
        else:shutil.copy2(path,target)
for name in ['feasibility','actual-http','curved-native']:
    shutil.copytree(root/name,out/name)
shutil.copytree(root.parent/'ifc-member-materials-20261115/post-ci',out/'predecessor-pr79-ci')
for path in (repo/'backend').glob('*.py'):
    target=out/'runtime-source'/path.relative_to(repo);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
for name in ['frontend/src/material-collection-ui.js','frontend/tests/ifc-member-ui.test.js']:
    target=out/'runtime-source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/name,target)
shutil.copy2(root/'IFC_COMPOSITE_MATERIALS_DELIVERY.md',repo/'docs/IFC_COMPOSITE_MATERIALS_DELIVERY.md')
p=repo/'docs/CURRENT_SCORE.json';before=p.read_bytes();history=repo/'docs/history/CURRENT_SCORE_20261115_before_composite.json';assert not history.exists();history.write_bytes(before)
score=json.loads(before)
score['candidate'].update(product_commit='205e9fdbd05eb6d2d277a615cb35f377ca736522',pr=79,delta=0)
score['review']='docs/IFC_MEMBER_MATERIALS_DELIVERY.md'
score['ci_receipt']='validation/ifc-composite-materials-20261115/predecessor-pr79-ci/ci-receipt.json'
score['latest_delivery']={'report':'docs/IFC_MEMBER_MATERIALS_DELIVERY.md','final_product_commit':'205e9fdbd05eb6d2d277a615cb35f377ca736522',
 'validation':'2043 backend passed,22 skipped,248 frontend+build,30 API passed; draft unmerged','ci_receipt':score['ci_receipt']}
score['in_progress']={'branch':'feature/ifc-composite-materials-20261115','report':'docs/IFC_COMPOSITE_MATERIALS_DELIVERY.md',
 'score_delta':0,'validation':'22 new core plus16 homogeneous regression,60 related backend,248 frontend+build,15 actual HTTP,isolated curved reference; precise CI pending'}
p.write_text(json.dumps(score,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=repo/'docs/IFC_MEMBER_MATERIALS_DELIVERY.md'
p.write_text('> 2026-11-15 收口：PR79/205e9fd 三CI成功，后端2043通过/22跳过/2警告/6子测试，前端248及构建，接口30。原八维复核仍78.5（增量0），正式仍76。回执见 validation/ifc-composite-materials-20261115/predecessor-pr79-ci/；下文为本批原交付，复合材料后续增量另见 IFC_COMPOSITE_MATERIALS_DELIVERY.md。\n\n'+p.read_text(encoding='utf-8'),encoding='utf-8')
plan='''# 当前工作安排

2026-11-15。原八维/87项95+目标保持。正式44f344e仍76；已复评候选PR79/205e9fd为78.5，三CI成功：后端2043、前端248及构建、接口30；22跳过不算通过。前批单材梁柱、三公开对象与真实成本碳链已收口，不重跑。

## 当前批次

feature/ifc-composite-materials-20261115：复合梁柱逐材空间计量已接入原材料集合与两方案流程。22新增核心、16整材回归、60相关后端、248前端及构建通过；15实际HTTP检查及圆环/圆芯原生隔离对照通过。详IFC_COMPOSITE_MATERIALS_DELIVERY和PLAN。当前推送草稿及核验精确CI，不预加分、不合并默认分支、不更新正式数据。

## 去重及停止条件

不重复已关闭的PR79/PR78回归、同一Agent题修补或Florence/模板/R2V失败筛查。新复合任务复用成本/碳和撤证机制，不重复算新增分。圆形容差及平面答案在首次求解前冻结，不因结果调宽。此批后重新选择原始剩余能力，不无限细化同一个几何输入域。

## 保留边界

复合几何新证据为合成模型；更广泛真实复合模型、变截面/复杂BRep、图纸语义、库外规范、实楼及生产部署仍缺。浏览器按用户选择暂缓，不绕过。一般Agent可靠性仍不足。95+尚未达到，不启动训练扩张或整体视觉改版。正式与候选分开记录。
'''
(repo/'docs/CURRENT_WORK_PLAN.md').write_text(plan,encoding='utf-8')
p=repo/'.gitattributes';s=p.read_text();line='validation/ifc-composite-materials-20261115/** -text'
if line not in s:p.write_text(s.rstrip()+'\n'+line+'\n')
files={p.relative_to(out).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'}
(out/'manifest.json').write_text(json.dumps({'files':files,'source_kind':'synthetic reference, actual local execution, no real building or browser','runtime_source_bytes_preserved':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
receipt=json.loads((root/'actual-http/receipt.json').read_text(encoding='utf-8'))
assert receipt['complete'] and all(hashlib.sha256((out/'runtime-source'/name).read_bytes()).hexdigest()==digest for name,digest in receipt['source_sha256'].items())
print(json.dumps({'manifest_files':len(files),'bytes':sum(r['bytes'] for r in files.values()),'runtime_hashes_match':True}))
