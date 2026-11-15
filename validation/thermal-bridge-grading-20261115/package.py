import gzip,hashlib,json,shutil,subprocess
from pathlib import Path
root=Path(__file__).parent
repo=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
dest=repo/'validation/thermal-bridge-grading-20261115'
dest.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ['graded-first.log','api-regression.log','frontend.log','build.log','build-preparation.json','live-first.log','live-frozen.json','live_acceptance.py','prepare_build.py','package.py']:
    shutil.copy2(root/name,dest/name)
shutil.copytree(root/'live-first',dest/'live-first')
experiment=dest/'experiment';experiment.mkdir()
for name in ['PLAN.md','experiment.py','frozen.json','receipt.json','experiment.log']:shutil.copy2(root/name,experiment/name)
compressed={}
for name in ['graded-4mm.json','graded-2mm.json']:
    source=root/name;target=experiment/(name+'.gz');target.write_bytes(gzip.compress(source.read_bytes(),mtime=0))
    compressed[target.name]={'original_sha256':sha(source),'original_bytes':source.stat().st_size,'archive_sha256':sha(target)}
save(experiment/'compression-receipt.json',compressed)
shutil.copytree(root.parent/'construction-leveling-20261115/post-ci',dest/'predecessor-pr82-ci')
for p in (root/'frontend-build/src').glob('*.js'):assert sha(p)==sha(repo/'frontend/src'/p.name),p.name
receipt=json.loads((dest/'live-first/receipt.json').read_text(encoding='utf-8'))
assert receipt['completed'] and receipt['process_stopped'] and len(receipt['checks'])==43 and all(c['passed'] for c in receipt['checks'])
for name,expected in receipt['product_sha256'].items():assert sha(repo/'backend'/name)==expected,name
save(dest/'build-receipt.json',{'passed':True,'build_ms':443,'frontend_tests':257,'browser':'deferred_by_user',
 'lock_sha256':sha(repo/'frontend/package-lock.json'),
 'source_js_hashes':{p.name:sha(p) for p in (repo/'frontend/src').glob('*.js')},
 'assets':{p.relative_to(root/'frontend-build/dist').as_posix():sha(p) for p in (root/'frontend-build/dist').rglob('*') if p.is_file()}})
save(dest/'assessment.json',{'base_commit':'a37d375692e239e7f4bad72fa1cc7aef38ddeec5','candidate_score':79,'published_score':76,'score_delta':0,
 'new_method_tests':11,'original_mode_and_api_tests':34,'frontend_tests':257,'http_cases':5,'http_checks':43,
 'ci':'pending exact final commit','original_uniform_failure_retained':True,'complete_standard_validation':False,
 'not_a_rigorous_continuum_error_bound':True,'real_building_validation':False,'browser':'deferred_by_user',
 'reason_no_score':'Original professional thermal4/4 already allocated; remaining independent-thermal point requires full dynamic-load reference and real-building calibration, not repetition of steady thermal capability.'})
score=repo/'docs/CURRENT_SCORE.json'
shutil.copy2(score,repo/'docs/history/CURRENT_SCORE_20261115_before_thermal_grading.json')
data=json.loads(score.read_text(encoding='utf-8'))
data['candidate'].update(product_commit='a37d375692e239e7f4bad72fa1cc7aef38ddeec5',pr=82)
data['latest_delivery']={'report':'docs/CONSTRUCTION_RESOURCE_LEVELING_DELIVERY.md','final_product_commit':'a37d375692e239e7f4bad72fa1cc7aef38ddeec5',
 'validation':'2120 backend,22 skipped,256 frontend/build,30 API; real model first1/3 and failed-two regression2/2, public6 all feasible3 optimum; draft unmerged',
 'ci_receipt':'validation/thermal-bridge-grading-20261115/predecessor-pr82-ci/ci-receipt.json'}
data['in_progress']={'branch':'feature/thermal-bridge-grading-20261115','score_delta':0,'scope':'Explicit graded material-interface grid; original public composite reference and original mesh gates passed without increasing budgets; default uniform retained',
 'report':'docs/THERMAL_BRIDGE_GRADING_DELIVERY.md','evidence':'validation/thermal-bridge-grading-20261115/assessment.json','validation':'11 new numerical,34 original/API,257 frontend/build,5 real HTTP cases/43 checks; exact CI pending'}
save(score,data)
(repo/'docs/CURRENT_WORK_PLAN.md').write_text('''# 当前工作安排

2026-11-15。原八维/87场景95+目标不变；正式44f344e仍76，已收口候选PR82/a37d375仍79。分值不按测试数量增长。

## 已收口，不重复

PR82：2120后端、22跳过、256前端及构建、30接口；资源受限方案实际HTTP10例/20检查，公开6例均可行、3例达到已知最优，另外3例差11/20/1；首轮真实模型1/3、两失败题回归2/2完整保留。PR81精确4930600三CI已绿。两批不重跑原模型题或改字段刷分。

## 当前完整能力批

二维材料界面加密网格：保持原默认模式及其失败记录，新增显式策略贯通输入、计算、保存、图示、报告、CSV、来源撤回。预算/容差均未扩大。公开复合4/2mm两档的全场网格差0.056/0.040K通过，同时9参考点及热流通过。28点解析角点奇异案例仍needs_refinement。11新数值、34原模式/API、257前端及构建、实际HTTP5例/43检查通过；最终精确CI待核验。

本批评分增量0：原专业热工已4/4；准确性独立热工3/4的剩余要求是完整动态负荷独立答案及实楼校准，不能把稳态改进重复计分。详THERMAL_BRIDGE_GRADING_DELIVERY。真实浏览器按用户选择暂缓。

## 下一步及退出规则

完成当前精确CI及证据归档后退出该批，不再调整两个已过网格或复测旧参照。先追踪已有逐时热工、自由漂移、理想负荷平衡和时间步可靠性代码及证据，再针对原未通过的动态系统/完整负荷边界选独立公开基准。已交付的时序、潜热、设备端用能及原生SQL不得按旧报告重做。

候选剩余21分：专业3、准确性2、Agent5.5、文件3.5、完整度2、稳定性1、安全2、体验2。未有实际实楼资料，保留实楼待验；没有浏览器授权，页面待验。95+前不扩大训练、不做整体视觉改版。权威工作区为本D盘仓库；旧C盘对象库保留，不继续修复无关历史。
''',encoding='utf-8')
p=repo/'docs/IMPLEMENTATION_STATUS.md'
p.write_text('# 2026-11-15 材料界面加密网格（候选，精确CI待验）\n\n详[交付及边界](THERMAL_BRIDGE_GRADING_DELIVERY.md)。公开复合参照与原网格门槛通过；默认均匀旧失败仍保留，诊断/来源撤回/导出同链验收。真实浏览器暂缓；候选79不变。PR82/a37d375已三CI成功，回执纳入本批。下方历史不作为待办。\n\n'+p.read_text(encoding='utf-8'),encoding='utf-8')
attrs=repo/'.gitattributes';attrs.write_text(attrs.read_text(encoding='utf-8')+'\nvalidation/thermal-bridge-grading-20261115/** -text\n',encoding='utf-8')
manifest={'base':'a37d375692e239e7f4bad72fa1cc7aef38ddeec5','scope':'Actual logs, source bytes, frozen inputs and compressed raw responses. No private runtime, credentials, dependencies or original user data.',
 'files':{p.relative_to(dest).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(dest.rglob('*')) if p.is_file()}}
save(dest/'manifest.json',manifest)
print(json.dumps({'evidence_files':len(manifest['files']),'bytes':sum(v['bytes'] for v in manifest['files'].values()),'score':79}))
