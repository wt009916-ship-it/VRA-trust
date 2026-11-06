"""Copy only compact native receipts, leaving large originals/SQL in private roots."""
import hashlib,json,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
platform='windows' if sys.platform=='win32' else 'linux'
snapshot=json.loads((out/(platform+'-source-v2.json')).read_text(encoding='utf-8'))
base=Path(snapshot['base']);root=Path(snapshot['root']);target=out/('native-'+platform+'-v2');target.mkdir(exist_ok=False)
summary=json.loads((base/'weather/weather-reference.json').read_text(encoding='utf-8'))
directories=[Path(item['run_dir']) for key in ('public_climates','synthetic_sky_checks') for item in summary[key]]
annual=json.loads((root/'validation/reference_comparison.json').read_text(encoding='utf-8'))
directories += [root/'runs'/item['run_id'] for item in annual['results']]
records=[]
for rd in directories:
    assert rd.resolve().is_relative_to(base.resolve())
    manifest=json.loads((rd/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['status']=='succeeded'
    for name in ('manifest.json','result.json','weather-quality.json','output/eplusout.err'):
        source=rd/name;raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if name!='manifest.json':assert manifest['artifact_hashes'][name]==digest
        destination=target/rd.name/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
        records.append({'source':str(source),'path':destination.relative_to(repo).as_posix(),'bytes':len(raw),'sha256':digest})
with (target/'index.json').open('x',encoding='utf-8') as stream:json.dump({'platform':platform,'runs':len(directories),'files':records},stream,indent=2)
if platform=='linux':
    old=json.loads((out/'linux-source-v1.json').read_text(encoding='utf-8'));failure=Path(old['base'])/'weather/public-0'
    dest=out/'linux-v1-failed-native';dest.mkdir(exist_ok=False)
    for name in ('manifest.json','result.json','partial-error-diagnostic.txt'):
        source=failure/name
        if source.is_file():(dest/name).write_bytes(source.read_bytes())
print(json.dumps({'platform':platform,'runs':len(directories),'compact_files':len(records)}))
