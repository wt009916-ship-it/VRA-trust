"""Loopback service acceptance with fixed independent inputs; no browser."""
import copy,csv,gzip,hashlib,io,json,os,secrets,socket,subprocess,sys,time
from fractions import Fraction as F
from pathlib import Path
import httpx

ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
BASE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def boundary(mode='adiabatic',temperature=None,resistance=None):return {'mode':mode,'temperature_c':temperature,'resistance_m2k_w':resistance,'basis':'Independent reference boundary'}
def region(name,x0,x1,y0,y1,k):return {'name':name,'x0':x0,'x1':x1,'y0':y0,'y1':y1,'conductivity':k,'conductivity_unit':'W/(m K)','source':'Independent synthetic material value; not measured'}
def freeze():
    public=ROOT/'validation/thermal-bridge-20261114/composite-reference-frozen.json'
    analytic=ROOT/'validation/thermal-bridge-20261114/analytical-reference-frozen.json'
    ref=json.loads(public.read_text(encoding='utf-8'));column=json.loads(analytic.read_text(encoding='utf-8'))['column_temperature']
    cases=[{'id':f'P{i+1:02}','input':{**ref['input'],'cell_size':step,'mesh_strategy':'graded_interface_aligned'},'expected':ref['expected'],'status':'calculated'} for i,step in enumerate([4.,2.])]
    for i,k in enumerate([.035,.07]):
        q=F(27)*F('1.2')/(F('.14')+F('.08')/F('.3')+F('.07')/F(str(k))+F('.04'))
        cases.append({'id':f'H{i+1:02}','expected':{'heat_w_per_m':float(q),'exact_heat_fraction':str(q),'absolute_heat_tolerance_w_per_m':1e-7},'status':'calculated','input':{
            'name':'Independent layered strip '+str(i),'width':.15,'height':1.2,'length_unit':'m','cell_size':.04,'mesh_strategy':'graded_interface_aligned',
            'geometry_source':'Synthetic two-layer rectangle','application':'Independent series resistance cross-check, not building data',
            'regions':[region('Dense',0.,.08,0.,1.2,.3),region('Light',.08,.15,0.,1.2,k)],
            'boundaries':{'left':boundary('film',22.,.14),'right':boundary('film',-5.,.04),'bottom':boundary(),'top':boundary()},'probes':[]}})
    case=copy.deepcopy(cases[2]['input']);case.update(name='Analytic two-dimensional column',width=1.,height=2.,cell_size=.02,
        regions=[region('Uniform',0.,1.,0.,2.,1.)],probes=[{'name':str(i),'x':p['x_m'],'y':p['y_m']} for i,p in enumerate(column['points'])],
        boundaries={'left':boundary('fixed_temperature',0.),'right':boundary(),'bottom':boundary('fixed_temperature',0.),'top':boundary('fixed_temperature',20.)})
    cases.append({'id':'A01','input':case,'expected':column,'status':'needs_refinement'})
    frozen={'script_sha256':sha(__file__),'source_sha256':{p.name:sha(p) for p in (public,analytic)},'cases':cases,
            'original_gates':{'two_grid_temperature_k':.1,'edge_heat_relative':.01,'max_cells':160000,'seconds':25,'iterations':6000},
            'scope':'Declared reference cases; no certified compliance or real-building validation; not independent held-out testing'}
    assert not (BASE/'live-frozen.json').exists();save(BASE/'live-frozen.json',frozen)
    return frozen
def serve():
    import uvicorn
    from backend.api import app
    uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[2]),log_level='warning')
def run():
    frozen=freeze();out=BASE/'live-first';out.mkdir(exist_ok=False);runtime=BASE/'private-live-runtime';runtime.mkdir(exist_ok=False)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    hashes={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')}
    source=out/'runtime-source';source.mkdir()
    for name in ['thermal_bridge.py','thermal_bridge_solver.py','calculation_provenance.py']:(source/name).write_bytes((ROOT/'backend'/name).read_bytes())
    receipt={'completed':False,'browser':False,'original_data_touched':False,'reference_frozen_sha256':sha(BASE/'live-frozen.json'),'product_sha256':hashes,'cases':[],'checks':[]}
    process=None;log=(out/'application.log').open('xb')
    def check(name,ok):receipt['checks'].append({'name':name,'passed':bool(ok)});save(out/'receipt.json',receipt);assert ok,name
    try:
        process=subprocess.Popen([sys.executable,'-B','-X','utf8',str(Path(__file__).resolve()),'serve',str(port)],cwd=ROOT,
            env={**os.environ,'VRA_DATA_DIR':str(runtime),'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=log,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=45) as c:
            for _ in range(200):
                assert process.poll() is None
                try:
                    if c.get('/api/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            else:raise TimeoutError('Local application startup')
            response=c.post('/api/auth/register',json={'username':'grading_isolated','display_name':'隔离二维导热验收','password':secrets.token_urlsafe(32)})
            check('isolated_registration_200',response.status_code==200);c.headers['X-CSRF-Token']=response.json()['csrf_token']
            def req(method,path,body=None):
                r=c.request(method,path,json=body);r.raise_for_status();return r.json()
            project=req('POST','/api/projects',{'name':'Isolated graded heat references','building':{'use':'reference','location':'Synthetic','region':'TEST','area_m2':100.}})
            base='/api/projects/'+project['project_id'];path=base+'/thermal-bridges'
            ev=req('POST',base+'/evidence',{'type':'manual_input','name':'Declared public/synthetic thermal reference','source_locator':'Frozen input references','authority':'Independent public benchmark and rational resistance equations','permission':'Public numerical references and synthetic tests','acquisition_method':'Reference transcription','responsible_person':'Test harness','status':'ASSUMED'})
            records={}
            for case in frozen['cases']:
                body={**case['input'],'evidence_ids':[ev['evidence_id']]};start=time.monotonic();r=c.post(path,json=body)
                check(case['id']+'_created_201',r.status_code==201);record=r.json();duration=time.monotonic()-start;result=record['result'];records[case['id']]=record
                (out/(case['id']+'.json.gz')).write_bytes(gzip.compress(json.dumps(record,ensure_ascii=False,separators=(',',':')).encode('utf-8'),mtime=0))
                expected=case['expected'];errors=[]
                if case['id'].startswith('P'):
                    errors=[abs(p['temperature_c']-expected['temperature_c'][p['name']]) for p in result['probes']]
                    check(case['id']+'_published_temperatures',max(errors)<=expected['absolute_temperature_tolerance_k'])
                elif case['id']=='A01':
                    errors=[abs(p['temperature_c']-q['temperature_c']) for p,q in zip(result['probes'],expected['points'],strict=True)]
                    check('analytic_28_points',max(errors)<=expected['max_abs_temperature_error_k'])
                if 'heat_w_per_m' in expected:
                    side='bottom' if case['id'].startswith('P') else 'left'
                    check(case['id']+'_independent_heat',abs(result['boundary_heat_into_domain_w_per_m'][side]-expected['heat_w_per_m'])<=expected['absolute_heat_tolerance_w_per_m'])
                check(case['id']+'_correct_status',record['status']==case['status'])
                mesh=result['mesh_check']
                check(case['id']+'_original_gates',mesh['fine_cells']<=160000 and (record['status']!='calculated' or (mesh['passed'] and mesh['max_temperature_difference_k']<=.1 and mesh['max_edge_heat_difference_relative']<=.01)))
                check(case['id']+'_unassessed_compliance',result['compliance_status']=='NOT_ASSESSED' and result['linear_thermal_transmittance_psi_w_mk'] is None)
                receipt['cases'].append({'id':case['id'],'seconds':duration,'status':record['status'],'max_probe_error_k':max(errors) if errors else None,'heat':result['boundary_heat_into_domain_w_per_m'],'mesh':mesh,'solver':result['linear_solver']});save(out/'receipt.json',receipt)
            check('material_change_matches_higher_conductance',records['H02']['result']['boundary_heat_into_domain_w_per_m']['left']>records['H01']['result']['boundary_heat_into_domain_w_per_m']['left'])
            current=path+'/'+records['P01']['thermalbridge_id']
            report=c.get(current+'/report.html');(out/'report.html').write_text(report.text,encoding='utf-8')
            check('report_preserves_method_and_noncertification',report.status_code==200 and '材料界面附近加密网格' in report.text and '不是完整热桥标准验证' in report.text)
            download=c.get(current+'/temperatures.csv');rows=list(csv.DictReader(io.StringIO(download.text)))
            (out/'temperatures.csv.gz').write_bytes(gzip.compress(download.content,mtime=0))
            check('csv_full_mesh_and_last_value',download.status_code==200 and len(rows)==records['P01']['result']['mesh_check']['fine_cells'] and float(rows[-1]['cell_temperature_c'])==records['P01']['result']['temperature_c'][-1][-1])
            body=copy.deepcopy(frozen['cases'][2]['input']);body['regions'][0]['conductivity']=None
            incomplete=req('POST',path,body);save(out/'incomplete.json',incomplete)
            check('missing_not_imputed',incomplete['status']=='incomplete' and incomplete['result']['temperature_c'] is None and c.get(path+'/'+incomplete['thermalbridge_id']+'/temperatures.csv').status_code==409)
            for label,change in [('negative_width',{'width':-.15}),('wrong_unit',{'length_unit':'inch'}),('mesh_budget',{'cell_size':1e-6}),('invented_strategy',{'mesh_strategy':'invented'})]:
                response=c.post(path,json={**frozen['cases'][2]['input'],**change});save(out/(label+'.json'),{'status_code':response.status_code,'body':response.json()});check(label+'_422',response.status_code==422)
            body=copy.deepcopy(frozen['cases'][2]['input']);body['regions'][0]['conductivity']=0.
            check('zero_conductivity_422',c.post(path,json=body).status_code==422)
            token=c.headers.pop('X-CSRF-Token');check('csrf_403',c.post(path,json=frozen['cases'][2]['input']).status_code==403);c.headers['X-CSRF-Token']=token
            with httpx.Client(base_url=c.base_url,trust_env=False) as anonymous:check('unauthorized_401',anonymous.get(current+'/temperatures.csv').status_code==401)
            req('PATCH',base+'/evidence/'+ev['evidence_id'],{'expected_revision':1,'review_state':'rejected','responsible_person':'Test harness','review_note':'Synthetic source withdrawn during acceptance'})
            stale=req('GET',current);save(out/'withdrawn.json',stale)
            check('evidence_withdraws_field',stale['status']=='stale' and stale['result'] is None)
            check('withdrawn_csv_409',c.get(current+'/temperatures.csv').status_code==409)
            check('withdrawn_report_has_no_heat_table','当前结果不可用' in c.get(current+'/report.html').text and '边界热流（W/m' not in c.get(current+'/report.html').text)
            check('runtime_code_unchanged',hashes=={p.name:sha(p) for p in (ROOT/'backend').glob('*.py')})
            receipt['completed']=True
    except Exception as exc:
        receipt['error']=type(exc).__name__+': '+str(exc);raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
        log.close();receipt['process_stopped']=process is None or process.poll() is not None;save(out/'receipt.json',receipt)
        print(json.dumps({'completed':receipt['completed'],'checks':len(receipt['checks']),'cases':receipt['cases']},ensure_ascii=False))
if __name__=='__main__':serve() if len(sys.argv)>1 and sys.argv[1]=='serve' else run()
