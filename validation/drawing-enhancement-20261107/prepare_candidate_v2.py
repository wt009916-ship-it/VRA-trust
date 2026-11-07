"""Freeze exact Git bytes, with explicit worktree newline comparison; no original runtime data."""
import hashlib,io,json,subprocess,sys,tarfile,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).parent;sys.path.insert(0,str(repo))
from backend.private_storage import private_mkdir
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert head==(out/'candidate-v3.txt').read_text().strip()
assert not subprocess.check_output(['git','status','--porcelain'],text=True).strip()
tracked=subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
names=['backend','tests','frontend/src','frontend/tests','frontend/index.html','frontend/package.json','frontend/package-lock.json',
       'scripts','shared','fixtures','cases','docs','.github']+[n for n in tracked if n and '/' not in n]
archive=subprocess.check_output(['git','archive','--format=tar',head,*names])
base=private_mkdir(Path(tempfile.gettempdir())/('vra-drawing-candidate-'+uuid.uuid4().hex));root=base/'source';root.mkdir()
records=[];normalized=[]
with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
    for item in stream.getmembers():
        if not item.isfile():continue
        name=item.name;raw=stream.extractfile(item).read();local=(repo/name).read_bytes()
        if local!=raw:
            assert local.replace(b'\r\n',b'\n')==raw,name
            if name.endswith('.json'):assert json.loads(local)==json.loads(raw)
            normalized.append(name)
        target=root/name;assert target.resolve().is_relative_to(root.resolve())
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        records.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'workspace_sha256':hashlib.sha256(local).hexdigest(),'bytes':len(raw)})
record={'application_commit':head,'base':str(base),'root':str(root),'files':records,'newline_normalizations':normalized,'source':'exact Git archive'}
with (out/'candidate-source-v2.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
with (out/'browser-build-v2.log').open('xb') as log:
    result=subprocess.run(['node',str(repo/'frontend/node_modules/vite/bin/vite.js'),'build','--outDir',str(root/'frontend/dist')],cwd=repo/'frontend',stdout=log,stderr=subprocess.STDOUT)
assert result.returncode==0
assets={p.relative_to(root/'frontend/dist').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'frontend/dist').rglob('*') if p.is_file()}
with (out/'browser-prepared-v2.json').open('x',encoding='utf-8') as f:json.dump({'root':str(base),'source':str(root),'port':18774,'application_commit':head,'assets':assets},f,indent=2)
print(json.dumps({'application_commit':head,'root':str(root),'files':len(records),'normalizations':normalized,'assets':len(assets)}))

