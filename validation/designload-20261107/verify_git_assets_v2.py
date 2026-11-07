import hashlib,json
from pathlib import Path
out=Path(__file__).parent
git=json.loads((out/'git-source-v2.json').read_text());browser=json.loads((out/'browser-prepared-v1.json').read_text())
left=Path(git['root'])/'dist';right=Path(browser['source'])/'frontend/dist'
def inventory(root):
 return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
a,b=inventory(left),inventory(right)
assert a==b,{'git_only':sorted(set(a)-set(b)),'tested_only':sorted(set(b)-set(a)),
              'changed':[n for n in a if n in b and a[n]!=b[n]]}
record={'candidate':git['candidate'],'assets':a,'same_as_browser_tested_bytes':True,
        'normalized_source_files':git['normalizations'],'backend_source_bytes_unchanged':True}
with (out/'git-assets-v2.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps({'assets':len(a),'same_as_browser_tested_bytes':True}))
