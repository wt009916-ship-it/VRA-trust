import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).parent;repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');out=repo/'validation/ifc-composite-materials-20261115'
receipt=json.loads((root/'actual-http-final/receipt.json').read_text(encoding='utf-8'));assert receipt['complete'] and receipt['passed']==18
for name in ['profile_type_counterexample.py','fix_source_profile.py','add_final_http_counterexample.py','http_acceptance_final.py','http-final.log','source-profile-fix.log','package_source_fix.py']:
    shutil.copy2(root/name,out/name)
for name in ['invalid-profile-before','actual-http-final']:shutil.copytree(root/name,out/name)
delta=out/'runtime-source-final/backend';delta.mkdir(parents=True,exist_ok=False)
shutil.copy2(repo/'backend/ifc_composite_materials.py',delta/'ifc_composite_materials.py')
for name,digest in receipt['source_sha256'].items():
    p=out/'runtime-source-final'/name
    if not p.exists():p=out/'runtime-source'/name
    assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,name
append='''

## 收尾反例与修复（原首轮证据保持）

### CMP-05 · 错误原始轮廓类型被分区过程掩盖（高，已修复，最终CI待核验）

- 功能：E08模型完整性及H01材料量。复现：把相邻两材的原IfcCompositeProfileDef.ProfileType改成CURVE，子轮廓仍为AREA，然后调用材料计量。
- 预期：原扫掠体不符合面积轮廓要求，应拒绝，不得默默按子轮廓重新解释原模型。
- 首轮实际：75c4550输出measured、24 m³。证据invalid-profile-before/member.ifc及result.json保留。
- 依据：[IFC4 IfcSweptAreaSolid SweptAreaType](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/FINAL/HTML/schema/ifcgeometricmodelresource/lexical/ifcsweptareasolid.htm)明确要求SweptArea.ProfileType为AREA。
- 修复：在任何分区前核对原复合轮廓AREA及有限正挤出深度；不通过时host和总量均null、片段为空。不是修改原文件类型。
- 修复验证：非法CURVE、零深度、负深度加正常平面／圆形共12项针对性测试通过。最终新实际HTTP为18/18，包含非法原轮廓原生工作器拒绝、正常12／10分材成本碳和撤证。首次15/15仍作为旧源码证据保留，不替换为新源码通过。
- 建议：后续进一步验证更广源表示约束；本次是明确扫掠条件检查，不是整个IFC文件的EXPRESS合规认证。

最终运行源哈希由actual-http-final/receipt.json记录；runtime-source-final仅保存本修复改动的模块，其余字节在原runtime-source。两者联合逐条核对全部后台源码。原manifest.json未改，新增manifest-final.json覆盖增量及历史证据。前端源码没有变化，沿用本批248项及构建，不无故重复。
'''
p=repo/'docs/IFC_COMPOSITE_MATERIALS_DELIVERY.md';p.write_text(p.read_text(encoding='utf-8')+append,encoding='utf-8')
p=repo/'docs/CURRENT_WORK_PLAN.md';s=p.read_text(encoding='utf-8').replace('15实际HTTP检查及圆环/圆芯原生隔离对照通过。','初轮15实际HTTP及圆环/圆芯原生隔离对照通过；收尾发现非法CURVE原轮廓仍可输出24m³，已保留失败并修复，12相关回归和最终新18实际HTTP检查通过。')
p.write_text(s,encoding='utf-8')
p=repo/'docs/CURRENT_SCORE.json';s=json.loads(p.read_text(encoding='utf-8'));s['in_progress']['validation']+='; source AREA/depth counterexample fixed,12 focused and18 final HTTP passed; final-head CI pending';p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(out).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest-final.json'}
(out/'manifest-final.json').write_text(json.dumps({'files':files,'previous_manifest_unchanged':True,'runtime_snapshot':'runtime-source-final overrides runtime-source only for matching named files'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(files),'final_runtime_source_match':True,'final_HTTP':receipt['passed']}))
