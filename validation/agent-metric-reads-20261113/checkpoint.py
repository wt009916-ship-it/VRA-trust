import json,hashlib,shutil
from pathlib import Path
root=Path.cwd()
out=root/'validation/agent-metric-reads-20261113'
live=out/'live-retry-b'
receipt=json.loads((live/'receipt.json').read_text(encoding='utf-8'))
assert receipt['completed'] and receipt['processes_stopped']
notes={
'M01':('failed','Delivered three thermal facts although only U was requested; omitted utility CV(RMSE).'),
'M02':('passed','Requested CV(RMSE) and interval count delivered.'),
'M03':('passed','Requested undefined CV(RMSE) delivered with null and source reason.'),
'M04':('failed','Four identical catalog batches in one model response exhausted recovery.'),
'M05':('passed','Unknown metric explicitly deferred, no substitute numeric delivery.'),
'M06':('passed','RMSE kWh delivered, excluding MBE and CV(RMSE).'),
'M07':('failed','Carrier totals delivered using native rounded table basis; independent carrier relationship was not explained sufficiently.'),
'M08':('passed','Thermal R delivered and withdrawn utility source reviewed without old quantities.')}
results=[]
records=json.loads((live/'records-before.json').read_text(encoding='utf-8'))
oracle=json.loads((live/'independent-oracle.json').read_text(encoding='utf-8'))
for ident,(status,reason) in notes.items():
 task=json.loads((live/(ident+'-task.json')).read_text(encoding='utf-8'))
 results.append({'id':ident,'assessment':status,'reason':reason,'task_sha256':hashlib.sha256((live/(ident+'-task.json')).read_bytes()).hexdigest()})
# Independently expected values from frozen arithmetic and wall fractions.
expected={'M02':{'cvrmse_percent':float(oracle['variants']['cancellation']['cvrmse_pct']),'interval_count':12},
          'M03':{'cvrmse_percent':None},'M06':{'rmse_kwh':float(oracle['variants']['bias']['rmse_kwh'])},
          'M08':{'total_resistance_m2k_w':1.62}}
import math
for ident,wanted in expected.items():
 task=json.loads((live/(ident+'-task.json')).read_text(encoding='utf-8'))
 actual={f['fact']:f['value'] for r in task['answer']['checked_statements'] for f in r['facts']}
 assert set(actual)==set(wanted),(ident,actual,wanted)
 for key,value in wanted.items():
  assert actual[key] is None if value is None else math.isclose(float(actual[key]),value,rel_tol=1e-10,abs_tol=1e-8)
report={'completed':True,'passed':5,'total':8,'cases':results,
        'product_sources':receipt['product_sha256'],
        'scope':'Actual fixed local model on fresh synthetic source. Subsequent duplicate-read and relation patches have unit evidence only; original screen remains 5/8.'}
(out/'assessment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ('read-first.log','affected-first.log','live-first.log','live-retry-b.log','focused-nov14-b.log'):
 source=Path('D:/稀土agent-稀土制暖全流程/outputs/agent-metric-20261113')/name
 if source.exists():shutil.copyfile(source,out/name)
doc=root/'docs/AGENT_METRIC_READ_PROGRESS.md'
doc.write_text('''# Agent 指标读取进展

2026-11-14。当前 feature/agent-metric-reads-20261113，开发验收进行中。

中文紧邻完整编号识别、当前目录约束指标、每记录批量指标选择已实现。新增13项测试通过。能耗协议旧驱动增加当前任务目录读取，撤证时点保持在数值读取之后。86项受影响测试通过，包含动作协议、能耗、指标选择和本地模型接口。

首次实际模型启动因 CUDA_Host 分配失败结束。保留 live-first。恢复后八道冻结新题完成，严格5/8。M01漏交CV且多报墙体字段，M04同答复四次重复目录读取，M07载体关系解释不足。M02/M03/M06独立公式核对，M08墙体R=1.62及撤证限制核对，M05未知指标澄清。原始输出见 validation/agent-metric-reads-20261113/assessment.json。

针对M04已增加同一模型答复内连续相同只读动作合并执行，原始JSON完整保留。针对关系解释已增加当前核验字段的载体/单位/期间解释及energy_relationship计划主题，至少选择两个能耗字段。结果展示已接通。新增3项测试通过，覆盖来源撤销、期间差异、字段不足。前端既有结果展示6项通过。关系修复后的真实模型、完整前端和最终全组回归待完成。

全组回归正运行，日志 outputs/agent-metric-20261113/all-nov14-c.log 位于D工作区。之前暂停中的两次全组测试未取得最终回执，其不完整日志保留。下一步读取本次终态结果，修复实际失败，补真实模型有限回归，再完成来源摘要核对和GitHub草稿同步。

开放任务M01仍有指标漏交和多报。当前关系解释覆盖同源已交付字段，跨记录关系义务及模型漏选关系主题仍需补强。当前评分尚无新增复评，95+目标继续按原八维/87项推进。
''',encoding='utf-8')
p=root/'docs/CURRENT_WORK_PLAN.md'
s=p.read_text(encoding='utf-8')
marker='> 2026-11-14 指标读取批进行中。当前工作分支 feature/agent-metric-reads-20261113，最新证据与待办见 AGENT_METRIC_READ_PROGRESS.md。下方PR74为上一批已完成基线。\n\n'
p.write_text(marker+s,encoding='utf-8')
print('Recorded independent 5/8 first screen and unfinished follow-ups.')
