import hashlib,json,shutil,subprocess
from pathlib import Path
root=Path(__file__).parent
old=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
repo=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
base='49306007f6b7c886f442f307ddc82ffec4dcd00e'
def git(*args):return subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false',*args],cwd=repo,text=True,encoding='utf-8').strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert git('rev-parse','HEAD')==base and not git('status','--porcelain')
git('fsck','--full','--no-reflogs')
git('switch','-c','feature/construction-resource-leveling-20261115')
paths=[p.relative_to(old) for p in (old/'backend').glob('*.py')]+[p.relative_to(old) for p in (old/'frontend/src').glob('*.js')]
paths += list(map(Path,['tests/test_calculation_provenance.py','tests/test_construction_leveling.py','tests/test_leveling_agent_recovery.py','tests/fixtures/resource_leveling_reference.json','frontend/tests/schedule-leveling.test.js','shared/schemas/openapi.json']))
for relative in paths:
 p=repo/relative;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/relative,p)
 assert sha(p)==sha(old/relative),str(relative)
receipt={'base':base,'old_workspace_preserved':True,'new_workspace':str(repo),'copied_files':len(paths),'mismatches':0,'clean_shallow_fsck':True,'full_old_object_store_repair':False}
(root/'migration.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')

dest=repo/'validation/construction-leveling-20261115';dest.mkdir(parents=True)
for name in ['reference-frozen.json','freeze_reference.py','freeze_public_reference.py','prepare_public_inputs.py','PLAN.md','live_acceptance.py','model_acceptance.py','model_retry.py','core-first.log','core-authorized.log','regression.log','provenance-fixed.log','metric-fix.log','empty-fixed.log','frontend.log','build.log','fix_provenance_tests.py','fix_metric_catalog.py','prepare_retry.py','repair_git_indexes.py','git-refetch.log','clean-clone.log','migration.json','migrate_package.py']:
 if (root/name).exists():shutil.copy2(root/name,dest/name)
for directory in ['live-first','model-first','model-after-catalog']:
 shutil.copytree(root/directory,dest/directory)
for name in ['frozen-public-reference.json','input-preparation.json']:
 p=dest/'public-reference'/name;p.parent.mkdir(exist_ok=True);shutil.copy2(root/'public-reference'/name,p)
for snapshot,source in [('runtime-source-first',root/'runtime-source-first/backend'),('runtime-source-final',old/'backend')]:
 for p in source.glob('*.py'):
  target=dest/snapshot/'backend'/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 live='model-first' if snapshot.endswith('first') else 'model-after-catalog'
 expected=json.loads((root/live/'receipt.json').read_text(encoding='utf-8'))['product_sha256']
 assert all(sha(dest/snapshot/'backend'/name)==value for name,value in expected.items())
shutil.copytree(root.parent/'agent-record-comparison-20261115/post-ci-final',dest/'predecessor-pr81-ci')
first=json.loads((root/'model-first/receipt.json').read_text(encoding='utf-8'));retry=json.loads((root/'model-after-catalog/receipt.json').read_text(encoding='utf-8'));http=json.loads((root/'live-first/receipt.json').read_text(encoding='utf-8'))
assert first['completed'] and retry['completed'] and http['completed']
assert sum(x['passed'] for x in first['tasks'])==1 and len(retry['tasks'])==2 and all(x['passed'] for x in retry['tasks'])
assert len(http['cases'])==10 and len(http['checks'])==20 and all(x['passed'] for x in http['checks'])
assessment={'score':79,'score_delta':0,'published_score':76,'http_cases':10,'http_checks':20,'http_all_passed':True,'model_first_passed':1,'model_first_total':3,'model_regression_passed':2,'model_regression_total':2,'model_fresh_rerun_all_three':False,'browser':'deferred_by_user','training_expansion':False,'public_benchmark_optimal_matches':3,'public_benchmark_total':6,'known_nonoptimal_gaps_days':[11,20,1],'initial_related_regression':{'passed':163,'failed':3},'inherited_injection_regression_fixed':52,'metric_fix_first':{'passed':45,'failed':1},'empty_selection_harness_fixed':1,'frontend':{'passed':256,'build_ms':429},'ci':'pending_exact_head','old_git_object_store':'preserved with unresolved historical references; migrated to clean exact-base checkout'}
(dest/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n',encoding='utf-8')
shutil.copy2(root/'DELIVERY.md',repo/'docs/CONSTRUCTION_RESOURCE_LEVELING_DELIVERY.md')
shutil.copy2(repo/'docs/CURRENT_SCORE.json',repo/'docs/history/CURRENT_SCORE_20261115_before_resource_leveling.json')
p=repo/'docs/CURRENT_SCORE.json';s=json.loads(p.read_text(encoding='utf-8'))
s['candidate'].update(product_commit=base,pr=81,prior_scored_commit=s['candidate']['product_commit'],previous_score=79,delta=0)
s['latest_delivery']={'report':'docs/AGENT_RECORD_COMPARISON_DELIVERY.md','final_product_commit':base,'validation':'2098 backend,22 skipped,252 frontend/build,30 API; first failures retained; draft unmerged','ci_receipt':'validation/construction-leveling-20261115/predecessor-pr81-ci/ci-receipt.json'}
s['in_progress']={'branch':'feature/construction-resource-leveling-20261115','score_delta':0,'scope':'Source-bound resource-constrained schedule, explicit original priority and mathematical bound; no global optimality promise','report':'docs/CONSTRUCTION_RESOURCE_LEVELING_DELIVERY.md','evidence':'validation/construction-leveling-20261115/assessment.json','validation':'10 real HTTP cases/20 checks; frozen public6 feasible3 match known optimum; first model1/3, failed two regression2/2;256 frontend/build; final exact CI pending'}
p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(repo/'docs/CURRENT_WORK_PLAN.md').write_text('''# 当前工作安排

2026-11-15。原八维/87场景95+目标不变。正式44f344e仍76；候选79，分值继承PR80复核，PR81最终4930600已全绿收口。本批不按测试数量加分。

## 已收口，不重复

PR81：2098后端、22跳过、252前端及构建、30接口；跨记录比较首个真实模型预算失败及首个CI目录超限保留，已修复。六题最终观察中C01是回归，C02–C06首次；不扩成所有Agent可靠。PR80/79及DWG限定证据已归档。本批不重跑旧模型题或CAD并集。

## 当前完整能力批

施工资源受限排程：保持原CPM计算器不变，新增源hash绑定、明确优先序/占用确认的独立方案，保存工序起止、相对CPM延后、资源峰值、精确数学下界、报告及Agent读取。来源变化撤下当前结果，不能替换实际进度。4独立算例及6提前冻结的PSPLIB公开算例全部满足独立约束检查；公开6例3个达到已知最优，其他分别差11/20/1，明确不是通用最优求解器。

真实模型首轮1/3；L01/L03暴露先选字段无含义及空投影仍生成交付工具的问题。修复静态字段契约及交付工具可用性后两题原样回归2/2，L02不重复。原预算、问题和失败保留，不能宣称首次全过或自由问题已被完整理解。来源回归52通过，前端256及构建通过；最终精确CI另验。

旧临时Git对象库的缺失索引恢复后仍有早期坏引用；没有删除分支，已迁到PR81精确基线的干净浅检出，逐文件hash核对一致，旧目录及失败日志保留。后续权威工作区为本仓库，不继续修补旧库无关历史。

## 下一步及退出规则

先完成当前草稿精确CI和证据归档，然后回到原剩余扣分项选完整能力批。资源领域若再扩展，应是有界优化/明确日历的完整输入—求解—独立基准—来源撤回链，不继续改同一组字段或重跑相同题。公共6例的非最优差距作为后续固定比较参照，不按结果重新选样本。

候选剩余21分：专业3、计算2、Agent5.5、文件3.5、完整度2、稳定性1、安全2、体验2。规范广度、图纸语义、复杂热桥、真实建筑/生产环境和广泛复合Agent仍是主要缺口；局部正确功能不能替代这些门槛。浏览器按用户明确选择暂缓，函数/构建/HTTP不计界面通过。95+前不扩大训练、不开始整体视觉改版。
''',encoding='utf-8')
p=repo/'docs/IMPLEMENTATION_STATUS.md';p.write_text('# 2026-11-15 施工资源受限方案（候选，精确CI待验）\n\n详[交付与反例](CONSTRUCTION_RESOURCE_LEVELING_DELIVERY.md)。本批完整链包含新方案、来源撤回、报告、Agent读取及公开独立约束验证；不声称全局最优、现场安全或浏览器验收。原CPM未改，历史条目不自动成为待办。\n\n'+p.read_text(encoding='utf-8'),encoding='utf-8')
p=repo/'.gitattributes';p.write_text(p.read_text(encoding='utf-8')+'\nvalidation/construction-leveling-20261115/** -text\n',encoding='utf-8')
manifest={'base':base,'files':{p.relative_to(dest).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(dest.rglob('*')) if p.is_file()},'raw_public_inputs_redistributed':False,'private_runtime_included':False,'source_overlay':'Both actual model runtime snapshots preserved; final snapshot corresponds to L01/L03 regressions.'}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'package-receipt.json').write_text(json.dumps({'files':len(manifest['files']),'bytes':sum(r['bytes'] for r in manifest['files'].values()),'repo':str(repo),'base':base},indent=2)+'\n')
print(json.dumps({'migration':receipt,'evidence_files':len(manifest['files']),'evidence_bytes':sum(r['bytes'] for r in manifest['files'].values())}))
