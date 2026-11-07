"""Freeze an independent reference before invoking actual IFC and scenario APIs."""
import hashlib,json,os,secrets,sys,tempfile
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path
out=Path(__file__).resolve().parent;root=out.parents[2]
candidate=Path(json.loads((out/'candidate.json').read_text())['candidate'])
sys.path.insert(0,str(candidate));sys.path.insert(0,str(candidate/'tests'))
os.environ['VRA_DATA_DIR']=tempfile.mkdtemp(prefix='vra-scenario-import-')
from fastapi.testclient import TestClient
from backend.api import create_app
from test_material_scenarios import payload
from test_api import create_project
from test_cad import upload
source=Path(sys.argv[1]);raw=source.read_bytes()
gold=json.loads((out.parent/'public-layer-gold-v1.json').read_text())
assert hashlib.sha256(raw).hexdigest()==gold['source_sha256']
placeholder={'takeoff_id':'takeoff_'+'a'*32,'result':{'layers':gold['layers']}}
body=payload(placeholder)
# Explicit artificial sensitivity inputs; never claim real market/EPD facts.
for alt in body['alternatives']:
 for row in alt['layers']:
  row['solid_fraction']=0.15 if row['layer_id']==4200 else 1.0
  row['fraction_source']='Declared sensitivity assumption, not verified solid fraction of the public IFC'
expected=[]
for alt in body['alternatives']:
 cost=D(0);carbon=D(0);rows=[]
 for layer,row in zip(gold['layers'],alt['layers']):
  net=D(layer['expected_volume_m3'])*D(str(row['solid_fraction']))
  purchase=net*(1+D(str(row['waste_ratio'])))
  mass=purchase*D(str(row['density_kg_m3']))
  price=(mass/D(1000)*D(str(row['quote']['unit_price']))).quantize(D('.01'),rounding=ROUND_HALF_UP)
  emissions=mass*D(str(row['factor']['value']))
  cost+=price;carbon+=emissions
  rows.append({'layer_id':row['layer_id'],'net_m3':str(net),'purchase_m3':str(purchase),'cost':str(price),'kgco2e':str(emissions)})
 expected.append({'name':alt['name'],'cost':str(cost),'kgco2e':str(carbon),'rows':rows})
frozen={'source_sha256':gold['source_sha256'],'input':body,'expected':expected,'carbon_abs_tolerance':'1e-8',
 'price_and_factors':'artificial sensitivity inputs, not real quotes or EPDs','geometry_gold':'independent raw STEP box intersections'}
with (out/'public-frozen.json').open('x',encoding='utf-8') as f:json.dump(frozen,f,ensure_ascii=False,indent=2)
app=create_app(Path(tempfile.mkdtemp(prefix='vra-public-scenarios-')),start_worker=False)
with TestClient(app) as client:
 auth=client.post('/api/auth/register',json={'username':'public_material_scenarios','display_name':'Isolated reference','password':secrets.token_urlsafe(32)}).json()
 client.headers['X-CSRF-Token']=auth['csrf_token']
 pid=create_project(client)['project_id'];fid=upload(client,pid,source.name,raw)
 response=client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid});assert response.status_code==201,response.text[:200]
 cad=response.json()
 response=client.post(f'/api/projects/{pid}/ifc-layer-takeoffs',json={'cad_id':cad['cad_id'],'product_id':5903});assert response.status_code==201,response.text[:200]
 takeoff=response.json();assert takeoff['status']=='measured'
 body['takeoff_id']=takeoff['takeoff_id']
 response=client.post(f'/api/projects/{pid}/material-scenarios',json=body);assert response.status_code==201,response.text[:500]
 scenario=response.json();assert scenario['status']=='calculated'
 for actual,want in zip(scenario['result']['alternatives'],expected):
  assert actual['cost']['material_total']==want['cost']
  assert abs(D(str(actual['carbon']['boundary_total_kgco2e']))-D(want['kgco2e']))<D('1e-8')
  for row,wrow in zip(actual['derivations'],want['rows']):assert abs(D(row['net_material_volume_m3'])-D(wrow['net_m3']))<D('1e-9')
 url=f"/api/projects/{pid}/material-scenarios/{scenario['scenario_id']}"
 report=client.get(url+'/report.html');assert report.status_code==200
 assert all(e['cost'] in report.text for e in expected)
 assert client.get(f'/api/projects/{pid}/files/{fid}').content==raw
 (out/'public-scenario.json').write_text(json.dumps(scenario,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/'public-report.html').write_text(report.text,encoding='utf-8')
 (out/'public-result.json').write_text(json.dumps({'passed':True,'source_sha256':gold['source_sha256'],'expected':expected,
  'actual':[{'name':a['name'],'cost':a['cost']['material_total'],'kgco2e':a['carbon']['boundary_total_kgco2e']} for a in scenario['result']['alternatives']],
  'original_download_identical':True,'full_lifecycle_validated':False,'functional_equivalence_validated':False},indent=2),encoding='utf-8')
 print(json.dumps({'passed':True,'actual':json.loads((out/'public-result.json').read_text())['actual']}))
