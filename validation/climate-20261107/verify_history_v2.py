import json,os,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
sys.path.insert(0,str(repo));os.environ['ENERGYPLUS_EXE']='F:/EnergyPlusV9-0-1/energyplus.exe'
from backend import core
old=json.loads((repo/'validation/ifc-topology-20261107/release-final/windows-source.json').read_text())
root=Path(old['root']);summary=core.read_json(root/'validation/reference_comparison.json');records=[]
for result in summary['results']:
    rd=root/'runs'/result['run_id']
    before={p.name:core.sha(p) for p in (rd/'manifest.json',rd/'result.json')}
    current,manifest,plan=core.read_validated(rd)
    assert current['status']=='stale' and current['metrics'] is None and current['carbon'] is None
    assert 'code' in plan['changed']
    after={p.name:core.sha(p) for p in (rd/'manifest.json',rd/'result.json')}
    assert before==after
    records.append({'run_id':rd.name,'before':before,'after':after,'invalidation':plan})
with (out/'history-invalidation-v2.json').open('x',encoding='utf-8') as stream:
    json.dump({'old_runs':records,'old_manifest_rewrites':0,'new_code_hash':core.code_hash()},stream,indent=2)
print(json.dumps({'old_runs_stale':len(records),'old_manifest_rewrites':0}))
