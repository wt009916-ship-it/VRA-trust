"""Retain exact PR74 CI metadata and completed job logs; no credential serialization."""
import hashlib,json,runpy,sys,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urlparse
sys.argv=['github_sync.py','load_only'];g=runpy.run_path('D:/稀土agent-稀土制暖全流程/outputs/vra-prototype-sync-20261104/github_sync.py')
root=Path(__file__).resolve().parent/'pre-fix-ci';root.mkdir(exist_ok=True);head='2db70b4a418b2a5aea141cb952e9bb99de34de0c'
pr=g['call']('/pulls/74')
checks=g['call']('/commits/'+head+'/check-runs')['check_runs'];receipt={'product_commit':head,'pr':74,'merged':pr['merged'],'checks':[{k:c[k] for k in ('name','status','conclusion','html_url','started_at','completed_at')} for c in checks],'logs':{}}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
opener=urllib.request.build_opener(NoRedirect)
for check in checks:
    name=check['name'];job=check['html_url'].rsplit('/',1)[1]
    if check['status']!='completed':continue
    p=root/(name+'.log')
    if not p.exists():
        req=urllib.request.Request(g['base']+'/actions/jobs/'+job+'/logs',headers={'Authorization':'Bearer '+g['token'],'Accept':'application/vnd.github+json','User-Agent':'VRA-authorized-audit'})
        try:
            with opener.open(req,timeout=30) as response:data=response.read()
        except urllib.error.HTTPError as exc:
            assert exc.code==302;url=exc.headers['Location'];parsed=urlparse(url);assert parsed.scheme=='https' and (parsed.hostname.endswith('.blob.core.windows.net') or parsed.hostname.endswith('.actions.githubusercontent.com'))
            # Signed log URL only. The GitHub Authorization header never follows it.
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VRA-authorized-audit'}),timeout=30) as response:data=response.read()
        p.write_bytes(data)
    receipt['logs'][p.name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
receipt['all_success']=set(c['name'] for c in checks)=={'backend','frontend','api-parser-contract'} and all(c['status']=='completed' and c['conclusion']=='success' for c in checks)
(root/'ci-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'all_success':receipt['all_success'],'checks':[{k:c[k] for k in ('name','status','conclusion')} for c in checks],'logs':list(receipt['logs'])}))
