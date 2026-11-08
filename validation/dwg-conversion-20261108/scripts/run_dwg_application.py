from pathlib import Path
import sys,os,subprocess,time,json,secrets,socket,signal,hashlib
import httpx
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-dwg-conversion-20261108')
out=Path('C:/Users/18483/AppData/Local/Temp/vra-dwg-application-20261108-v3');out.mkdir(exist_ok=False)
reference=Path('C:/Users/18483/AppData/Local/Temp/vra-libredwg-014-reference-20261108')
runtime=Path('C:/Users/18483/AppData/Local/Temp/vra-dwg-checks-20261108/dwg-runtime')
sys.path.insert(0,str(repo))
from backend.private_storage import private_mkdir
private_mkdir(out/'data')
port=18779
with socket.socket() as check:check.bind(('127.0.0.1',port))
cases=[('line',reference/'decode-reference/2000-Line/input.dwg',True),('text',reference/'decode-reference/2018-Text/input.dwg',True),('mixed',reference/'strict-gate/example_2004/input.dwg',True),('r14',reference/'strict-gate/example_r14/input.dwg',False)]
(out/'frozen.json').write_text(json.dumps({'cases':[{'id':n,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'expected_pass':ok} for n,p,ok in cases],
 'assertions':['native conversion and strict parser required','original byte preservation','warnings retained and partial coverage labelled','DXF download equals saved digest','corrupt input rejected without record','cross-user access blocked','source/derivative/runtime tamper withdraws results/download','no automatic repair'],
 'numeric_tolerance':'original frozen reference rule: half last printed decimal place plus 1e-9; 17.4075 printed inches gives 0.00005 inch tolerance, propagated to meters',
 'scope':'actual local HTTP/application integration, not building survey or complete DWG information preservation'},indent=2))
env=dict(os.environ);env.update(VRA_DATA_DIR=str(out/'data'),VRA_DWG_RUNTIME=str(runtime),PYTHONDONTWRITEBYTECODE='1')
log=(out/'server.log').open('wb')
proc=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
checks=[]
def verify(value,name):
    checks.append({'name':name,'passed':bool(value)});(out/'checks.json').write_text(json.dumps(checks,indent=2));assert value,name
try:
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,limits=httpx.Limits(keepalive_expiry=4)) as c:
        for _ in range(80):
            if proc.poll() is not None:raise RuntimeError('API exited before health')
            try:
                if c.get('/api/health').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.25)
        else:raise RuntimeError('API health timeout')
        auth=c.post('/api/auth/register',json={'username':'dwg_acceptance','display_name':'Isolated DWG acceptance','password':secrets.token_urlsafe(30)});verify(auth.status_code==200,'register isolated user')
        c.headers['X-CSRF-Token']=auth.json()['csrf_token']
        p=c.post('/api/projects',json={'name':'Public DWG acceptance','building':{'use':'office','location':'Reference only','region':'Reference','area_m2':100.0}});verify(p.status_code==201,'create isolated project');pid=p.json()['project_id'];base='/api/projects/'+pid
        verify(c.get(base+'/dwg-capability').json()['available'],'verified converter advertised')
        saved=[]
        for name,path,passed in cases:
            raw=path.read_bytes();upload=c.post(base+'/files',files={'file':(name+'.dwg',raw)});verify(upload.status_code==201,name+' upload')
            fid=upload.json()['file_id'];r=c.post(base+'/cad-inspections',json={'file_id':fid})
            (out/(name+'-response.json')).write_text(json.dumps({'status':r.status_code,'body':r.json()},ensure_ascii=False,indent=2),encoding='utf-8')
            verify(r.status_code==(201 if passed else 409),name+' strict result matches frozen gate')
            verify(c.get(base+'/files/'+fid).content==raw,name+' original preserved')
            if passed:
                obj=r.json();saved.append(obj)
                verify(obj['status']=='parsed' and obj['conversion']['coverage']=='partial_not_lossless',name+' explicit partial conversion')
                verify(bool(obj['conversion']['notifications']),name+' converter notifications retained')
                verify(obj['conversion']['resource_limits']['filesystem_network_sandbox'] and obj['result']['resource_limits']['execution_receipt']['filesystem_network_sandbox'],name+' both stages isolated')
                d=c.get(base+'/cad-inspections/'+obj['cad_id']+'/converted.dxf');verify(d.status_code==200 and hashlib.sha256(d.content).hexdigest()==obj['derivative']['sha256'],name+' derived download verified')
                (out/(name+'-download.dxf')).write_bytes(d.content)
                if name=='line':
                    line=next(x for x in obj['result']['objects'] if x['type']=='LINE');verify(abs(line['length_m']-17.4075*.0254)<=.00005*.0254+1e-9,'independent line length and declared inches conversion')
                elif name=='text':
                    verify(any(x.get('text') for x in obj['result']['objects']),'original text extracted')
        upload=c.post(base+'/files',files={'file':('corrupt.dwg',b'AC1015'+b'\0'*60)}).json()
        fail=c.post(base+'/cad-inspections',json={'file_id':upload['file_id']});verify(fail.status_code==409,'corrupt DWG rejected')
        verify(len(c.get(base+'/cad-inspections').json())==3,'no success records for two failed conversions')
        obj=saved[0];record=base+'/cad-inspections/'+obj['cad_id']
        for kind,target in [('source',out/'data'/obj['source']['path']),('derivative',out/'data'/obj['derivative']['path']),('runtime',runtime/'ACadSharp.dll')]:
            original=target.read_bytes()
            try:
                target.write_bytes(original+b'changed-for-isolated-acceptance')
                v=c.get(record).json();verify(v['status']=='stale' and v['result'] is None,kind+' change withdraws quantities')
                verify(c.get(record+'/converted.dxf').status_code==409,kind+' change withdraws derived download')
                (out/(kind+'-stale.json')).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
            finally:target.write_bytes(original)
            verify(c.get(record).json()['status']=='parsed',kind+' exact-byte restoration revalidates')
        token=c.headers.pop('X-CSRF-Token');verify(c.post(base+'/cad-inspections',json={'file_id':saved[0]['source']['file_id']}).status_code==403,'CSRF mandatory');c.headers['X-CSRF-Token']=token
        with httpx.Client(base_url=c.base_url,timeout=15) as other:
            verify(other.get(record+'/converted.dxf').status_code==401,'anonymous download blocked')
            a=other.post('/api/auth/register',json={'username':'dwg_other_user','display_name':'Other isolated user','password':secrets.token_urlsafe(30)})
            verify(a.status_code==200,'second isolated user')
            verify(other.get(record+'/converted.dxf').status_code==403,'other user download blocked')
        (out/'project-summary.json').write_text(json.dumps({'project_id':pid,'cad_ids':[x['cad_id'] for x in saved],'runtime_manifest_sha256':hashlib.sha256((runtime/'manifest.json').read_bytes()).hexdigest()},indent=2))
finally:
    if proc.poll() is None:
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        try:proc.wait(timeout=20)
        except subprocess.TimeoutExpired:print('Owned test API has not exited: '+str(proc.pid),flush=True)
    log.close();(out/'service-exit.json').write_text(json.dumps({'pid':proc.pid,'exit_code':proc.poll(),'stopped':proc.poll() is not None}))
print(json.dumps({'checks':len(checks),'passed':sum(x['passed'] for x in checks),'service_stopped':proc.poll() is not None}),flush=True)
