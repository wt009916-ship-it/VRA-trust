NOTE = "\n## 中文未见验收：正式交付1/3，完整要求0/3\n\n3项、14次真实模型请求，应用源码未再调整。H01正式交付正确，但模型原文将记录ID的 `9aa75571...` 写为 `9aa75557...`，对象引用错误，因此不能判完整任务通过。H02在第五轮提交了最后一项availability，但finish=false，随后触发iteration budget exhausted，已有三项交付均未做最终当前重检。H03只反复输出失效解释，没有professional_limit；最终状态succeeded仍有unfulfilled目标，必须按业务失败记录。原始日志与人工复核保留，不回改题目或重算成绩。\n\n|编号|功能/描述|复现|预期|实际|级别|证据|建议|\n|---|---|---|---|---|---|---|---|\n|SR-02|原文对象编号失真|冻结H01中文混合任务|所有引用对应实际声明记录|原生卡正确、自由原文ID错一位|高|holdout-4b/model-call-003.json、results.json|对自由原文标识符做精确引用核对；不能仅检查数值/卡片|\n|SR-03|预算结束丢失已提交任务的当前核验|H02三目标，最后availability finish=false|有界结束，已有交付最终复核；不把模型结束标志当业务唯一依据|第五轮后直接failed；未完成当前重检，无正式answer|高|holdout-4b/model-call-005至009、results.json|类型化终止与部分交付，预留最终重检；未读/未交付不能自动补成功|\n|SR-04|失效解释不能形成正式交付|H03墙体stale＋设备availability|按原ID提交限制且复核来源|三轮只写文字，wall unfulfilled；任务状态与业务完成不等价|高|holdout-4b/model-call-010至014、results.json|待交付目标提供明确下一工具/参数类型和终止状态；不靠重复泛化提示或增加预算|\n\n本批仍是开发工作树阶段；先同步可审阅开发分支，不合并main、不更新原型。下一任务以SR-03的类型化有界结束、SR-04明确限制交付及SR-02引用核验组成同一Agent任务完整性里程碑；不得为17行修复单独重复全量发布流程。\n"
from pathlib import Path
import json,hashlib,re,subprocess,shutil
base=Path('validation/agent-scope-routing-20261107')
p=Path('docs/AGENT_SCOPE_ROUTING_DELIVERY.md')
p.write_text(p.read_text(encoding='utf-8').split('\n## 中文未见验收：')[0]+NOTE,encoding='utf-8',newline='\n')
p=Path('docs/CURRENT_WORK_PLAN.md');s=p.read_text(encoding='utf-8')
s=s.replace('中文冻结未见题另测','中文冻结未见3任务14请求：正式交付1/3，原文错编号导致完整要求0/3；SR-02/03/04开放。中文冻结未见题详见')
s=s.replace('接下来按实际失败处理Agent解释/恢复/注入','下一项直接处理SR-03类型化有界结束、SR-04限制正式交付及SR-02原文编号核验，合并为一次Agent完整性里程碑；随后处理解释/恢复/注入')
p.write_text(s,encoding='utf-8',newline='\n')
reviews=[]
for cohort in ['fresh','holdout']:
 data=json.loads((base/(cohort+'-4b')/'results.json').read_text(encoding='utf-8'))
 assert data['completed'] and data['server_stopped'] and data['loopback_verified'] and data['unauthenticated_status']==401
 for c in data['cases']:
  task=c['task'];allowed={x.get('record_id') for x in task['read_requests']} - {None}
  mentioned=set(re.findall(r'(?:thermal|cost|lifecycle|engineering|schedule|operation)_[a-f0-9]+\b',task.get('llm_commentary') or ''))
  reviews.append({'cohort':cohort,'case':c['id'],'formal_checks_pass':c['automated_pass'],'unknown_prose_ids':sorted(mentioned-allowed),'full_case_pass':c['automated_pass'] and not mentioned-allowed,'prose_present':bool(task.get('llm_commentary')),'note':'Absence of prose is not evidence of prose competence; source IDs must match exactly'})
(base/'manual-review.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2),encoding='utf-8')
(base/'retained-worktree.patch').write_bytes(subprocess.check_output(['git','diff','--','backend/backup.py','backend/extensions.py','backend/store.py','shared/schemas/openapi.json','tests/test_backup.py']))
shutil.copyfile('backend/cad_catalog.py',base/'retained-cad_catalog.py')
a=Path('.gitattributes');s=a.read_text(encoding='utf-8');rule='validation/agent-scope-routing-20261107/** -text'
if rule not in s:a.write_text(s+'\n'+rule+'\n',encoding='utf-8',newline='\n')
selected=[p for p in base.iterdir() if p.is_file() and p.suffix in {'.py','.json','.sha256','.patch','.log'}]
selected += [p for folder in ['fresh-4b','holdout-4b'] for p in (base/folder).iterdir() if p.is_file() and p.suffix in {'.json','.log'}]
index={'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'release_status':'unpublished_development_branch','score':77,'validation_scope':'dirty worktree, full backend hashes in actual model results; retained unrelated catalog changes attached for replay','files':[{'path':str(p).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(selected)]}
Path('docs/AGENT_SCOPE_ROUTING_EVIDENCE.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'evidence_files':len(selected),'bytes':sum(p.stat().st_size for p in selected),'reviews':reviews},ensure_ascii=False))
