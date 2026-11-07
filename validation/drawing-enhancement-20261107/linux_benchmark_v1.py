import hashlib,json,os,subprocess,uuid
from pathlib import Path
os.umask(0o077);assert os.getuid()==65534
repo=Path(__file__).resolve().parents[2];out=Path(__file__).parent
ctx=json.loads((repo/'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
snapshot=json.loads((out/'candidate-source-v1.json').read_text());base=Path(ctx['root'])/('drawing-geometry-'+uuid.uuid4().hex);base.mkdir();root=base/'source';root.mkdir()
for row in snapshot['files']:
    raw=(repo/row['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row['sha256']:
        assert row['path'] in snapshot['newline_normalizations'];raw=raw.replace(b'\r\n',b'\n')
    assert hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
    target=root/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
public=json.loads((out/'public-source-v1.json').read_text());source=Path('/mnt/'+public['path'][0].lower()+public['path'][2:].replace('\\','/'))
data=source.read_bytes();assert hashlib.sha256(data).hexdigest()==public['sha256']
target=base/'public.jpg';target.write_bytes(data)
with (out/'linux-source-v1.json').open('x') as f:json.dump({**snapshot,'base':str(base),'root':str(root),'public':str(target)},f,indent=2)
env=dict(os.environ,VRA_DATA_DIR=str(base/'bootstrap'),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',ENERGYPLUS_EXE=ctx['engine'])
for label,args in [('linux-benchmark-v1',['scripts/verify_drawing_geometry_reference.py',str(root/'fixtures/drawing_geometry'),str(target),str(base/'benchmark-v1')]),
                   ('linux-related-v1',['-m','pytest','-q','-p','no:cacheprovider','tests/test_drawing_geometry.py','tests/test_drawings.py','tests/test_backup.py'])]:
    with (out/(label+'.log')).open('xb') as log:
        result=subprocess.run([ctx['python'],*args],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
    print(json.dumps({'stage':label,'exit_code':result.returncode,'root':str(root)}),flush=True)
    if label=='linux-benchmark-v1' and (base/'benchmark-v1/summary.json').is_file():
        with (out/'linux-benchmark-v1.json').open('xb') as f:f.write((base/'benchmark-v1/summary.json').read_bytes())
    if result.returncode:raise SystemExit(result.returncode)
