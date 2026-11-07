import hashlib,json
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1]
summary='2026-11-07自由漂移更新：新增分区温度切换、双峰值日曲线及逐时表；双平台同输入8例各6达0.02K、2粗步长超限，温度/负荷序列跨平台差0。92前端、66后端专项及构建/语法通过；浏览器真实年度6区8760小时、288温度值与API一致、390px及撤证清空通过，普通点击/截图稳定性超时保留。后端68源码与原业务记录不改。复评76保持；发布以本批release回执为准。接下来设计资料适用性、复杂IFC净量及一般Agent注入；训练/整体视觉后置。详[交付](FREEFLOAT_THERMAL_DELIVERY.md)、[交叉验证](FREEFLOAT_THERMAL_CROSSCHECK.md)、[复评](RESCORE_20261107_FREEFLOAT.md)。\n\n'
for name in ('CURRENT_STATE_AUDIT.md','IMPLEMENTATION_STATUS.md','EXECUTION_PLAN_95_PLUS.md'):
    p=repo/'docs'/name;old=p.read_text(encoding='utf-8')
    assert not old.startswith(summary)
    p.write_text(summary+old,encoding='utf-8',newline='\n')
def row(p):return {'path':p.relative_to(repo).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
exclude={'ui-server-v1.log','browser-reference-snapshot-v1.log'}
files=[row(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name not in exclude]
publications=[row(repo/'docs'/name) for name in ('FREEFLOAT_THERMAL_DELIVERY.md','FREEFLOAT_THERMAL_CROSSCHECK.md','RESCORE_20261107_FREEFLOAT.md')]
sources=[row(repo/p) for p in ('scripts/verify_freefloat_thermal.py','frontend/src/hourly-thermal.js','frontend/src/hourly-thermal.css','frontend/src/main.js','frontend/tests/hourly-thermal.test.js')]
index={'base_commit':'2d461e5b4c8cc79d7df5c8195bd51c1220826f48','score':76,'goal':'active','evidence_files':files,'publications':publications,'tested_sources':sources,
       'validation':{'frontend_passed':92,'backend_focused_passed':66,'native_cases_per_platform':8,'within_tolerance_per_platform':6,'coarse_step_mismatches_per_platform':2,'visual':'pending: stable-wait timeouts'},
       'publication_boundary':'Bounded public/synthetic test artifacts only. Large native SQL retained locally with hashes. No private DB, cookies or passwords.'}
(repo/'docs/FREEFLOAT_THERMAL_EVIDENCE.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'evidence_files':len(files),'publications':len(publications),'bytes':sum(r['bytes'] for r in files)}))
