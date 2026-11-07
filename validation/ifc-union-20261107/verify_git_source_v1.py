import hashlib,io,json,os,subprocess,sys,tarfile,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
index=json.loads((repo/'docs/IFC_SELECTED_UNION_EVIDENCE.json').read_text())
for row in index['evidence_files']+index['publications']:
    blob=subprocess.check_output(['git','show',head+':'+row['path']])
    assert hashlib.sha256(blob).hexdigest()==row['sha256'],row['path']
plan=json.loads((out/'candidate-source-v2.json').read_text())
root=Path(tempfile.gettempdir())/('vra-hourly-git-'+uuid.uuid4().hex);root.mkdir()
archive=subprocess.check_output(['git','archive','--format=tar',head,'backend','frontend','scripts','fixtures','cases','shared','pyproject.toml'])
normalizations=[];files=[]
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    for item in tar.getmembers():
        if not item.isfile():continue
        target=root/item.name;assert target.resolve().is_relative_to(root.resolve())
        raw=tar.extractfile(item).read();target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        files.append({'path':item.name,'sha256':hashlib.sha256(raw).hexdigest()})
for row in plan['files']:
    local=Path(plan['root'])/row['path'];target=root/row['path']
    if not target.exists():continue
    old=local.read_bytes();new=target.read_bytes()
    if old!=new:
        assert old.replace(b'\r\n',b'\n')==new,row['path']
        assert not row['path'].startswith('backend/'),'Physics bytes changed after full regression'
        normalizations.append(row['path'])
modules=(repo/'frontend/node_modules').resolve()
subprocess.run(['cmd','/c','mklink','/J',str(root/'frontend/node_modules'),str(modules)],check=True,stdout=subprocess.DEVNULL)
with (out/'git-build-v1.log').open('xb') as log:
    cp=subprocess.run(['node',str(modules/'vite/bin/vite.js'),'build'],cwd=root/'frontend',stdout=log,stderr=subprocess.STDOUT)
assert cp.returncode==0
assets={p.relative_to(root/'frontend/dist').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'frontend/dist').rglob('*') if p.is_file()}
served=Path(plan['root'])/'frontend/dist'
assert assets=={p.relative_to(served).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in served.rglob('*') if p.is_file()}
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe')
physics=subprocess.check_output([sys.executable,'-B','-c','from backend.core import code_hash;print(code_hash())'],cwd=root,env=env,text=True).strip()
previous=json.loads((out/'runtime-context-v1.json').read_text())
assert physics==previous['physics_hash']
record={'application_commit':head,'root':str(root),'files':files,'evidence_hashes_verified':len(index['evidence_files']+index['publications']),
        'physics_hash':physics,'newline_normalizations':normalizations,'assets':assets,'browser_assets_byte_identical':True}
with (out/'git-source-verified-v1.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps({k:v for k,v in record.items() if k not in ['files','assets']}))
