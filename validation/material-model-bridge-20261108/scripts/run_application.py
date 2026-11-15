"""Frozen public-reference scenario through real HTTP and native EnergyPlus."""
from pathlib import Path
import os,sys,subprocess,signal,time,json,hashlib,secrets,socket,re,sqlite3,traceback
from decimal import Decimal
import httpx
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-thermal-model-bridge-20261108')
out=Path('C:/Users/18483/AppData/Local/Temp/vra-model-bridge-application-20261108');out.mkdir(exist_ok=False)
sys.path.insert(0,str(repo))
from backend.private_storage import private_mkdir
private_mkdir(out/'data')
port=18779
with socket.socket() as sock:sock.bind(('127.0.0.1',port))
raw=(repo/'fixtures/demo/reference_5zone/baseline.idf').read_bytes()
weather=(repo/'fixtures/demo/reference_5zone/weather.epw').read_bytes()
def parse(data):
    return [[t.strip() for t in block.split(',')] for block in re.sub(r'!.*','',data.decode('utf-8')).split(';') if block.strip()]
objects=parse(raw);original_materials={o[1]:o for o in objects if o[0].lower()=='material'}
original_wall=next(o[2:] for o in objects if o[:2]==['Construction','WALL-1'])
targets=['FRONT-1','RIGHT-1','BACK-1','LEFT-1']
assert len(targets)==len(set(targets))
for n in targets:assert next(o for o in objects if o[0].lower()=='buildingsurface:detailed' and o[1]==n)[2:6]==['WALL','WALL-1','SPACE'+{'FRONT-1':'1-1','RIGHT-1':'2-1','BACK-1':'3-1','LEFT-1':'4-1'}[n],'Outdoors']
layers=[];properties=[]
for name in original_wall:
    m=original_materials[name]
    layers.append({'name':name,'thickness':float(m[3]),'thickness_unit':'m','conductivity':float(m[4]),'conductivity_unit':'W/(m K)',
        'source':'EnergyPlus 9.0.1 5ZoneAirCooled reference Material '+name,'correction_factor':1.,'correction_basis':'Original reference dry material parameter'})
    properties.append(dict(density_kg_m3=float(m[5]),specific_heat_j_kg_k=float(m[6]),roughness=m[2],thermal_absorptance=float(m[7]),solar_absorptance=float(m[8]),visible_absorptance=float(m[9]),property_source='EnergyPlus 9.0.1 5ZoneAirCooled reference Material '+name))
scenario_layer={'name':'Declared extra exterior insulation','thickness':40.,'thickness_unit':'mm','conductivity':40.,'conductivity_unit':'mW/(m K)','source':'Independent declared scenario, not measured or manufacturer certified','correction_factor':1.,'correction_basis':'Dry scenario at declared constant conductivity'}
scenario_property=dict(density_kg_m3=35.,specific_heat_j_kg_k=840.,roughness='MediumRough',thermal_absorptance=.9,solar_absorptance=.6,visible_absorptance=.6,property_source='Independent hypothetical insulation scenario; no product certification')
assembly={'name':'Public reference original wall','layers':layers,'rsi_m2k_w':.13,'rse_m2k_w':.04,'surface_basis':'Declared one-dimensional comparison films only; not written into EnergyPlus','application':'Public reference model; uncalibrated hypothetical material scenario'}
scenario={**assembly,'name':'Four occupied-zone walls with 40 mm exterior insulation','layers':[scenario_layer]+layers}
oracle_r=sum(Decimal(original_materials[n][3])/Decimal(original_materials[n][4]) for n in original_wall)
oracle_u=1/(Decimal('.17')+oracle_r);oracle_derived_u=1/(Decimal('.17')+oracle_r+1)
frozen={'baseline_sha256':hashlib.sha256(raw).hexdigest(),'weather_sha256':hashlib.sha256(weather).hexdigest(),'target_surfaces':targets,
 'assembly':assembly,'scenario':scenario,'properties_outside_to_inside':[scenario_property]+properties,
 'independent_original_r':str(oracle_r),'independent_original_u':str(oracle_u),'independent_derived_u':str(oracle_derived_u),
 'assertions':['only four named construction references change; all other original fields/bytes preserved','five ordinary materials in outside-to-inside order; no surface-film material',
 'preview and explicit confirmation required','new pending ASSUMED evidence; original unchanged','two actual native annual runs with same weather/engine/area',
 'annual saving recomputed independently from native SQLite total site energy, no assumed sign or U-proxy','source withdrawal revokes model, run, comparison and download','anonymous/cross-account/CSRF refusal'],
 'scope':'New public reference application task, not a measured building or independent product certification'}
def save(name,obj): (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
save('frozen.json',frozen)
env=dict(os.environ);env.update(VRA_DATA_DIR=str(out/'data'),ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',PYTHONDONTWRITEBYTECODE='1')
log=(out/'server.log').open('wb')
proc=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
checks=[]
def verify(value,name):
    checks.append({'name':name,'passed':bool(value)});save('checks.json',checks);assert value,name
try:
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,limits=httpx.Limits(keepalive_expiry=4)) as c:
        for _ in range(80):
            if proc.poll() is not None:raise RuntimeError('API exited before health')
            try:
                if c.get('/api/health').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.25)
        else:raise RuntimeError('API health timeout')
        def call(method,path,expected=200,**kwargs):
            r=c.request(method,path,**kwargs)
            if r.status_code!=expected:
                save('unexpected-response.json',{'method':method,'path':path,'expected':expected,'status':r.status_code,'body':r.text})
                raise AssertionError(str(r.status_code)+' '+path+' '+r.text[:500])
            return r.json()
        auth=call('POST','/api/auth/register',json={'username':'model_bridge_acceptance','display_name':'Isolated material model acceptance','password':secrets.token_urlsafe(30)})
        c.headers['X-CSRF-Token']=auth['csrf_token']
        project=call('POST','/api/projects',201,json={'name':'New material-to-energy reference task','data_nature':'engineering_reference','building':{'use':'office reference','location':'Golden Colorado reference','region':'US-CO','area_m2':927.2}})
        pid=project['project_id'];base='/api/projects/'+pid
        evidence={}
        for kind,data,filename in [('idf',raw,'original.idf'),('epw',weather,'reference.epw')]:
            file=call('POST',base+'/files',201,files={'file':(filename,data)})
            ev=call('POST',base+'/evidence',201,json={'type':kind,'name':'Public reference '+kind,'scheme_id':'baseline' if kind=='idf' else None,
              'source_file':file['file_id'],'source_locator':'EnergyPlus 9.0.1 distributed reference input','authority':'EnergyPlus public example',
              'permission':'Public reference validation only','acquisition_method':'Existing repository public reference input','responsible_person':'Acceptance test','status':'IMPORTED'})
            ev=call('PATCH',base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'confirmed','responsible_person':'Acceptance test','review_note':'Reference input inspected; not an as-built or calibrated building'})
            evidence[kind]=ev
        initial=call('POST',base+'/thermal',201,json=assembly);thermal=call('POST',base+'/thermal',201,json=scenario)
        verify(abs(initial['result']['u_w_m2k']-float(oracle_u))<1e-12,'original U matches independent Decimal oracle')
        verify(abs(thermal['result']['u_w_m2k']-float(oracle_derived_u))<1e-12,'scenario U matches independent Decimal oracle')
        plan={'name':scenario['name'],'source_evidence_id':evidence['idf']['evidence_id'],'scheme_id':'R1',
              'assignments':[{'thermal_id':thermal['thermal_id'],'surface_names':targets,'layer_order':'outside_to_inside','properties':[scenario_property]+properties}],
              'responsible_person':'Acceptance test','basis':'Explicit four occupied-zone wall references; original plenum walls, roof, geometry, schedules and HVAC preserved'}
        preview=call('POST',base+'/retrofit-previews',json=plan);save('preview.json',preview)
        record=call('POST',base+'/retrofits',201,json={**plan,'expected_preview_hash':preview['preview_hash'],'acknowledge_scope':True});save('generated.json',record)
        rid=record['retrofit_id'];route=base+'/retrofits/'+rid
        verify(record['evidence_review']['review_state']=='pending' and record['evidence_review']['status']=='ASSUMED','generated scenario is pending and assumed')
        verify(not call('GET',base+'/gate?scheme_id=R1')['can_simulate'],'unreviewed model blocked from simulation')
        derived=c.get(route+'/model.idf');verify(derived.status_code==200,'current derived model downloadable')
        (out/'derived.idf').write_bytes(derived.content)
        expected=raw.decode('utf-8')
        # Independent location oracle uses surface object/name, not producer-supplied spans.
        newconstruction=record['changes']['assignments'][0]['construction']
        for name in targets:
            pattern=r'(BuildingSurface:Detailed\s*,\s*'+re.escape(name)+r'\s*,\s*!?[^\n]*\n\s*WALL\s*,[^\n]*\n\s*)WALL-1'
            # Resolve object fields independently while retaining comments and whitespace.
            objpattern=r'(?is)BuildingSurface:Detailed\s*,(?:(?!;).)*?;'
            matches=[m for m in re.finditer(objpattern,expected) if parse(m[0].encode())[0][1]==name]
            assert len(matches)==1
            m=matches[0];replacement,count=re.subn(r'\bWALL-1(?=\s*,)',newconstruction,m[0],count=1)
            assert count==1;expected=expected[:m.start()]+replacement+expected[m.end():]
        prefix=derived.content.split(b'\n\n! VRA derived')[0]
        verify(prefix==expected.encode(),'exact bytes preserved outside four construction references')
        newobjs=parse(derived.content);newmaterials=[o for o in newobjs if o[0]=='Material' and o[1].startswith('VRA_')]
        verify(len(newmaterials)==5 and len(newobjs)==len(objects)+6,'five materials and one construction; no film layers')
        verify([float(o[3]) for o in newmaterials]==[.04]+[float(original_materials[n][3]) for n in original_wall],'derived layer thickness/order match independently declared inputs')
        verify(c.get(base+'/files/'+evidence['idf']['source_file']).content==raw,'baseline original retained byte for byte')
        ev=record['evidence_review'];call('PATCH',base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'confirmed','responsible_person':'Acceptance test','review_note':'Derived references and declared material properties independently inspected; scenario only'})
        jobs=[]
        for scheme in ['baseline','R1']:
            r=call('POST','/api/runs',202,json={'project_id':pid,'scheme_id':scheme,'factor_profile_id':'none'});jobs.append(r['run_id'])
        deadline=time.monotonic()+650
        while time.monotonic()<deadline:
            views=[call('GET','/api/runs/'+j) for j in jobs]
            if all(v['status'] not in {'queued','running'} for v in views):break
            time.sleep(2)
        save('runs.json',views);verify(all(v['status']=='succeeded' for v in views),'two actual native annual simulations succeeded')
        comparison=call('POST',route+'/comparison',json={'run_ids':jobs});save('comparison.json',comparison)
        energies=[];sql_oracles=[]
        for job,view in zip(jobs,views):
            sqls=list((out/'data/runs'/job).rglob('eplusout.sql'));assert len(sqls)==1
            with sqlite3.connect(sqls[0]) as db:
                cells=db.execute("SELECT Value,Units FROM TabularDataWithStrings WHERE ReportName='AnnualBuildingUtilityPerformanceSummary' AND ReportForString='Entire Facility' AND TableName='Site and Source Energy' AND RowName='Total Site Energy' AND ColumnName='Total Energy'").fetchall()
                assert len(cells)==1
                value,unit=cells[0];scale={'kWh':Decimal(1),'GJ':Decimal(1000)/Decimal('3.6'),'MJ':Decimal(1)/Decimal('3.6'),'J':Decimal(1)/Decimal(3600000)}[unit]
                kwh=Decimal(value.strip())*scale;energies.append(kwh)
                verify(abs(view['metrics']['annual_energy_kwh']-float(kwh))<1e-8,view['scheme_id']+' SQL annual energy matches independent unit conversion')
                sql_oracles.append({'run_id':job,'scheme':view['scheme_id'],'raw_value':value,'unit':unit,'energy_kwh_decimal':str(kwh),'sql_sha256':hashlib.sha256(sqls[0].read_bytes()).hexdigest()})
        saving=(1-energies[1]/energies[0])*100
        derivedview=next(v for v in comparison['comparison']['results'] if v['scheme_id']=='R1')
        verify(abs(derivedview['saving_rate_pct']-float(saving))<1e-10,'annual saving independently computed from native SQL')
        u_reduction=(1-oracle_derived_u/oracle_u)*100
        verify(abs(float(saving-u_reduction))>.01,'annual saving differs from U reduction and is not substituted')
        save('independent-crosscheck.json',{'sql_cells':sql_oracles,'annual_saving_rate_pct':str(saving),'u_reduction_pct':str(u_reduction),'original_u':str(oracle_u),'derived_u':str(oracle_derived_u)})
        (out/'report.html').write_text(c.get(route+'/report.html').text,encoding='utf-8')
        token=c.headers.pop('X-CSRF-Token');verify(c.post(route+'/comparison',json={'run_ids':jobs}).status_code==403,'CSRF required');c.headers['X-CSRF-Token']=token
        with httpx.Client(base_url=c.base_url,timeout=15) as other:
            verify(other.get(route+'/model.idf').status_code==401,'anonymous download refused')
            r=other.post('/api/auth/register',json={'username':'model_other_user','display_name':'Other isolated user','password':secrets.token_urlsafe(30)})
            verify(r.status_code==200,'second isolated account created')
            verify(other.get(route).status_code==404,'other account cannot inspect model derivation')
        ev=evidence['idf'];call('PATCH',base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'pending','responsible_person':'Acceptance test','review_note':'Withdraw baseline reference review for stale acceptance'})
        stale=call('GET',route);save('stale.json',stale)
        verify(stale['status']=='stale' and stale['changes'] is None,'source withdrawal clears derived change result')
        verify(c.get(route+'/model.idf').status_code==409,'stale derived model download refused')
        stale_runs=[call('GET','/api/runs/'+j) for j in jobs];save('stale-runs.json',stale_runs)
        verify(all(v['status']=='stale' and v['metrics'] is None for v in stale_runs),'source withdrawal clears both baseline and derived annual results')
        verify(c.post(route+'/comparison',json={'run_ids':jobs}).status_code==409,'source withdrawal prevents annual comparison')
        verify(not call('GET',base+'/gate?scheme_id=R1')['can_simulate'],'stale thermal derivative cannot start new run')
        save('summary.json',{'project_id':pid,'retrofit_id':rid,'runs':jobs,'checks':len(checks),'passed':sum(c['passed'] for c in checks),'native_energy_kwh':[str(v) for v in energies],'annual_saving_rate_pct':str(saving),'u_reduction_pct':str(u_reduction)})
except BaseException:
    (out/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
finally:
    if proc.poll() is None:
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        try:proc.wait(timeout=25)
        except subprocess.TimeoutExpired:print('Owned API did not exit: '+str(proc.pid),flush=True)
    log.close();save('service-exit.json',{'pid':proc.pid,'exit_code':proc.poll(),'stopped':proc.poll() is not None})
print(json.dumps({'checks':len(checks),'passed':sum(c['passed'] for c in checks),'service_stopped':proc.poll() is not None}),flush=True)
