import hashlib,json,runpy,sys
from pathlib import Path
root=Path(__file__).parent
head='a37d375692e239e7f4bad72fa1cc7aef38ddeec5'
receipt={'head':head,'pr':82,'all_success':True,
 'backend':{'run':43716529590,'job':132819175960,'passed':2120,'skipped':22,'warnings':2,'subtests':6,'seconds':976.62},
 'frontend':{'run':43716529609,'job':132819175910,'passed':256,'build_ms':232},
 'api':{'run':43716529624,'job':132819175873,'passed':30,'warnings':1,'seconds':17.54},
 'candidate_score':79,'published_score':76,'score_delta':0,'browser':'deferred_by_user',
 'logs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.log')}}
assert '2120 passed, 22 skipped' in (root/'backend.log').read_text(encoding='utf-8')
assert '# pass 256' in (root/'frontend.log').read_text(encoding='utf-8')
assert '30 passed' in (root/'api.log').read_text(encoding='utf-8')
(root/'ci-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
sys.argv=['github_sync.py','load_only']
g=runpy.run_path('D:/稀土agent-稀土制暖全流程/outputs/vra-prototype-sync-20261104/github_sync.py')
pr=g['call']('/pulls/82');assert pr['head']['sha']==head
body=pr['body']
marker='\n\n最终精确 CI 收口：'
if marker in body:body=body.split(marker)[0]
body+=marker+head+'；三工作流全部成功。后端2120通过、22跳过、2警告、6子测试（976.62秒）；前端256及构建232ms；接口30通过（17.54秒）。跳过不计通过。原始失败和非最优反例保留，候选79／正式76不变。草稿未合并、未部署。'
g['call']('/pulls/82','PATCH',{'body':body})
print(json.dumps({'pr':82,'head':head,'all_success':True}))
