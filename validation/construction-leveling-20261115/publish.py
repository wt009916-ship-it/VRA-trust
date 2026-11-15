import ast,hashlib,json,runpy,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).parent
repo=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
dest=repo/'validation/construction-leveling-20261115'
base='49306007f6b7c886f442f307ddc82ffec4dcd00e'
def git(*args):return subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','-c','core.safecrlf=false',*args],cwd=repo,text=True,encoding='utf-8').strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert git('rev-parse','HEAD')==base
assert git('branch','--show-current')=='feature/construction-resource-leveling-20261115'
assert git('remote','get-url','github')=='https://github.com/wt009916-ship-it/VRA-trust.git'
for name in ['capability.log','publish.py']:
 shutil.copy2(root/name,dest/name)
p=dest/'runtime-source-metadata/backend/agent_capabilities.py';p.parent.mkdir(parents=True);shutil.copy2(repo/'backend/agent_capabilities.py',p)
def entries(p):
 tree=ast.parse(p.read_text(encoding='utf-8'))
 node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ENTRIES' for t in n.targets))
 return ast.literal_eval(node.value)
old=entries(dest/'runtime-source-final/backend/agent_capabilities.py');new=entries(repo/'backend/agent_capabilities.py')
assert {k:v[0] for k,v in old.items()}=={k:v[0] for k,v in new.items()}
assert [k for k in new if new[k]!=old[k]]==['schedule_cpm']
for directory in ['model-first','model-after-catalog']:
 for p in (dest/directory).glob('L*.json'):
  task=json.loads(p.read_text(encoding='utf-8'))
  assert not any(e['tool']=='capability_lookup' for e in task['events'])
(dest/'metadata-update.json').write_text(json.dumps({'scope':'Only schedule_cpm capability metadata and implementation locator, after model runs','identifiers_and_labels_unchanged':True,'capability_lookup_called_in_recorded_model_tasks':False,'model_rerun':False},indent=2)+'\n')
for p in (root/'frontend-build/src').glob('*.js'):assert sha(p)==sha(repo/'frontend/src'/p.name),p.name
receipt={'build_success':True,'build_ms':429,'frontend_passed':256,'browser':'deferred_by_user','lock_sha256':sha(repo/'frontend/package-lock.json'),'assets':{p.relative_to(root/'frontend-build/dist').as_posix():sha(p) for p in (root/'frontend-build/dist').rglob('*') if p.is_file()},'source_js_hashes':{p.name:sha(p) for p in (repo/'frontend/src').glob('*.js')}}
(dest/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
manifest={'base':base,'files':{p.relative_to(dest).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='manifest-final.json'},'scope':'Additive final receipt; original 303-file manifest unchanged. No raw public datasets, private runtime, credentials, dependencies or model weights.'}
(dest/'manifest-final.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
git('add','--','.gitattributes','backend','frontend/src','frontend/tests/schedule-leveling.test.js','shared/schemas/openapi.json','tests/test_calculation_provenance.py','tests/test_construction_leveling.py','tests/test_leveling_agent_recovery.py','tests/fixtures/resource_leveling_reference.json','docs/CURRENT_SCORE.json','docs/CURRENT_WORK_PLAN.md','docs/IMPLEMENTATION_STATUS.md','docs/CONSTRUCTION_RESOURCE_LEVELING_DELIVERY.md','docs/history/CURRENT_SCORE_20261115_before_resource_leveling.json')
git('add','-f','--','validation/construction-leveling-20261115')
git('diff','--cached','--check','--','backend','frontend','tests','docs','shared/schemas','.gitattributes')
names=git('diff','--cached','--name-only').splitlines()
assert not any('/private-' in n or '/node_modules/' in n or n.endswith(('.gguf','.sqlite3','.zip','.sm')) for n in names)
assert 'backend/construction.py' not in names
git('commit','-m','feat(construction): preserve source-bound resource-constrained schedules')
head=git('rev-parse','HEAD')
for name,expected in manifest['files'].items():
 raw=subprocess.check_output(['git','show',head+':validation/construction-leveling-20261115/'+name],cwd=repo)
 assert hashlib.sha256(raw).hexdigest()==expected['sha256'],name
(root/'committed-evidence-check.json').write_text(json.dumps({'head':head,'verified_files':len(manifest['files']),'mismatches':0},indent=2)+'\n')
git('push','github','HEAD:refs/heads/feature/construction-resource-leveling-20261115')
sys.argv=['github_sync.py','load_only'];g=runpy.run_path('D:/稀土agent-稀土制暖全流程/outputs/vra-prototype-sync-20261104/github_sync.py')
body='''原施工计划只能报告资源超配，不能按已声明容量给出可执行的时间安排。本PR保留原CPM记录，另存来源hash绑定、完整占用确认和明确优先序下的资源受限方案，输出工序起止、原CPM延后、资源峰值及精确数学下界。原件/证据/项目/计算版本失效时，方案、报告及Agent撤下当前数值。没有改写实际进度，也不承诺现场安全或通用最优。

验收：4个提前冻结独立算例 + 6个提前固定PSPLIB算例，真实HTTP10例/20检查通过，独立Fraction逐项检查容量和依赖。公开6例3个达到已知最优，另外3例多11/20/1，完整保留反例。256前端及构建通过，实际浏览器按用户明确选择暂缓。

固定9B模型首次新题1/3。发现选择前缺字段含义和空所选事实仍生成交付工具的真实失败；补齐静态字段契约及所选投影工具可用性后，L01/L03原问法、原模型、原5轮/15事件预算回归2/2；L02不重复。不是首答3/3或全Agent可靠。没有训练和答案替身。

17初始新测试、独立分数/派生版本补验、52来源回归、45目录相关通过后修正一项测试次数假设并单项通过、17能力目录回归；不相加重叠次数。首次相关回归163通过/3故障注入模块假设失败也保留，全部原拒绝写入/来源撤下断言保持。旧临时Git对象库异常后迁到PR81精确提交的干净检出，182个源码/测试文件字节匹配；旧库及失败保留，不删除历史引用。

候选仍79，正式已发布76；原八维87场景未全重跑，95+未达。原件、私有账号/数据库、模型权重、依赖及公共数据原包不入库。仅提交原始运行日志、方法、参考摘要、实际源码快照与清单。依赖PR81；保持草稿，不合并、不部署。最终精确提交CI待核验。
'''
pr=g['call']('/pulls','POST',{'title':'feat: 来源绑定的施工资源受限排程与独立公开基准','head':'feature/construction-resource-leveling-20261115','base':'feature/agent-record-comparison-20261115','draft':True,'body':body+'\n\n精确提交：'+head+'；提交证据'+str(len(manifest['files']))+'项SHA256匹配，0不一致。'})
(root/'pr.json').write_text(json.dumps({'number':pr['number'],'url':pr['html_url'],'head':head,'base':base,'evidence_files':len(manifest['files'])},indent=2)+'\n')
print(json.dumps({'pr':pr['number'],'url':pr['html_url'],'head':head,'evidence_files':len(manifest['files'])}))
