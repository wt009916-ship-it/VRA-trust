import hashlib,json,subprocess,sys,tempfile,uuid
from pathlib import Path
repo=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
sys.path.insert(0,str(repo))
from backend.private_storage import private_mkdir
root=private_mkdir(Path(tempfile.gettempdir())/('vra-designload-ui-'+uuid.uuid4().hex))
frozen=json.loads((out/'final-source-v5.json').read_text())
source=root/'source';source.mkdir()
for record in frozen['files']:
    raw=(Path(frozen['root'])/record['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==record['sha256']
    target=source/record['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
with (out/'frontend-build-v2.log').open('xb') as log:
    p=subprocess.run(['node',str(repo/'frontend/node_modules/vite/bin/vite.js'),'build','--outDir',str(source/'frontend/dist')],
                     cwd=repo/'frontend',stdout=log,stderr=subprocess.STDOUT)
assert p.returncode==0
plan={'root':str(root),'source':str(source),'frozen_source':frozen['root'],'port':18774}
with (out/'browser-prepared-v2.json').open('x',encoding='utf-8') as stream:json.dump(plan,stream,indent=2)
print(json.dumps(plan))
