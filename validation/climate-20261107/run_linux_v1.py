"""New non-root Linux native references and full regression; no old manifests copied."""
import hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
os.umask(0o077)
repo=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
ctx=json.loads((repo/'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
assert os.getuid()==ctx['uid']==65534
base=Path(ctx['root'])/('weather-v1-'+uuid.uuid4().hex);base.mkdir()
root=base/'source';root.mkdir()
win=json.loads((out/'windows-source-v1.json').read_text());records=[]
frontend_changes=[]
for record in win['files']:
    name=record['path'];raw=(repo/name).read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest!=record['sha256']:
        assert name.startswith('frontend/'),name
        frontend_changes.append(name)
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    records.append({'path':name,'bytes':len(raw),'sha256':digest})
with (out/'linux-source-v1.json').open('x',encoding='utf-8') as stream:
    json.dump({'root':str(root),'base':str(base),'uid':os.getuid(),'files':records,
               'frontend_changes_since_windows_freeze':frontend_changes,'reused_reference_calls':0},stream,indent=2)
env=dict(os.environ,ENERGYPLUS_EXE=ctx['engine'],VRA_DATA_DIR=str(base/'data'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
for name,command in [
    ('linux-weather-v1',[ctx['python'],'scripts/verify_weather_reference.py',str(base/'weather'),'/mnt/f/EnergyPlusV9-0-1/WeatherData']),
    ('linux-yearly-v1',[ctx['python'],'scripts/run_reference.py']),
    ('linux-full-v1',[ctx['python'],'-m','pytest','-q','-rs']),
]:
    with (out/(name+'.log')).open('xb') as log:
        process=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2100)
    print(json.dumps({'stage':name,'exit_code':process.returncode,'root':str(root)}),flush=True)
    if process.returncode:raise SystemExit(process.returncode)
summary=json.loads((base/'weather/weather-reference.json').read_text())
with (out/'linux-weather-v1.json').open('x',encoding='utf-8') as stream:json.dump(summary,stream,indent=2)
