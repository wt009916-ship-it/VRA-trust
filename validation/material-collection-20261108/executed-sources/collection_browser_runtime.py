"""Private localhost acceptance server; no production account/data access."""
from pathlib import Path
import os,sys,subprocess,secrets,json,socket,time,uuid
from hashlib import sha256
import httpx
REPO=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-material-collection-public-20261108')
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
        r=client.post('/api/auth/register',json={'username':'material_collection_ui','display_name':'隔离多墙验收','password':secrets.token_urlsafe(32)})
        assert r.status_code==200;client.headers['X-CSRF-Token']=r.json()['csrf_token']
        r=client.post('/api/projects',json={'name':'公开IFC多墙计量验收','data_nature':'engineering_reference','building':{'use':'reference','location':'Public reference','region':'US-CO','area_m2':927.2}})
        assert r.status_code==201;pid=r.json()['project_id'];base=f'/api/projects/{pid}'
        r=client.post(base+'/files',files={'file':(source.name,raw,'application/octet-stream')});assert r.status_code==201
        uploaded=r.json();fid=uploaded['file_id']
        r=client.post(base+'/cad-inspections',json={'file_id':fid});assert r.status_code==201
        receipt.update(project_id=pid,cad_id=r.json()['cad_id'],file_id=fid)
        state={'cookies':[{'name':c.name,'value':c.value,'domain':'127.0.0.1','path':'/','expires':-1,'httpOnly':True,'secure':False,'sameSite':'Strict'} for c in client.cookies.jar],'origins':[]}
        state_path.write_text(json.dumps(state),encoding='utf-8')
        (OUT/'browser-ready.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps({'ready':True,'port':port,'api_pid':api.pid}),flush=True)
        while True:
            command=input().strip()
            if command=='stop':break
            assert command in {'verify','invalidate'}
            records=client.get(base+'/ifc-material-collections').json();assert records
            record=next(r for r in records if r['product_ids']==gold['selected_ids'])
            if command=='verify':
                from decimal import Decimal as D
                expected=gold['cases'][-1]
                assert record['status']=='measured'
                assert abs(D(str(record['result']['union_envelope_m3']))-D(expected['union_envelope_m3']))<=D(gold['absolute_tolerance_m3'])
                (OUT/'browser-created-record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                html=client.get(base+'/ifc-material-collections/'+record['materialset_id']+'/report.html')
                assert html.status_code==200
                (OUT/'browser-report.html').write_text(html.text,encoding='utf-8')
                receipt['browser_created_and_independently_checked']=True
            else:
                # Alter only the newly created isolated uploaded copy.
                import sqlite3
                with sqlite3.connect(runtime/'api/vra.sqlite3') as con:
                    row=con.execute("SELECT body FROM records WHERE kind='file' AND id=? ORDER BY revision DESC LIMIT 1",(fid,)).fetchone()
                target=(runtime/'api'/json.loads(row[0])['path']).resolve()
                assert target.is_relative_to((runtime/'api').resolve()) and target.read_bytes()==raw
                target.write_bytes(b'Intentionally corrupted isolated acceptance copy')
                r=client.get(base+'/ifc-material-collections/'+record['materialset_id']).json()
                assert r['status']=='stale' and r['result'] is None
                receipt['isolated_source_invalidation_verified']=True
            print(command+' completed',flush=True)
finally:
    if api.poll() is None:api.terminate()
    api.wait(timeout=30);log.close()
    if state_path.exists():state_path.unlink()
    receipt.update(stopped=True,private_state_deleted=True,public_original_unchanged=sha256(source.read_bytes()).hexdigest()==gold['source_sha256'])
    (OUT/'browser-runtime-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('Isolated API stopped; private browser state deleted.',flush=True)
