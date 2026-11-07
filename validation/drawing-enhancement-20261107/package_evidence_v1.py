import gzip,hashlib,json,re,subprocess
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1]
def digest(raw):return hashlib.sha256(raw).hexdigest()
final=json.loads((out/'candidate-source-v2.json').read_text())
linux=json.loads((out/'linux-source-v1.json').read_text())
old={x['path']:x['sha256'] for x in linux['files']}
differences=[]
for row in final['files']:
    raw=(Path(final['root'])/row['path']).read_bytes();assert digest(raw)==row['sha256']
    if old[row['path']]!=row['sha256']:differences.append(row['path'])
assert sorted(differences)==['docs/DRAWING_GEOMETRY_PROGRESS.md','frontend/src/drawing-geometry-ui.js']
prepared=json.loads((out/'browser-prepared-v2.json').read_text())
assets={p.relative_to(Path(final['base'])/'git-dist-v1').as_posix():digest(p.read_bytes()) for p in (Path(final['base'])/'git-dist-v1').rglob('*') if p.is_file()}
assert assets==prepared['assets'] and len(assets)==5
bench=json.loads((out/'benchmark-windows-v3.json').read_text())
files={row['path']:row['sha256'] for row in final['files']}
for name,value in bench['source_versions'].items():assert files['backend/'+name]==value,name
proof={'application_commit':final['application_commit'],'linux_commit':linux['application_commit'],
       'linux_to_final_differences':differences,'all_backend_tests_scripts_identical':True,
       'assets':assets,'exact_git_build_matches_browser':True,'git_dist':str(Path(final['base'])/'git-dist-v1')}
with (out/'source-and-assets-verified-v1.json').open('x',encoding='utf-8') as f:json.dump(proof,f,indent=2)
entries=[]
source=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-benchmark-1b83fd1ba09540d18fbf23ffa961148b/windows-v3')
for p in sorted(source.glob('*-api.json')):
    raw=p.read_bytes();text=raw.decode('utf-8')
    assert not re.search(r'(?i)"(?:password|csrf_token|access_token|api_key)"\s*:\s*"[^"\s]+"',text)
    entries.append({'path':p.name,'sha256':digest(raw),'bytes':len(raw),'text':text})
assert len(entries)==12
with (out/'public-api-text-v1.jsonl.gz').open('xb') as f,gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as z:
    for row in entries:z.write((json.dumps(row,ensure_ascii=False)+'\n').encode())
with gzip.open(out/'public-api-text-v1.jsonl.gz','rt',encoding='utf-8') as f:assert [json.loads(x) for x in f]==entries
with (out/'public-package-v1.json').open('x',encoding='utf-8') as f:
    json.dump({'files':[{k:v for k,v in x.items() if k!='text'} for x in entries],
               'scope':'12 public/synthetic Windows raw API results. Linux summary included separately; raw files retained in isolated Linux path. No auth/session/database.'},f,indent=2)
print(json.dumps({'source_proof':proof,'public_api_results':len(entries),'archive_bytes':(out/'public-api-text-v1.jsonl.gz').stat().st_size}))
