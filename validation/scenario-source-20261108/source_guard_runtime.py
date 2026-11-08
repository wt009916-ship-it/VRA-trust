from pathlib import Path
import os,sys,subprocess,secrets,json,socket,time,uuid,sqlite3
from hashlib import sha256
import httpx
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108');O=Path('C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108')
sys.path[:0]=[str(R),str(R/'tests')]
from backend.private_storage import private_mkdir
from test_slab_collection import slab_pair
fixture=O/'fixture';fixture.mkdir(exist_ok=False);doc,products,source=slab_pair(fixture,shift=1.,tilted=True)
raw=source.read_bytes();runtime=private_mkdir(O/('private-'+uuid.uuid4().hex));port=18779
with socket.socket() as s:s.bind(('127.0.0.1',port))
log=(O/'api.log').open('wb');env={**os.environ,'VRA_DATA_DIR':str(runtime/'api'),'PYTHONUTF8':'1'}
api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=R,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
state=runtime/'state.json';receipt={'port':port,'api_pid':api.pid,'runtime':str(runtime),'state_path':str(state),'source_hash':sha256(raw).hexdigest()}
try:
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,trust_env=False) as c:
        for _ in range(60):
            assert api.poll() is None
            try:
                if c.get('/api/health').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(1)
        else:raise RuntimeError('readiness timeout')
        r=c.post('/api/auth/register',json={'username':'scenario_source_ui','display_name':'来源状态隔离验收','password':secrets.token_urlsafe(32)});assert r.status_code==200;c.headers['X-CSRF-Token']=r.json()['csrf_token']
        r=c.post('/api/projects',json={'name':'方案来源状态验收','data_nature':'engineering_reference','building':{'use':'reference','location':'Synthetic fixture','region':'US-CO','area_m2':12}});assert r.status_code==201
        pid=r.json()['project_id'];base='/api/projects/'+pid
        r=c.post(base+'/files',files={'file':('synthetic-slabs.ifc',raw,'application/octet-stream')});assert r.status_code==201;fid=r.json()['file_id']
        r=c.post(base+'/cad-inspections',json={'file_id':fid});assert r.status_code==201;cid=r.json()['cad_id']
        r=c.post(base+'/ifc-material-collections',json={'cad_id':cid,'product_ids':[p.id() for p in products]});assert r.status_code==201 and r.json()['status']=='measured';collection=r.json()
        r=c.post(base+'/ifc-layer-takeoffs',json={'cad_id':cid,'product_id':products[0].id()});assert r.status_code==201 and r.json()['status']=='measured';takeoff=r.json()
        receipt.update(project_id=pid,cad_id=cid,file_id=fid,materialset_id=collection['materialset_id'],takeoff_id=takeoff['takeoff_id'],product_id=products[0].id())
        (O/'collection.json').write_text(json.dumps(collection,indent=2),encoding='utf-8');(O/'takeoff.json').write_text(json.dumps(takeoff,indent=2),encoding='utf-8')
        state.write_text(json.dumps({'cookies':[{'name':x.name,'value':x.value,'domain':'127.0.0.1','path':'/','expires':-1,'httpOnly':True,'secure':False,'sameSite':'Strict'} for x in c.cookies.jar],'origins':[]}),encoding='utf-8')
        (O/'ready.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({'ready':True,'port':port,'state_path':str(state)}),flush=True)
        with sqlite3.connect(runtime/'api/vra.sqlite3') as db:row=db.execute("SELECT body FROM records WHERE kind='file' AND id=? ORDER BY revision DESC LIMIT 1",(fid,)).fetchone()
        target=(runtime/'api'/json.loads(row[0])['path']).resolve();assert target.is_relative_to((runtime/'api').resolve())
        while True:
            command=input().strip()
            if command=='stop':break
            assert command in {'invalidate','restore','verify'}
            if command=='invalidate':target.write_bytes(b'Damaged isolated test copy')
            if command=='restore':target.write_bytes(raw)
            if command in {'invalidate','restore'}:
                for name,ident in [('ifc-material-collections',collection['materialset_id']),('ifc-layer-takeoffs',takeoff['takeoff_id'])]:
                    actual=c.get(base+'/'+name+'/'+ident).json();assert actual['status']==('stale' if command=='invalidate' else 'measured')
            else:
                result=c.get(base+'/collection-scenarios').json();assert result;receipt['created_scenarios']=len(result)
                (O/'created-scenarios.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(command+' completed',flush=True)
finally:
    if api.poll() is None:api.terminate()
    api.wait(timeout=30);log.close()
    if state.exists():state.unlink()
    receipt.update(stopped=True,private_state_deleted=True,fixture_original_unchanged=sha256(source.read_bytes()).hexdigest()==receipt['source_hash'])
    (O/'runtime-receipt.json').write_text(json.dumps(receipt,indent=2));print('Isolated runtime stopped and session file deleted.',flush=True)
