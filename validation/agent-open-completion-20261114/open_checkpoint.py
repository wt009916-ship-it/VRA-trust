import hashlib,json,math,shutil
from pathlib import Path
root=Path.cwd();out=root/'validation/agent-open-completion-20261114';live=out/'live-completion-d'
task=json.loads((live/'M01-task.json').read_text(encoding='utf-8'))
receipt=json.loads((live/'receipt.json').read_text(encoding='utf-8'))
oracle=json.loads((live/'independent-oracle.json').read_text(encoding='utf-8'))
assert receipt['completed'] and receipt['processes_stopped']
facts={f['fact']:float(f['value']) for row in task['answer']['checked_statements'] for f in row['facts']}
assert set(facts)=={'u_w_m2k','cvrmse_percent'}
assert math.isclose(facts['u_w_m2k'],50/81,rel_tol=1e-10)
assert math.isclose(facts['cvrmse_percent'],float(oracle['variants']['bias']['cvrmse_pct']),rel_tol=1e-10)
assert task['early_finish_with_unresolved_reads']
for name,digest in receipt['product_sha256'].items():
 data=(root/name).read_bytes();assert hashlib.sha256(data).hexdigest()==digest,name
 p=out/'source-snapshot'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
assessment={'case':'M01','passed':True,'current_source_hashes_verified':len(receipt['product_sha256']),
 'independent_values':facts,'events':len(task['events']),'original_screen':'5/8 retained',
 'limitation':'Bounded replay of a known failure. Duplicate delivery actions still consume event budget.'}
(out/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n',encoding='utf-8')
base=Path('D:/稀土agent-稀土制暖全流程/outputs/agent-metric-20261113')
for name in ('open-completion-first.log','open-completion-final.log','open-completion-live.log','fix_open_completion.py','limit_completion_scope.py'):
 shutil.copyfile(base/name,out/name)
p=root/'docs/AGENT_OPEN_COMPLETION_PROGRESS.md'
p.write_text('''# 开放任务完成检查修复

2026-11-14，feature/agent-open-completion-20261114，基于PR75的007579f8。

原M01失败已追踪到agent_recovery.unresolved只收集读取失败的恢复目标，成功目录读取未进入待交付清单。已将开放任务中模型实际选择的成功读取及批量子读取纳入清单，专业检查模式保留原行为。控制器来源复核不会创建额外交付义务，非数值来源审查可以关闭对应记录。

第一组33项回归通过，限定开放任务后的51项回归通过。原M01一次真实模型回归通过，U=50/81，CV(RMSE)按原冻结bias公式核对，恰好交付两个要求字段。成功截住提前结束并继续处理账单。112份运行源码摘要核对通过。模型重复提交墙体结果，实际用满15事件，仍需改进稳定性。首次新题5/8保留。

完整Agent及直接接口回归正在运行，日志位于D工作区outputs/agent-metric-20261113/open-completion-all.log。PR75的前端及接口CI通过，后端仍在核验中。当前修复尚未提交下一PR。

后续先收齐两组终态回执，完成证据同步，再用冻结新题检查开放任务覆盖。已选记录交付检查只约束观察到的目标，原问题遗漏记录、遗漏关系或额外交付字段仍须依实际任务验证。
''',encoding='utf-8')
p=root/'docs/CURRENT_WORK_PLAN.md';s=p.read_text(encoding='utf-8')
p.write_text('> 当前开放任务完成检查修复见 AGENT_OPEN_COMPLETION_PROGRESS.md，分支 feature/agent-open-completion-20261114。PR75已同步，精确提交CI正在收口。\n\n'+s,encoding='utf-8')
print(json.dumps(assessment))
