"""Predeclared nonlinear air-capacity balance vs fresh native free-floating runs."""
import hashlib,json,math,re,sqlite3,sys,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent;sys.path.insert(0,str(repo))
from backend import core
from backend.execution import Policy,supervise
from backend.private_storage import private_mkdir
from scripts.verify_hourly_thermal import model
base=private_mkdir(Path(tempfile.gettempdir())/('vra-freefloat-'+uuid.uuid4().hex))
source=repo/'fixtures/test/native_zone_sizing_projection.json'
base_model=json.loads(source.read_text())['model_idf']
specs=[dict(name='steady',steps=6,cap=100,amplitude=0,algorithm='AnalyticalSolution'),
       dict(name='periodic_1min',steps=60,cap=100,amplitude=5,algorithm='AnalyticalSolution'),
       dict(name='periodic_5min',steps=12,cap=100,amplitude=5,algorithm='AnalyticalSolution'),
       dict(name='periodic_10min',steps=6,cap=100,amplitude=5,algorithm='AnalyticalSolution'),
       dict(name='half_capacity',steps=60,cap=50,amplitude=5,algorithm='AnalyticalSolution'),
       dict(name='internal_step',steps=60,cap=100,amplitude=0,algorithm='AnalyticalSolution',gains=True),
       dict(name='third_order',steps=60,cap=100,amplitude=5,algorithm='ThirdOrderBackwardDifference'),
       dict(name='euler',steps=60,cap=100,amplitude=5,algorithm='EulerMethod')]
for spec in specs:
    spec.setdefault('gains',False)
    spec.update(mean_C=10,volume_m3=75,area_m2=110,wall_R=.4,inside_h=10,outside_h=25,pressure_Pa=101325,
                cp_dry_J_kgK=1004.84,cp_vapour_J_kgK=1858.95,gas_constant=287,humidity_floor=1e-5,tolerance_K=.02)
    conductance=110/.54
    air_constant=75*spec['cap']*101325*(1004.84+1858.95*1e-5)/(287*(1+1.6077687*1e-5))
    dt=3600/spec['steps'];temperature=10
    boundary=[10+spec['amplitude']*math.sin(2*math.pi*i/(24*spec['steps'])) for i in range(1,24*spec['steps']+1)]
    spec['boundary_C']=boundary
    for day in range(200):
        start=temperature;values=[]
        for index,external in enumerate(boundary):
            gain=1000 if spec['gains'] and index>=12*spec['steps'] else 0
            equilibrium_K=external+gain/conductance+273.15
            temperature=equilibrium_K/(1+(equilibrium_K/(temperature+273.15)-1)*math.exp(-conductance/air_constant*equilibrium_K*dt))-273.15
            values.append(temperature)
        if abs(start-temperature)<1e-12:break
    else:raise AssertionError('Independent periodic solution did not converge')
    spec['gold_periodic_start_C']=start;spec['gold_periodic_days']=day+1
    spec['gold_hourly_temperature_C']=[math.fsum(values[i:i+spec['steps']])/spec['steps'] for i in range(0,len(values),spec['steps'])]
    seed={'name':spec['name'],'density':None,'steps':spec['steps'],'phases':[1],'multiplier':1,'list_multiplier':1,'gains':spec['gains']}
    objects=[[v.strip() for v in p.split(',')] for p in model(base_model,seed).split(';') if p.strip()]
    for obj in objects:
        if obj[0]=='SimulationControl':obj[:]=['SimulationControl','No','No','No','Yes','No']
        if obj[0]=='Building':obj[-2:] = ['100','20']
        if obj[0]=='SizingPeriod:DesignDay':obj[5]=obj[10]='-60'
        if obj[0]=='Schedule:Constant' and obj[1]=='Control':obj[3]='0'
        if obj[0]=='Schedule:Compact' and obj[1]=='Boundary_1':
            for index,value in enumerate(boundary):obj[7+2*index]=format(value,'.15g')
    objects.extend([['ZoneAirHeatBalanceAlgorithm',spec['algorithm']],
                    ['ZoneCapacitanceMultiplier:ResearchSpecial','Known air capacity','Box_1',str(spec['cap']),'1','1','1'],
                    ['Output:Variable','*','Zone Air Humidity Ratio','Hourly']])
    work=private_mkdir(base/spec['name'])
    (work/'input.idf').write_text('\n'.join(','.join(o)+';' for o in objects),encoding='ascii')
    spec['model_sha256']=core.sha(work/'input.idf')
core.write_json(base/'predeclared.json',{'method':'Exact nonlinear C(T)=S/(T+273.15) piecewise-constant boundary integration; no native outputs used as gold; hourly endpoint averages. Dry-air property floor must be verified in output.','specs':specs})
receipt={'base':str(base),'script_sha256':core.sha(Path(__file__)),'source_sha256':core.sha(source),'gold_sha256':core.sha(base/'predeclared.json'),'cases':[]}
core.write_json(out/'probe-inputs-v1.json',{k:v for k,v in receipt.items() if k!='cases'})
for spec in specs:
    work=base/spec['name'];output=private_mkdir(work/'output');logs=private_mkdir(work/'logs')
    row={'name':spec['name'],'status':'not_run','model_sha256':spec['model_sha256'],'tolerance_K':spec['tolerance_K']}
    try:
        row['execution']=supervise([core.engine_path(),'-d',output,work/'input.idf'],work,logs,Policy(),120,output=output)
        err=(output/'eplusout.err').read_text(errors='replace')
        assert not re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*',err,re.I),'Native severe/fatal'
        with sqlite3.connect((output/'eplusout.sql').resolve().as_uri()+'?mode=ro',uri=True) as con:
            results={}
            for variable in ['Zone Air Temperature','Zone Air Humidity Ratio','Zone Air System Sensible Heating Rate','Zone Air System Sensible Cooling Rate']:
                rows=con.execute('SELECT t.Hour,r.Value FROM ReportData r JOIN ReportDataDictionary d USING(ReportDataDictionaryIndex) JOIN Time t USING(TimeIndex) WHERE d.Name=? AND d.ReportingFrequency=? AND COALESCE(t.WarmupFlag,0)=0 ORDER BY t.TimeIndex',(variable,'Hourly')).fetchall()
                assert len(rows)==24,(variable,len(rows));results[variable]=[v for h,v in rows]
            row['native_hourly']=results
            row['maximum_temperature_error_K']=max(abs(a-b) for a,b in zip(results['Zone Air Temperature'],spec['gold_hourly_temperature_C']))
            row['humidity_max']=max(results['Zone Air Humidity Ratio'])
            row['HVAC_absolute_max_W']=max(abs(v) for name in ['Zone Air System Sensible Heating Rate','Zone Air System Sensible Cooling Rate'] for v in results[name])
            row['dry_property_floor_verified']=row['humidity_max']<=1e-5
            row['status']='passed' if row['maximum_temperature_error_K']<=spec['tolerance_K'] and row['dry_property_floor_verified'] and row['HVAC_absolute_max_W']<1e-6 else 'numerical_or_premise_mismatch'
            row['sql_sha256']=core.sha(output/'eplusout.sql')
    except Exception as exc:row.update(status='failed',error=type(exc).__name__+': '+str(exc))
    receipt['cases'].append(row);core.write_json(work/'receipt.json',row)
    print(json.dumps({k:v for k,v in row.items() if k not in ['execution','native_hourly','model_sha256','sql_sha256']}),flush=True)
core.write_json(out/'probe-freefloat-v1.json',receipt)
