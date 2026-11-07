"""Publish the completed, immutable local evidence once both regressions have finished."""
import hashlib, json, re, subprocess
from pathlib import Path

out = Path(__file__).parent.resolve(); repo = out.parents[1]
assert (out / 'linux-final-regression-v2.json').is_file()
summaries = {}
for platform in ['windows', 'linux']:
    text = (out / (platform + '-full-final-v2.log')).read_text(encoding='utf-8')
    matches = re.findall(r'(\d+) passed, (\d+) skipped,.*?(\d+) subtests passed in ([\d.]+)s', text)
    assert matches and not re.search(r'\d+ failed|ERROR collecting', text)
    passed, skipped, subtests, seconds = matches[-1]
    summaries[platform] = {'passed': int(passed), 'skipped': int(skipped), 'subtests': int(subtests), 'seconds': float(seconds)}
assert summaries['windows']['passed'] == 1050 and summaries['linux']['passed'] == 1059
application = '03bda16d411705affa56396768ed5b3b573cbfbe'
assert not subprocess.check_output(['git', 'diff', '--name-only', application, '--', 'backend', 'frontend/src', 'frontend/tests', 'tests', 'scripts', 'shared', 'cases', 'fixtures'], cwd=repo).strip()
delivery = repo / 'docs/DESIGN_LOADS_DELIVERY.md'
text = delivery.read_text(encoding='utf-8'); assert '{{FINAL_REGRESSION}}' in text
text = text.replace('{{FINAL_REGRESSION}}', f"最终应用全量：Windows **1050 通过/25 跳过**（{summaries['windows']['seconds']} 秒），Linux **1059 通过/16 跳过**（{summaries['linux']['seconds']} 秒），各 **6 子测试通过**。跳过项与平台边界逐项记录，不能视为跨平台全部执行。")
delivery.write_text(text, encoding='utf-8', newline='\n')
summary = '2026-11-07设计负荷更新：真实ZoneSizes/设计日解析、来源绑定、API/PDF/ZIP与Agent原生结果卡已交付。双平台各7个新稳态模型/28数值检查，最大差0.003272W；最终Windows1050通过/25跳过、Linux1059通过/16跳过，各6子测试；前端82通过。37真实模型任务105请求逐轮保留，最终有效四题两模型均读取两页，但4B失效恢复失败、原文仍有数值错配，Agent分不增加。两轮浏览器、当前失效重检及原件保护留证；最终Git前端资源与验收字节相同。复评76（独立热工+1），发布状态以release回执为准。下一批图纸来源保全/倾斜噪声/尺度冲突及独立金标准，继续动态热工与设计资料；RS-07/RS-09、一般注入、净工程量、DWG/转换、实楼/专家和生产验收仍开放。详[交付](DESIGN_LOADS_DELIVERY.md)、[交叉验证](DESIGN_LOADS_CROSSCHECK.md)、[证据](DESIGN_LOADS_EVIDENCE.json)、[复评](RESCORE_20261107_DESIGN_LOADS.md)。95+未达，不扩大训练，整体视觉后置。'
for name in ['CURRENT_STATE_AUDIT.md', 'IMPLEMENTATION_STATUS.md', 'EXECUTION_PLAN_95_PLUS.md', 'ACCEPTANCE_ROADMAP.md']:
    path = repo / 'docs' / name
    old = path.read_text(encoding='utf-8'); assert not old.startswith('2026-11-07设计负荷更新')
    path.write_text(summary + '\n\n' + old, encoding='utf-8', newline='\n')
progress = repo / 'docs/DESIGN_LOADS_PROGRESS.md'
with progress.open('a', encoding='utf-8', newline='\n') as stream:
    stream.write('\n## 最终本地验证完成\n\n' + summary + '\n\n上文各阶段“待验证”为当时状态，保留不改写。最终源码03bda16，真实模型4B四有效题通过/失效题失败，8B五题通过限定检查；不认定自由问题全部完成。最终全量引用本批已完成的新三方案，不把逐字节复用称为新运行。完整失败和限定关闭状态见交付报告。\n')
readme = repo / 'README.md'
with readme.open('a', encoding='utf-8', newline='\n') as stream:
    stream.write('\n设计负荷增量：分区显热、设计日工况和当前来源绑定已交付，见[交付与限制](docs/DESIGN_LOADS_DELIVERY.md)、[独立交叉验证](docs/DESIGN_LOADS_CROSSCHECK.md)及[复评76/100](docs/RESCORE_20261107_DESIGN_LOADS.md)。这不是全楼设备选型、当地设计气象认证或实楼验收。\n')
attributes = repo / '.gitattributes'
with attributes.open('a', encoding='utf-8', newline='\n') as stream:
    stream.write('validation/designload-20261107/** -text\n')

def record(path):
    raw = path.read_bytes()
    return {'path': path.relative_to(repo).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

skip = {'pr-created.json', 'release-head.txt', 'merge-receipt.json', 'release-receipt.json', 'ui-server.log',
        'ui-server-error.log', 'ui-server.pid', 'prototype-started-v1.json', 'ui-graceful-stop.json',
        'runtime-after.json', 'served-assets-verified.json', 'publish-paths.txt', 'final-remote-receipt.json'}
allowed = {'.json', '.py', '.log', '.err', '.idf', '.cjs', '.png', '.md', '.txt', '.ps1', '.gz'}
files = []
for path in sorted(out.rglob('*')):
    if not path.is_file() or path.name in skip or path.name.startswith('final-ci-'): continue
    assert path.suffix in allowed, path
    if path.suffix not in {'.gz', '.png'}:
        content = path.read_text(encoding='utf-8-sig', errors='strict')
        assert not re.search(r'(?:gh[pousr]_[A-Za-z0-9]{25,}|sk-[A-Za-z0-9]{30,})', content), path.name
        assert not re.search(r'(?i)"(?:password|csrf_token|access_token|api_key)"\s*:\s*"[^"\s]+"', content), path.name
    files.append(record(path))
names = ['README.md', '.gitattributes', 'docs/DESIGN_LOADS_DELIVERY.md', 'docs/DESIGN_LOADS_CROSSCHECK.md',
         'docs/DESIGN_LOADS_PROGRESS.md', 'docs/RESCORE_20261107_DESIGN_LOADS.md', 'docs/CURRENT_STATE_AUDIT.md',
         'docs/IMPLEMENTATION_STATUS.md', 'docs/EXECUTION_PLAN_95_PLUS.md', 'docs/ACCEPTANCE_ROADMAP.md']
for name in names:
    path = repo / name
    text = path.read_text(encoding='utf-8-sig')
    path.write_text(text, encoding='utf-8', newline='\n')
index = {'application_commit': application, 'score': 76, 'score_prior': 75, 'goal': 'active', 'training': False,
         'regression': summaries, 'model_tasks': 37, 'model_requests': 105,
         'source_snapshot': 'validation/designload-20261107/final-source-v6.json',
         'git_source_check': 'validation/designload-20261107/git-source-v3.json',
         'evidence_files': files, 'publications': [record(repo / name) for name in names],
         'release_receipt': 'validation/designload-20261107/release-receipt.json',
         'release_notice': 'Release/CI receipts are generated after this immutable index; their absence means release is not verified.',
         'limits': ['synthetic steady sensible load, not complex dynamic or real-building validation',
                    'model prose misattribution persists; 4B stale recovery failed', 'no general injection certification',
                    'no whole-building coincident load, latent total capacity or certified equipment sizing',
                    'browser af8dcf6 frontend identical to final03; final model/API/full regression on03']}
with (repo / 'docs/DESIGN_LOADS_EVIDENCE.json').open('x', encoding='utf-8') as stream:
    json.dump(index, stream, ensure_ascii=False, indent=2)
with (out / 'publish-paths.txt').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write('\n'.join(x['path'] for x in files) + '\n')
print(json.dumps({'evidence_files': len(files), 'publications': len(names), 'regression': summaries}))
