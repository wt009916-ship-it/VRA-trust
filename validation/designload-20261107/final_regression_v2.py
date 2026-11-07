"""Freeze final Agent source and reuse byte-identical native references only when physics is unchanged."""
import hashlib, json, os, shutil, subprocess, sys, uuid
from pathlib import Path

repo=Path(__file__).resolve().parents[2]; out=Path(__file__).parent
platform=sys.argv[1]; assert platform in {'windows','linux'}
snapshot=json.loads((out/'final-source-v5.json').read_text())
old=json.loads((out/('integration-source-v1.json' if platform=='windows' else 'linux-source-v1.json')).read_text())
if platform=='windows':
    root=Path(snapshot['root']); base=Path(snapshot['base']); python=sys.executable; engine='F:/EnergyPlusV9-0-1/energyplus.exe'
else:
    os.umask(0o077)
    ctx=json.loads((repo/'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text()); assert os.getuid()==ctx['uid']==65534
    base=Path(ctx['root'])/('designload-final-'+uuid.uuid4().hex); base.mkdir(); root=base/'source'; root.mkdir()
    python=ctx['python']; engine=ctx['engine']
    for item in snapshot['files']:
        raw=(repo/item['path']).read_bytes(); assert hashlib.sha256(raw).hexdigest()==item['sha256'],item['path']
        target=root/item['path']; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
for item in snapshot['files']:
    assert hashlib.sha256((root/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
    if item['path'].startswith(('backend/','frontend/','tests/')):
        assert hashlib.sha256((repo/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
sys.path.insert(0,str(root))
from backend import core
assert core.code_hash()=='811cc91edfdfbed58f78d4b69bb52cbfde20a51b22fdcc68545a2b868d29d6ab'
prior=Path(old['root']); assert not (root/'runs').exists()
references=json.loads((prior/'validation/reference_comparison.json').read_text())
copied=[]
for view in references['results']:
    rid=view['run_id']; assert rid.startswith('run_') and len(rid)==36
    original=prior/'runs'/rid; target=root/'runs'/rid
    shutil.copytree(original,target)
    for path in sorted(original.rglob('*')):
        if path.is_file():
            rel=path.relative_to(original); digest=core.sha(path); assert core.sha(target/rel)==digest
            copied.append({'path':'runs/'+rid+'/'+rel.as_posix(),'sha256':digest})
    core.read_validated(target)
(root/'validation').mkdir(exist_ok=True)
shutil.copyfile(prior/'validation/reference_comparison.json',root/'validation/reference_comparison.json')
record={'platform':platform,'application_commit':snapshot['application_commit'],'root':str(root),'base':str(base),
        'source_files':snapshot['files'],'physics_hash':core.code_hash(),'reference_origin':str(prior),
        'reference_reuse_notice':'Reuse this batch native v1 references unchanged: Agent-only source changes do not alter physics hash. No new reference simulations claimed.',
        'copied_reference_files':copied}
with (out/(platform+'-final-regression-v2.json')).open('x',encoding='utf-8') as handle:json.dump(record,handle,indent=2)
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',ENERGYPLUS_EXE=engine,VRA_DATA_DIR=str(base/'full-final-bootstrap'))
with (out/(platform+'-full-final-v2.log')).open('xb') as log:
    result=subprocess.run([python,'-m','pytest','-q','-rs','-p','no:cacheprovider'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
print(json.dumps({'platform':platform,'exit_code':result.returncode,'root':str(root)}),flush=True)
raise SystemExit(result.returncode)
