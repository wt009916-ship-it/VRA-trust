import hashlib,json,re,shutil,statistics
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1]
summary='2026-11-07图纸几何更新：真实隔离OCR处理版本、原件/派生件校验、正逆坐标、用户声明尺度区间和条件长度JSON已实现。双平台各12场景限定检查通过，公开OCR仅7/8、旋转后6/8；过滤删除81像素弱线，语义修复未实现。Windows1083/Linux1092及各6子测试、85前端通过。浏览器先复现越界后旧3m残留，修复后输入/失败/迟到响应撤下通过；损坏派生件stale/null与原件保护通过。截图接口与桌面审批均超时，视觉验收待验证。精确Git构建资源与浏览器一致；复评76保持，发布以release回执为准。下一批动态热工独立基准与设计资料适用性，净量/复杂图纸/一般注入/实楼及生产验收仍开放。不扩大训练，整体视觉后置。详[交付](DRAWING_GEOMETRY_DELIVERY.md)、[交叉验证](DRAWING_GEOMETRY_CROSSCHECK.md)、[证据](DRAWING_GEOMETRY_EVIDENCE.json)、[复评](RESCORE_20261107_DRAWING_GEOMETRY.md)。\n\n'
for name in ['CURRENT_STATE_AUDIT.md','IMPLEMENTATION_STATUS.md','EXECUTION_PLAN_95_PLUS.md','ACCEPTANCE_ROADMAP.md']:
    p=repo/'docs'/name;old=p.read_text(encoding='utf-8');assert not old.startswith(summary);p.write_text(summary+old,encoding='utf-8')
with (repo/'docs/DRAWING_GEOMETRY_PROGRESS.md').open('a',encoding='utf-8') as f:
    f.write('\n## 本批本地验收收口\n\n后续限定检查、版本差异、DG-004修复、双平台全量和未通过的视觉截图，见DRAWING_GEOMETRY_DELIVERY.md与机器证据索引。上述“待验收”是各阶段当时状态，原失败保留。当前复评76，GitHub/原型发布以release回执为准，95+目标继续。\n')
for origin,name in [(repo/'.playwright-cli/console-2026-11-07T02-50-42-851Z.log','browser-console-content-v1.log'),
                    (repo/'.playwright-cli/console-2026-11-07T03-15-21-999Z.log','browser-headed-console-content-v1.log'),
                    (repo/'output/playwright/drawing-geometry-20261107/conditional-length-v1.json','browser-conditional-length-v1.json')]:
    target=out/name;assert not target.exists();shutil.copyfile(origin,target)
performance={}
for platform,name in [('windows','benchmark-windows-v3.json'),('linux','linux-benchmark-v1.json')]:
    data=json.loads((out/name).read_text());values=[x['seconds'] for x in data['cases']]
    performance[platform]={'scenarios':len(values),'min_seconds':min(values),'median_seconds':statistics.median(values),'max_seconds':max(values),
                           'scope':'Sequential local reference OCR API wall times; not a load test, production SLA or quality score.'}
with (out/'performance-summary-v1.json').open('x',encoding='utf-8') as f:json.dump(performance,f,indent=2)
files=[]
for p in sorted(out.iterdir()):
    if p.suffix not in {'.json','.log','.py','.js','.md','.txt','.gz'}:continue
    raw=p.read_bytes()
    if p.suffix!='.gz':
        text=raw.decode('utf-8-sig')
        assert not re.search(r'(?i)"(?:password|csrf_token|access_token|api_key)"\s*:\s*"[^"\s]+"',text),p.name
        assert not re.search(r'(?:gh[pousr]_[A-Za-z0-9]{25,}|sk-[A-Za-z0-9]{30,})',text),p.name
    files.append({'path':p.relative_to(repo).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
pubs=[]
for name in ['DRAWING_GEOMETRY_DELIVERY.md','DRAWING_GEOMETRY_CROSSCHECK.md','RESCORE_20261107_DRAWING_GEOMETRY.md','DRAWING_GEOMETRY_PROGRESS.md']:
    p=repo/'docs'/name;raw=p.read_bytes();pubs.append({'path':p.relative_to(repo).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
index={'application_commit':json.loads((out/'candidate-source-v2.json').read_text())['application_commit'],
       'score':76,'prior_score':76,'goal':'active','training':False,'visual_acceptance':'pending: browser capture and desktop app approval timeouts',
       'regression':{'windows':{'passed':1083,'skipped':25,'subtests':6,'seconds':1112.06},'linux':{'passed':1092,'skipped':16,'subtests':6,'seconds':678.17},'frontend':85},
       'source_snapshot':'validation/drawing-enhancement-20261107/candidate-source-v2.json',
       'source_proof':'validation/drawing-enhancement-20261107/source-and-assets-verified-v1.json',
       'performance':performance,'evidence_files':files,'publications':pubs}
(repo/'docs/DRAWING_GEOMETRY_EVIDENCE.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'evidence_files':len(files),'evidence_bytes':sum(x['bytes'] for x in files),'performance':performance}))
