import hashlib,json,re,runpy,sys,urllib.request,urllib.error,urllib.parse
from pathlib import Path
out=Path('validation/climate-20261107');mode=sys.argv[1]
helper='../outputs/vra-prototype-sync-20261104/github_sync.py';sys.argv=[helper,'load_only'];ns=runpy.run_path(helper);call=ns['call']
number=json.loads((out/'pr-created.json').read_text())['number'];pr=call('/pulls/'+str(number));head=pr['head']['sha'];checks=call('/commits/'+head+'/check-runs')['check_runs']
assert head==(out/'release-head.txt').read_text().strip()
assert sorted(x['name'] for x in checks)==sorted(['backend','frontend','api-parser-contract']*2)
assert len(checks)==6 and all(x['status']=='completed' and x['conclusion']=='success' for x in checks),'Six exact-head checks not yet successful'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
opener=urllib.request.build_opener(NoRedirect)
records=[]
for check in checks:
 if check['name']!='backend':continue
 job=int(check['html_url'].rstrip('/').split('/')[-1]);url=f'https://api.github.com/repos/wt009916-ship-it/VRA-trust/actions/jobs/{job}/logs'
 req=urllib.request.Request(url,headers={'Authorization':'Bearer '+ns['token'],'Accept':'application/vnd.github+json','User-Agent':'VRA-authorized-acceptance'})
 try:
  with opener.open(req,timeout=30) as response:data=response.read()
 except urllib.error.HTTPError as error:
  if error.code!=302:raise RuntimeError('GitHub log download failed: '+str(error.code)) from None
  location=error.headers['Location'];parsed=urllib.parse.urlsplit(location)
  assert parsed.scheme=='https' and any((parsed.hostname or '').endswith(s) for s in ['.githubusercontent.com','.blob.core.windows.net','.github.com'])
  # Never forward GitHub credentials to the signed download host.
  with urllib.request.urlopen(location,timeout=30) as response:data=response.read()
 path=out/f'{mode}-ci-backend-{job}.log'
 with path.open('xb') as stream:stream.write(data)
 matches=re.findall(r'(\d+) passed, (\d+) skipped,.*?(\d+) subtests passed in ([\d.]+)s',data.decode('utf-8',errors='replace'))
 assert matches,'No completed pytest summary';passed,skipped,subtests,seconds=matches[-1]
 records.append({'job':job,'path':path.as_posix(),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'passed':int(passed),'skipped':int(skipped),'subtests':int(subtests),'seconds':float(seconds)})
receipt={'pr':number,'head':head,'checks':[{'name':x['name'],'id':x['id'],'conclusion':x['conclusion'],'url':x['html_url']} for x in checks],'backend_logs':records}
(out/f'{mode}-remote-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
