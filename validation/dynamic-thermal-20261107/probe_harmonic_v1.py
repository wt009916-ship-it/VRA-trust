"""Independent harmonic conduction gold frozen before native diagnostic probes."""
import cmath,copy,hashlib,json,math,re,sqlite3,sys,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent;sys.path.insert(0,str(repo))
from backend import core
from backend.execution import Policy,supervise
from backend.private_storage import private_mkdir
base=private_mkdir(Path(tempfile.gettempdir())/('vra-dynamic-harmonic-'+uuid.uuid4().hex))
objects=[[f.strip() for f in p.split(',')] for p in re.sub(r'!.*','',json.loads((repo/'fixtures/test/native_zone_sizing_projection.json').read_text())['model_idf']).split(';') if p.strip()]
specs=[{'case':'massless','mass':False,'steps':6},{'case':'massive_10min','mass':True,'steps':6},{'case':'massive_5min','mass':True,'steps':12}]
for s in specs:
    s.update(L_m=.2,conductivity_W_mK=.5,density_kg_m3=1000,cp_J_kgK=1000,area_m2=110,indoor_C=20,outer_mean_C=0,outer_amplitude_K=5,period_h=24,inside_h=10,outside_h=25)
    resistance=.1+.4+.04
    if s['mass']:
        gamma=cmath.sqrt(1j*2*math.pi/(86400*(.5/1e6)));z=gamma*.2
        a=d=cmath.cosh(z);b=cmath.sinh(z)/(.5*gamma);c=.5*gamma*cmath.sinh(z)
        transfer=b+.04*d+.1*a+.04*.1*c
    else:transfer=complex(resistance)
    amplitude=5/transfer
    s['analytical_heating_mean_W']=110*20/resistance
    s['analytical_heating_amplitude_W']=110*abs(amplitude)
    s['analytical_inward_phase_rad']=cmath.phase(amplitude)
    s['expected_hourly_heating_W']=[sum(110*(20/resistance-(amplitude*cmath.exp(1j*2*math.pi*((hour-1)+(k+1)/s['steps'])/24)).imag) for k in range(s['steps']))/s['steps'] for hour in range(1,25)]
    s['tolerance_W']=max(1,110*abs(amplitude)*.02)
    s['gold_scope']='1D homogeneous harmonic conduction + prescribed films, uniform six faces, clamped indoor 20 C; endpoint-sampled hourly mean matching declared native output convention; no solar, ventilation, latent loads or real-building calibration.'
core.write_json(base/'predeclared.json',specs)
receipt={'base':str(base),'gold_sha256':core.sha(base/'predeclared.json'),'script_sha256':core.sha(Path(__file__)),'source_fixture_sha256':core.sha(repo/'fixtures/test/native_zone_sizing_projection.json'),'cases':[]}
core.write_json(out/'harmonic-probe-inputs-v1.json',{k:v for k,v in receipt.items() if k!='cases'})
for spec in specs:
    work=private_mkdir(base/spec['case']);output=private_mkdir(work/'output');logs=private_mkdir(work/'logs')
    data=copy.deepcopy(objects);data=[x for x in data if not (x[0]=='SizingPeriod:DesignDay' and x[1]=='Synthetic summer')]
    for obj in data:
        if obj[0]=='Timestep':obj[1]=str(spec['steps'])
        if obj[0]=='Material:NoMass':
            if spec['mass']:obj[:]=['Material','R2','Smooth','.2','.5','1000','1000','.9','.7','.7']
            else:obj[3]='.4'
        if obj[0]=='SurfaceProperty:OtherSideCoefficients':obj[:]=['SurfaceProperty:OtherSideCoefficients','Ambient','25','5','0','0','0','0','0','','Yes','24','0']
    for name in ['Zone Air System Sensible Heating Rate','Zone Air System Sensible Cooling Rate','Zone Air System Sensible Heating Energy','Zone Air System Sensible Cooling Energy','Zone Air Humidity Ratio']:
        data.append(['Output:Variable','*',name,'Hourly'])
    model=work/'input.idf';model.write_text('\n'.join(','.join(x)+';' for x in data),encoding='ascii')
    row={'case':spec['case'],'model_sha256':core.sha(model),'status':'not_run'}
    try:
        row['execution']=supervise([core.engine_path(),'-d',output,model],work,logs,Policy(),90,output=output)
        err=(output/'eplusout.err').read_text(errors='replace')
        assert not re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*',err,re.I),'Native severe/fatal'
        with sqlite3.connect((output/'eplusout.sql').resolve().as_uri()+'?mode=ro',uri=True) as con:
            con.row_factory=sqlite3.Row
            row['environments']=[dict(x) for x in con.execute('SELECT * FROM EnvironmentPeriods')]
            row['dictionary']=[dict(x) for x in con.execute("SELECT * FROM ReportDataDictionary WHERE Name IN ('Zone Mean Air Temperature','Zone Air System Sensible Heating Rate','Zone Air System Sensible Cooling Rate','Zone Air System Sensible Heating Energy','Zone Air System Sensible Cooling Energy')")]
            samples=[dict(x) for x in con.execute("SELECT t.*,r.Value FROM ReportData r JOIN ReportDataDictionary d USING(ReportDataDictionaryIndex) JOIN Time t USING(TimeIndex) WHERE d.Name='Zone Air System Sensible Heating Rate' AND d.ReportingFrequency='Hourly' AND COALESCE(t.WarmupFlag,0)=0 ORDER BY t.TimeIndex")]
            row['native_samples']=samples
            assert len(samples)==24,len(samples)
            row['absolute_errors_W']=[abs(x['Value']-expected) for x,expected in zip(samples,spec['expected_hourly_heating_W'])]
            row['maximum_error_W']=max(row['absolute_errors_W']);row['tolerance_W']=spec['tolerance_W']
            row['within_predeclared_tolerance']=row['maximum_error_W']<=spec['tolerance_W']
            row['native_sql_sha256']=core.sha(output/'eplusout.sql')
            row['status']='passed' if row['within_predeclared_tolerance'] else 'numerical_mismatch'
    except Exception as exc:row.update(status='failed',error=type(exc).__name__+': '+str(exc))
    core.write_json(work/'record.json',row);receipt['cases'].append(row)
    print(json.dumps({k:row[k] for k in ['case','status','maximum_error_W','tolerance_W','error'] if k in row}),flush=True)
core.write_json(out/'harmonic-probe-v1.json',receipt)
