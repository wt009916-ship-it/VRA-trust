import json,runpy,sys
from pathlib import Path
out=Path('validation/climate-20261107')
receipt=json.loads((out/'final-remote-receipt.json').read_text())
expected=(out/'release-head.txt').read_text().strip()
assert receipt['head']==expected
helper='../outputs/vra-prototype-sync-20261104/github_sync.py'
sys.argv=[helper,'load_only'];call=runpy.run_path(helper)['call']
number=json.loads((out/'pr-created.json').read_text())['number'];pr=call('/pulls/'+str(number))
assert pr['head']['sha']==expected and pr['base']['ref']=='main'
assert pr['base']['sha']=='7504d8cb450f551581698b7c4094e013e3530761','Base changed; verify the new integration before merging'
checks=call('/commits/'+expected+'/check-runs')['check_runs']
assert len(checks)==6 and sorted(x['name'] for x in checks)==sorted(['backend','frontend','api-parser-contract']*2)
assert all(x['status']=='completed' and x['conclusion']=='success' for x in checks)
assert pr['mergeable'] and not pr['merged']
result=call('/pulls/'+str(number)+'/merge','PUT',{'sha':expected,'merge_method':'merge'})
assert result.get('merged')
record={'pr':number,'url':pr['html_url'],'tested_head':expected,'merge_sha':result['sha'],'merged':True}
(out/'merge-receipt.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record))
