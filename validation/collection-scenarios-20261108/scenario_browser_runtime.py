"""Private localhost acceptance server; no production account/data access."""
from pathlib import Path
import os,sys,subprocess,secrets,json,socket,time,uuid
from hashlib import sha256
import httpx
REPO=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-collection-scenarios-public-20261108')
sys.path.insert(0,str(REPO))
from backend.private_storage import private_mkdir
runtime=private_mkdir(OUT/('browser-private-'+uuid.uuid4().hex));port=18779
with socket.socket() as s:s.bind(('127.0.0.1',port))
env={**os.environ,'VRA_DATA_DIR':str(runtime/'api'),'PYTHONUTF8':'1'}
log=(OUT/'browser-api.log').open('wb')
api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=REPO,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
state_path=runtime/'state.json';receipt={'port':port,'api_pid':api.pid,'runtime':str(runtime),'state_path':str(state_path)}
source=Path('D:/稀土agent-稀土制暖全流程/outputs/vra-m2-intake-20261108/Duplex_A_20110907.ifc')
raw=source.read_bytes();gold=json.loads((OUT/'frozen-gold.json').read_text())
assert sha256(raw).hexdigest()==gold['source_sha256']
try:
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,trust_env=False) as client:
        for _ in range(60):
            assert api.poll() is None
            try:
                if client.get('/api/health').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(1)
        else:raise RuntimeError('API readiness timeout')
        r=client.post('/api/auth/register',json={'username':'collection_scenarios_ui','display_name':'隔离多墙验收','password':secrets.token_urlsafe(32)})
        assert r.status_code==200;client.headers['X-CSRF-Token']=r.json()['csrf_token']
        r=client.post('/api/projects',json={'name':'公开IFC多墙计量验收','data_nature':'engineering_reference','building':{'use':'reference','location':'Public reference','region':'US-CO','area_m2':927.2}})
        assert r.status_code==201;pid=r.json()['project_id'];base=f'/api/projects/{pid}'
        r=client.post(base+'/files',files={'file':(source.name,raw,'application/octet-stream')});assert r.status_code==201
        uploaded=r.json();fid=uploaded['file_id']
        r=client.post(base+'/cad-inspections',json={'file_id':fid});assert r.status_code==201
        receipt.update(project_id=pid,cad_id=r.json()['cad_id'],file_id=fid)
        r=client.post(base+'/ifc-material-collections',json={'cad_id':receipt['cad_id'],'product_ids':gold['selected_ids']});assert r.status_code==201,r.text
        collection=r.json();assert collection['status']=='measured'
        receipt['materialset_id']=collection['materialset_id']
        r=client.post(base+'/evidence',json={'type':'assumption','name':'合成验收材料参数与因子v2','source_locator':'Frozen Decimal QA input, SHA256 '+sha256((OUT/'frozen-gold.json').read_bytes()).hexdigest(),'value':'Declared arithmetic assumptions only','authority':'QA synthetic reference','permission':'Self-authored arithmetic inputs','acquisition_method':'Explicit synthetic assumptions','responsible_person':'QA','status':'ASSUMED'})
        assert r.status_code==201,r.text
        receipt['evidence_id']=r.json()['evidence_id']
        (OUT/'seeded-collection.json').write_text(json.dumps(collection,ensure_ascii=False,indent=2),encoding='utf-8')
        state={'cookies':[{'name':c.name,'value':c.value,'domain':'127.0.0.1','path':'/','expires':-1,'httpOnly':True,'secure':False,'sameSite':'Strict'} for c in client.cookies.jar],'origins':[]}
        state_path.write_text(json.dumps(state),encoding='utf-8')
        (OUT/'browser-ready.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps({'ready':True,'port':port,'api_pid':api.pid}),flush=True)
        while True:
            command=input().strip()
            if command=='stop':break
            assert command in {'verify','negative','revoke'}
            rows=client.get(base+'/collection-scenarios').json();assert rows
            records=[client.get(base+'/collection-scenarios/'+row['collectionscenario_id']).json() for row in rows]
            record=next(r for r in records if r['input']['alternatives'][0]['name']=='参考方案A')
            path=base+'/collection-scenarios/'+record['collectionscenario_id']
            if command=='verify':
                from decimal import Decimal as D
                assert record['status']=='calculated',record['status']
                assert record['input']['materialset_id']==receipt['materialset_id']
                checks=[]
                for a,expected in zip(record['result']['alternatives'],gold['expected']):
                    assert D(a['cost']['material_total'])==D(expected['cost'])
                    assert abs(D(str(a['carbon']['boundary_total_kgco2e']))-D(expected['carbon_total']))<=D('0.00001')
                    assert abs(D(a['transport'][0]['quantity_tkm'])-D(expected['transport_tkm']))<=D('0.00001')
                    for key,value in expected['stages'].items():
                        assert abs(D(str(a['carbon']['stages'][key]['kgco2e']))-D(value))<=D('0.00001')
                    for actual,want in zip(a['derivations'],expected['derivations']):
                        assert actual['source_material_id']==want['source_material_id']
                        assert abs(D(actual['net_material_volume_m3'])-D(want['net_m3']))<=D('1e-7')
                        assert abs(D(actual['purchase_volume_m3'])-D(want['purchase_m3']))<=D('1e-7')
                    checks.append({'name':a['name'],'cost':a['cost']['material_total'],'carbon_total':a['carbon']['boundary_total_kgco2e']})
                assert D(record['result']['comparison']['cost_difference'])==D(gold['comparison']['cost_difference'])
                assert record['result']['issued_credits_t'] is None and record['result']['functional_equivalence']=='NOT_ASSESSED'
                (OUT/'browser-created-scenario.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                (OUT/'browser-report.html').write_text(client.get(path+'/report.html').text,encoding='utf-8')
                receipt.update(browser_created_and_independently_checked=True,numerical_checks=checks)
            elif command=='negative':
                import copy
                body=copy.deepcopy(record['input']);body['alternatives'][0]['materials'][0]['solid_fraction']=None
                body['alternatives'][0]['name']='Missing fraction reference'
                r=client.post(base+'/collection-scenarios',json=body);assert r.status_code==201,r.text
                missing=r.json();assert missing['status']=='incomplete' and missing['result']['comparison'] is None
                results={'missing_fraction':'incomplete, comparison null'}
                for kind in ['forged_volume','factor_version_conflict','negative_density']:
                    body=copy.deepcopy(record['input'])
                    if kind=='forged_volume':body['alternatives'][0]['materials'][0]['union_envelope_m3']=999
                    elif kind=='factor_version_conflict':body['alternatives'][1]['materials'][0]['factor']['factor_id']=body['alternatives'][0]['materials'][0]['factor']['factor_id']
                    else:body['alternatives'][0]['materials'][0]['density_kg_m3']=-1.
                    r=client.post(base+'/collection-scenarios',json=body);assert r.status_code==422,r.text
                    results[kind]=r.status_code
                (OUT/'adversarial-api-results.json').write_text(json.dumps(results,indent=2))
                receipt['adversarial_api']=results
            else:
                r=client.patch(base+'/evidence/'+receipt['evidence_id'],json={'expected_revision':1,'review_state':'rejected','responsible_person':'QA','review_note':'Isolated evidence withdrawal acceptance'})
                assert r.status_code==200,r.text
                current=client.get(path).json();assert current['status']=='stale' and current['result'] is None
                html=client.get(path+'/report.html').text
                assert '2613.61' not in html and '16332.95' not in html
                (OUT/'withdrawn-scenario.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
                (OUT/'withdrawn-report.html').write_text(html,encoding='utf-8')
                receipt['evidence_withdrawal_verified']=True
            print(command+' completed',flush=True)
finally:
    if api.poll() is None:api.terminate()
    api.wait(timeout=30);log.close()
    if state_path.exists():state_path.unlink()
    receipt.update(stopped=True,private_state_deleted=True,public_original_unchanged=sha256(source.read_bytes()).hexdigest()==gold['source_sha256'])
    (OUT/'browser-runtime-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('Isolated API stopped; private browser state deleted.',flush=True)
