"""Run the frozen new benchmark without changing its inputs or prior outputs."""
import hashlib,json,os,subprocess,sys
from importlib.metadata import version
from pathlib import Path
out=Path(__file__).parent;repo=out.resolve().parents[1]
plan=json.loads((out/'benchmark-inputs-v1.json').read_text());base=Path(plan['base']);gold=Path(plan['gold'])
assert hashlib.sha256((gold/'truth.json').read_bytes()).hexdigest()==plan['truth_sha256']
assert hashlib.sha256((repo/'scripts/make_drawing_geometry_benchmark.py').read_bytes()).hexdigest()==plan['generator_sha256']
source={str(p.relative_to(repo)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [repo/'backend'/n for n in ['drawings.py','drawing_processing.py','drawing_scale.py','drawing_worker.py','drawing_models.py','parser_runtime.py','parser_worker.py','extensions.py']]+[repo/'scripts/verify_drawing_geometry_reference.py']}
with (out/'benchmark-source-v2.json').open('x',encoding='utf-8') as f:
    json.dump({'files':source,'versions':{p:version(p) for p in ['Pillow','opencv-python-headless','rapidocr','numpy']},'output':str(base/'windows-v2')},f,indent=2)
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',VRA_DATA_DIR=str(base/'bootstrap'))
with (out/'benchmark-windows-v2.log').open('xb') as log:
    result=subprocess.run([sys.executable,'scripts/verify_drawing_geometry_reference.py',str(gold),plan['public'],str(base/'windows-v2')],
                          cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
for name,digest in source.items():assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,name
summary=base/'windows-v2/summary.json'
if summary.exists():
    with (out/'benchmark-windows-v2.json').open('xb') as f:f.write(summary.read_bytes())
print(json.dumps({'exit_code':result.returncode,'output':str(base/'windows-v2')}),flush=True)
raise SystemExit(result.returncode)
