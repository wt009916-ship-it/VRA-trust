from pathlib import Path
import json,shutil,subprocess
ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');B=ROOT/'validation/agent-phase-contract-20261113';L=Path('D:/稀土agent-稀土制暖全流程/outputs/agent-phase-20261113');HEAD='bb21a9cfc65922c45714d6d3c213a90d5299ed8e';CODE='aaed498af3839bd48b2b54da4c2b110f336f3c0d'
subprocess.run(['git','diff','--exit-code',CODE,HEAD,'--','backend','frontend','shared'],cwd=ROOT,check=True)
s=(B/'fetch_ci.py').read_text(encoding='utf-8');(B/'fetch_intermediate_ci.py').write_text(s.replace("/'post-ci'","/'pre-fixture-ci'").replace("pr=g['call']('/pulls/74');assert pr['head']['sha']==head","pr=g['call']('/pulls/74')"),encoding='utf-8')
p=B/'post-ci';q=B/'pre-fixture-ci';assert not q.exists();p.rename(q)
(B/'fetch_ci.py').write_text(s.replace(CODE,HEAD),encoding='utf-8')
for filename in ['AGENT_PHASE_ACTIONS_DELIVERY.md','RESCORE_20261113_PHASE_ACTIONS.md','AGENT_INTENT_BINDING_PLAN.md']:
 p=ROOT/'docs'/filename;s=p.read_text(encoding='utf-8').replace(CODE,HEAD).replace('最终产品aaed498','最终产品bb21a9c').replace('PR74/aaed498','PR74/bb21a9c')
 if filename=='AGENT_PHASE_ACTIONS_DELIVERY.md':
  s=s.replace('故最终aaed498必须重新检查；两个提交的原CI均保留','故aaed498必须重新检查。首个完整CI另发现27项旧测试驱动未适配现行协议；两个驱动修正后56项受影响回归通过，最终bb21a9c的业务源码与aaed498完全相同；三个提交的原CI均保留')
  s=s.replace('最终产品单项复验通过','aaed498业务源码单项复验通过')
 p.write_text(s,encoding='utf-8')
p=B/'README.md';s=p.read_text(encoding='utf-8').replace('最终aaed498','最终bb21a9c（业务源码同aaed498）').replace('两次精确CI','三次精确CI');p.write_text(s,encoding='utf-8')
p=B/'assessment.json';d=json.loads(p.read_text(encoding='utf-8'));d.update(final_product_commit=HEAD,final_business_code_commit=CODE,final_increment='Only engineering/outage test fixtures changed after final bounded live source-status repair; backend/frontend/shared Git diff empty.');p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=B/'assess.py';s=p.read_text(encoding='utf-8').replace("'final_product_commit':'"+CODE+"'", "'final_product_commit':'"+HEAD+"','final_business_code_commit':'"+CODE+"'");p.write_text(s,encoding='utf-8')
p=B/'source-integrity.json';d=json.loads(p.read_text(encoding='utf-8'));d.update(final_product_commit=HEAD,final_business_code_commit=CODE,final_test_only_diff_verified=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=B/'environment-failures.json';d=json.loads(p.read_text(encoding='utf-8'));d['failures'].append({'type':'full_CI','step':'2db70b4 backend','result':'28 failed,1932 passed,22 skipped,2 warnings,6 subtests','detail':'One nonnumeric review regression fixed in aaed498; 4 engineering driver assertions still read old numeric schema,23 fault-injected transport cases returned old native tool-call messages. Updated only those explicit mocks to current fact-selection/action wire; independent arithmetic, retries, no duplicated writes and stale checks preserved; 56 affected cases passed. bb21a9c business source unchanged.'});p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ['backend-ci-fixture-fix.log','fix_ci_fixtures.py','diagnose_next.py']:shutil.copyfile(L/name,B/name)
print('Final product metadata updated; business source equivalence verified; earlier CI archives separated.')
