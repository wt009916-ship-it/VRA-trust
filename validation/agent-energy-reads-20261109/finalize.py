"""Close evidence only after the exact final CI is successful; never raise the score."""
import hashlib,json,re,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
FINAL='67e79959fbdf119f8ed782109e28bf29811b05b2'
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def replace(path,old,new):
 p=ROOT/path;s=p.read_text(encoding='utf-8-sig');assert old in s,(path,old);p.write_text(s.replace(old,new),encoding='utf-8')
ci=json.loads((BASE/'post-ci/ci-receipt.json').read_text());assert ci['all_success'] and ci['product_commit']==FINAL and not ci['merged']
log=(BASE/'post-ci/backend.log').read_text(encoding='utf-8');matches=re.findall(r'(\d+) passed, (\d+) skipped, (\d+) warnings, (\d+) subtests passed in ([0-9.]+)s',log);assert matches,matches
passed,skipped,warnings,subtests,seconds=matches[-1]
summary=f'三项CI全部成功：后端{passed}通过/{skipped}跳过/{warnings}警告/{subtests}子测试通过，{seconds}秒；前端239及lint/build；接口集成30通过/1警告。跳过不计通过。'
replace('docs/AGENT_ENERGY_READ_DELIVERY.md','最终67e7995精确CI进行中。',summary)
replace('docs/AGENT_ENERGY_READ_DEFECTS.md','默认工具目录超出既定预算（修复待最终CI）','默认工具目录超出既定预算（已修复）')
replace('docs/AGENT_ENERGY_READ_DEFECTS.md','最终CI待回执。',summary)
replace('docs/RESCORE_20261113_AGENT_ENERGY.md','最终全组尚在运行，不提前记通过。',summary)
replace('docs/CURRENT_WORK_PLAN.md','Agent能耗读取收口中','Agent能耗读取已收口')
replace('docs/CURRENT_WORK_PLAN.md','精确CI尚在收口。',summary)
replace('docs/CURRENT_WORK_PLAN.md','等待67e7995精确后端CI，完成后归档机器回执和更新评分版本；不重跑本机全组。','67e7995精确三项CI已成功，机器回执已归档，评分版本同步但分数不变；未重跑本机全组。')
replace('docs/AGENT_ENERGY_READ_PLAN.md','精确CI进行中。','最终67e7995三项精确CI成功，开发/证据收口；本批模型能力仍未过门槛。')
p=ROOT/'docs/CURRENT_SCORE.json';score=json.loads(p.read_text(encoding='utf-8'));assert score['published']['score']==76 and score['candidate']['score']==78.5
score['candidate'].update(product_commit=FINAL,pr=72,merged=False,previous_score=78.5,delta=0,changed_subitem={'name':'AI Agent/真实工程读取与任务完成','before':9.5,'after':9.5,'maximum':15,'scope':'Two real energy read tools added. Strict first screen12/16; critical E13/E14 fail. Two new repair questions pass but do not replace original failures. No score increase.'})
score.update(review='docs/RESCORE_20261113_AGENT_ENERGY.md',ci_receipt='validation/agent-energy-reads-20261109/post-ci/ci-receipt.json')
score['latest_capability_screen']={'report':'docs/AGENT_ENERGY_READ_DELIVERY.md','evidence':'validation/agent-energy-reads-20261109/first-screen-assessment.json','adopted':False,'delta':0,'scope':'16 new actual API/model tasks12 strict passes; E06/E10/E13/E14 fail, E13/E14 critical. Raw responses retained. No full Agent reliability claim.'}
score['latest_delivery']={'report':'docs/AGENT_ENERGY_READ_DELIVERY.md','first_model_product_commit':'fa30deff733b331f052f6da764c67b1cba5fc89a','repair_model_product_commit':'0d46616e1a7682ee5f44c5e3242809570cb67f0b','final_product_commit':FINAL,'final_increment':'Default unscoped connectivity/status catalogue is read-only; explicit task tool schemas unchanged.55 scoped regressions plus exact CI. No model screen rerun on final metadata-only increment.','next_plan':'docs/AGENT_INTENT_BINDING_PLAN.md'}
assert sum(d['score'] for d in score['candidate']['dimensions'])==78.5;save(p,score)
save(BASE/'final-summary.json',{'final_product_commit':FINAL,'pr':72,'ci_all_success':True,'backend':{'passed':int(passed),'skipped':int(skipped),'warnings':int(warnings),'subtests':int(subtests),'seconds':float(seconds)},'frontend_tests':239,'integration_tests':30,'first_model_screen':{'passed':12,'total':16,'critical_failures':['E13','E14'],'adopted':False},'repair_holdout':{'passed':2,'total':2,'replaces_first_screen':False},'candidate_score':78.5,'published_score':76,'browser':'deferred_by_user','merged':False,'deployed':False,'training_expanded':False,'full_visual_redesign_started':False})
files=[p for p in BASE.rglob('*') if p.is_file() and p != BASE/'manifest.json']
save(BASE/'manifest.json',{'product_commit':FINAL,'file_count':len(files),'files':{str(p.relative_to(BASE)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},'notice':'Original failures and raw messages retained; no private runtime DB, credentials, model weights or large native outputs included.'})
print(summary);print('evidence_files',len(files))
