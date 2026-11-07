"""Copy only public/synthetic compact evidence; exclude SQL, account DB, credentials and archives."""
import hashlib,json,os,sys
from pathlib import Path
out=Path(__file__).parent;platform=sys.argv[1]
assert platform in {'windows','linux'}
if platform=='windows':
 assert os.name=='nt'
 analytic=Path(json.loads((out/'windows-analytic-location-v1.json').read_text())['root'])
 base=Path(json.loads((out/'integration-source-v1.json').read_text())['base'])
else:
 assert os.getuid()==65534
 base=Path(json.loads((out/'linux-source-v1.json').read_text())['base']);analytic=base/'analytic'
destination=out/('compact-native-'+platform+'-v1');destination.mkdir()
records=[]
def copy(source,relative):
 raw=source.read_bytes();assert len(raw)<1024*1024,'Unexpected large evidence file'
 target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as stream:stream.write(raw)
 records.append({'path':target.relative_to(out).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
summary=json.loads((analytic/'summary.json').read_text())
assert summary['new_energyplus_simulations']==7 and all(r['status']=='passed' for r in summary['records'])
copy(analytic/'predeclared.json','analytic/predeclared.json')
for record in summary['records']:
 name=record['spec']['id'];root=analytic/name
 assert name in {'baseline','insulated','temperature','thermal_mass','zone_multiplier','user_sizing','zone_group'}
 assert json.loads((root/'record.json').read_text())==record
 for file in ('input.idf','record.json','output/eplusout.err'):
  copy(root/file,'analytic/'+name+'/'+Path(file).name)
native=base/'native';api=json.loads((native/'summary.json').read_text())
assert api['binding_tamper_rejected'] and api['new_energyplus_simulations']==1
rid=api['run_id'];run=native/'api/runs'/rid
for file in ('actual-report.json','clean-result.json','clean-manifest.json','binding-rejected.json'):
 copy(native/file,'api/'+file)
for file in ('result.json','manifest.json','output/eplusout.err','weather-quality.json'):
 copy(run/file,'api/post-tamper-'+Path(file).name)
record={'platform':platform,'copied_files':records,'new_analytic_calls':7,'new_authenticated_api_calls':1,
        'raw_sql_not_published':True,'account_database_not_published':True,
        'api_sequence':'clean report/result/manifest copied before deliberate binding corruption; post-tamper files and failed current view retained'}
with (out/('compact-native-'+platform+'-v1.json')).open('x') as f:json.dump(record,f,indent=2)
print(json.dumps({'platform':platform,'files':len(records),'bytes':sum(r['bytes'] for r in records)}))
