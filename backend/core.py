"""Validated computation and evidence layer. No silent mock or numerical fallback.

Integration revision of the three submissions: Guo's evidence rules, Gong's task /
dependency design and Xiong's dashboard contract. Historical source is archived.
Python standard library only. Not a certified design or carbon-credit verifier.
"""
from __future__ import annotations
import hashlib, json, math, os, re, shutil, sqlite3, subprocess, tempfile, time, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PARSER_VERSION='native-sql-0.2.0'
REPORT_NAME='AnnualBuildingUtilityPerformanceSummary'
class ValidationError(ValueError): pass
def now(): return datetime.now(timezone.utc).isoformat()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def hash_json(data):return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def read_json(p):
    def reject(x):raise ValidationError('JSON contains non-finite value: '+x)
    return json.loads(Path(p).read_text(encoding='utf-8-sig'),parse_constant=reject)
def write_json(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(p)
def number(v,name,minimum=0,positive=False):
    if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<minimum or (positive and v<=0):
        raise ValidationError(name+' must be a finite '+('positive' if positive else 'nonnegative')+' number')
    return float(v)
def relative_file(root,value):
    root=Path(root).resolve();p=(root/value).resolve()
    if not p.is_relative_to(root) or not p.is_file():raise ValidationError('Missing or unsafe registered file: '+str(value))
    return p
def code_hash():
    # Physics validity must not depend on UI, authentication or Agent code.
    # Keep the entire audited computation module conservative for physics changes.
    return hash_json({'physics_core':sha(Path(__file__)), 'parser':PARSER_VERSION})
def engine_path():
    configured=os.environ.get('ENERGYPLUS_EXE')
    if not configured and (ROOT/'config.local.json').is_file():configured=read_json(ROOT/'config.local.json').get('energyplus_exe')
    configured=configured or shutil.which('energyplus')
    if not configured or str(configured).lower()=='mock' or not Path(configured).is_file():raise ValidationError('请设置 ENERGYPLUS_EXE 或 config.local.json 中的 energyplus_exe；不自动降级为模拟结果。')
    return Path(configured).resolve()
def load_case(case_id):
    registry=read_json(ROOT/'cases/registry.json')
    if case_id not in registry:raise ValidationError('未登记的 case_id')
    c=read_json(relative_file(ROOT,registry[case_id]))
    if c['case_id']!=case_id:raise ValidationError('case_id 不一致')
    return c
def get_scheme(case,scheme_id):
    matches=[s for s in case['schemes'] if s['scheme_id']==scheme_id]
    if len(matches)!=1:raise ValidationError('未登记或重复的 scheme_id')
    return matches[0]
def profiles():return read_json(ROOT/'cases/carbon_profiles.json')
def get_profile(profile_id):
    ps=profiles()
    if profile_id not in ps:raise ValidationError('未登记的碳因子配置')
    return ps[profile_id]

def parse_sql(path):
    """Read E+ native SQLite, require one full-year weather period and explicit units."""
    p=Path(path)
    if not p.is_file() or p.stat().st_size==0:raise ValidationError('SQL missing/empty')
    con=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    try:
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValidationError('SQLite integrity failed')
        sim=con.execute('SELECT EnergyPlusVersion,Completed,CompletedSuccessfully FROM Simulations').fetchall()
        if len(sim)!=1 or tuple(sim[0])[1:]!=(1,1):raise ValidationError('Simulation not uniquely completed successfully')
        env=con.execute('SELECT EnvironmentPeriodIndex FROM EnvironmentPeriods WHERE EnvironmentType=3').fetchall()
        if len(env)!=1:raise ValidationError('Expected exactly one weather run period')
        dates=con.execute('SELECT DISTINCT Month,Day FROM Time WHERE EnvironmentPeriodIndex=? AND COALESCE(WarmupFlag,0)=0 AND IntervalType=1',(env[0][0],)).fetchall()
        covered={(r[0],r[1]) for r in dates}
        if len(covered) not in (365,366) or (1,1) not in covered or (12,31) not in covered:raise ValidationError('Not a full-year weather run; annual metric rejected')
        hours=con.execute('SELECT SUM(Interval)/60.0 FROM Time WHERE EnvironmentPeriodIndex=? AND COALESCE(WarmupFlag,0)=0 AND IntervalType=1',(env[0][0],)).fetchone()[0]
        if hours not in (8760,8784):raise ValidationError('Incomplete annual hourly record coverage')
        rows=con.execute('SELECT TableName,RowName,ColumnName,Units,Value FROM TabularDataWithStrings WHERE ReportName=? AND ReportForString=?',(REPORT_NAME,'Entire Facility')).fetchall()
        def one(table,row,column):
            found=[r for r in rows if (r['TableName'],r['RowName'],r['ColumnName'])==(table,row,column)]
            if len(found)!=1:raise ValidationError('Missing/duplicate SQL cell: '+str((table,row,column)))
            r=found[0]
            try:v=float(r['Value'])
            except (ValueError,TypeError):raise ValidationError('Invalid numeric SQL cell')
            number(v,'SQL '+row)
            return v,r['Units'],{'table':table,'row':row,'column':column,'unit':r['Units'],'raw_value':r['Value'].strip()}
        scales={'kWh':1,'GJ':1000/3.6,'MJ':1/3.6,'J':1/3600000}
        def energy(table,row,col):
            v,u,loc=one(table,row,col)
            if u not in scales:raise ValidationError('Unsupported energy unit: '+u)
            return v*scales[u],loc
        total,loc=energy('Site and Source Energy','Total Site Energy','Total Energy')
        area,u,aloc=one('Building Area','Total Building Area','Area')
        if u!='m2' or area<=0:raise ValidationError('Invalid floor area')
        carriers={};locators={'total_energy':loc,'area':aloc}
        for r in rows:
            if r['TableName']=='End Uses' and r['RowName']=='Total End Uses' and r['ColumnName']!='Water':
                value,cloc=energy('End Uses','Total End Uses',r['ColumnName'])
                carriers[r['ColumnName']]=value;locators[r['ColumnName']]=cloc
        if not carriers or abs(sum(carriers.values())-total)>max(1,total*.005):raise ValidationError('Fuel totals do not reconcile to site total')
        comfort={}
        for r in rows:
            if r['TableName']=='Comfort and Setpoint Not Met Summary' and r['Units'].lower() in ('hr','hrs','hours'):
                try:v=float(r['Value'])
                except (ValueError,TypeError):continue
                if math.isfinite(v):comfort[r['RowName']+' / '+r['ColumnName']]=v
        return {'annual_energy_kwh':total,'area_m2':area,'eui_kwh_m2a':total/area,'energy_by_carrier_kwh':carriers,'annual_days':len(covered),'engine_sql_version':sim[0][0],'locators':locators,'comfort_hours':comfort,'scope':'annual_site_energy_not_source_energy','parser_version':PARSER_VERSION}
    except sqlite3.Error as e:raise ValidationError('Native EnergyPlus SQLite rejected: '+str(e)) from e
    finally:con.close()

def calculate_carbon(energy,profile,region):
    if profile.get('region') not in ('*',region):raise ValidationError('碳因子地区与案例不匹配，禁止自动套用')
    rows=[];missing=[]
    for carrier,amount in energy.items():
        amount=number(amount,carrier)
        factor=profile.get('factors',{}).get(carrier)
        if amount==0:continue
        if not factor:missing.append(carrier);continue
        if factor.get('unit')!='kgCO2/kWh':raise ValidationError('排放因子单位不匹配：'+carrier)
        val=number(factor.get('value'),'factor')
        if not factor.get('source') or not factor.get('factor_id'):raise ValidationError('Missing factor provenance')
        rows.append({'carrier':carrier,'energy_kwh':amount,'factor':val,'factor_id':factor['factor_id'],'factor_source':factor['source'],'carbon_kg':amount*val})
    subtotal=sum(r['carbon_kg'] for r in rows)
    complete=not missing and bool(profile.get('factors'))
    return {'status':('scenario' if profile.get('scenario') else 'calculated') if complete else 'incomplete','operating_carbon_kg':subtotal if complete else None,'covered_carbon_kg':subtotal if rows else None,'missing_carriers':missing,'coverage':'positive site-energy carriers only; direct and electricity CO2, not full lifecycle or all GHG','profile_id':profile['profile_id'],'profile_hash':hash_json(profile),'scenario':profile.get('scenario',False),'rows':rows,'lca_total_kg':None,'ccer_issued_t':None}

ALL={'energy','eui','saving_rate','operating_carbon','cost','comparison','report'}
DEPENDENCIES={'model':ALL,'weather':ALL,'engine':ALL,'code':ALL,'case':ALL,'sql':ALL,'result':ALL,'binding':ALL,'factor':{'operating_carbon','comparison','report'},'cost':{'cost','comparison','report'},'display':{'report'}}
def invalidation(old,new):
    changed=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    affected=set()
    for k in changed:affected.update(DEPENDENCIES.get(k,ALL))
    energy_keys={'model','weather','engine','code','case'}
    action='reuse'
    if set(changed)&energy_keys or any(k not in DEPENDENCIES for k in changed):action='rerun_energyplus'
    elif set(changed)&{'binding','sql','result'}:action='reject_and_restore_or_reparse'
    elif 'factor' in changed:action='recalc_carbon'
    elif 'cost' in changed:action='recalc_cost'
    elif 'display' in changed:action='regenerate_report'
    return {'changed':changed,'invalid':sorted(affected),'action':action,'energyplus_rerun_planned':action=='rerun_energyplus','energyplus_calls_executed':0}

def source_fingerprints(case,scheme,profile,engine,file_root=None):
    root=Path(file_root) if file_root else ROOT
    return {'model':sha(relative_file(root,scheme['model'])),'weather':sha(relative_file(root,case['weather'])),'case':hash_json(case),'factor':hash_json(profile),'engine':sha(engine),'code':code_hash()}

def run_simulation(case_id,scheme_id,profile_id,run_dir,timeout=300,*,case_override=None,profile_override=None,file_root=None):
    rd=Path(run_dir);rd.mkdir(parents=True,exist_ok=True)
    identity={'run_id':rd.name,'case_id':case_id,'scheme_id':scheme_id,'status':'running','started_at':now(),'data_nature':'engineering_reference'}
    manifest={**identity,'engine_calls_executed':0,'artifact_hashes':{},'fingerprints':{}}
    start=time.perf_counter()
    try:
        case=case_override if case_override is not None else load_case(case_id)
        scheme=get_scheme(case,scheme_id);profile=profile_override if profile_override is not None else get_profile(profile_id);engine=engine_path()
        root=Path(file_root) if file_root else ROOT
        if case['case_id']!=case_id:raise ValidationError('Case binding mismatch')
        if profile.get('region') not in ('*',case['region']):raise ValidationError('碳因子地区不匹配')
        manifest['data_nature']=case['data_nature'];manifest['factor_profile_id']=profile_id
        manifest['fingerprints']=source_fingerprints(case,scheme,profile,engine,root)
        manifest['engine_version']=subprocess.check_output([str(engine),'--version'],text=True,encoding='utf-8',errors='replace',timeout=15).strip()
        manifest['engine_idd_hash']=sha(engine.parent/'Energy+.idd') if (engine.parent/'Energy+.idd').is_file() else None
        inp=rd/'input';inp.mkdir(exist_ok=True)
        shutil.copy2(relative_file(root,scheme['model']),inp/'model.idf');shutil.copy2(relative_file(root,case['weather']),inp/'weather.epw')
        if sha(inp/'model.idf')!=manifest['fingerprints']['model'] or sha(inp/'weather.epw')!=manifest['fingerprints']['weather']:raise ValidationError('Inputs changed during snapshot')
        write_json(inp/'case.json',case);write_json(inp/'carbon_profile.json',profile)
        # E+ 9.0 SQLite cannot open some Unicode paths. Use an isolated ASCII working directory.
        with tempfile.TemporaryDirectory(prefix='vra_ep_') as temp:
            tmp=Path(temp)
            if not str(tmp).isascii():raise ValidationError('EnergyPlus 9.0 requires an ASCII TEMP directory')
            shutil.copy2(inp/'model.idf',tmp/'model.idf');shutil.copy2(inp/'weather.epw',tmp/'weather.epw')
            output=tmp/'output';output.mkdir()
            command=[str(engine),'-d',str(output),'-w',str(tmp/'weather.epw'),str(tmp/'model.idf')]
            manifest['command']=command;manifest['command_note']='Temporary execution paths; archived inputs are input/model.idf and input/weather.epw.'
            try:
                with (rd/'stdout.log').open('wb') as stdout,(rd/'stderr.log').open('wb') as stderr:
                    manifest['engine_calls_executed']=1
                    cp=subprocess.run(command,cwd=tmp,stdout=stdout,stderr=stderr,timeout=timeout,check=False)
                manifest['exit_code']=cp.returncode
            except subprocess.TimeoutExpired as e:
                manifest['exit_code']=None;raise ValidationError('EnergyPlus timeout; process terminated') from e
            finally:
                shutil.copytree(output,rd/'output',dirs_exist_ok=True)
            if cp.returncode!=0:raise ValidationError('EnergyPlus exited with code '+str(cp.returncode))
        err=rd/'output/eplusout.err'
        if not err.is_file():raise ValidationError('Missing ERR')
        text=err.read_text(encoding='utf-8',errors='replace')
        severe=len(re.findall(r'\*\*\s*Severe\s*\*\*',text,re.I));fatal=len(re.findall(r'\*\*\s*Fatal\s*\*\*',text,re.I))
        manifest['warnings']=len(re.findall(r'\*\*\s*Warning\s*\*\*',text,re.I))
        manifest['warning_review']='pending_engineer_review' if manifest['warnings'] else 'none'
        if severe or fatal or 'EnergyPlus Completed Successfully' not in text:raise ValidationError('ERR unsuccessful or Severe/Fatal present')
        metrics=parse_sql(rd/'output/eplusout.sql')
        if source_fingerprints(case,scheme,profile,engine,root)!=manifest['fingerprints']:raise ValidationError('Inputs changed while simulation was running')
        result={**identity,'status':'succeeded','finished_at':now(),'data_nature':case['data_nature'],'scheme_name':scheme['name'],'metrics':metrics,'carbon':calculate_carbon(metrics['energy_by_carrier_kwh'],profile,case['region']),'cost':scheme.get('cost'),'limitations':case['notes'],'warnings_count':manifest['warnings'],'geometry_status':case['geometry_status'],'ccer':{'status':'not_assessed','issued_credits_t':None,'reason':'参考算例无真实业主、合规历史监测及开发核证证据。'}}
        manifest['status']='succeeded'
    except Exception as e:
        manifest['status']='failed';manifest['error']={'code':type(e).__name__,'message':str(e)}
        result={**identity,'status':'failed','metrics':None,'carbon':None,'error':manifest['error']}
    manifest['finished_at']=now();manifest['elapsed_seconds']=time.perf_counter()-start
    result['finished_at']=manifest['finished_at']
    write_json(rd/'result.json',result)
    # Local integrity checks detect accidental edits/mixing, not a signature against malicious rewriting.
    for p in rd.rglob('*'):
        if p.is_file() and p.name not in {'manifest.json','task.json'}:manifest['artifact_hashes'][p.relative_to(rd).as_posix()]=sha(p)
    write_json(rd/'manifest.json',manifest)
    return result

def read_validated(rd,check_current=True):
    rd=Path(rd);manifest=read_json(rd/'manifest.json');result=read_json(rd/'result.json')
    if manifest['run_id']!=rd.name or any(result.get(k)!=manifest.get(k) for k in ['run_id','case_id','scheme_id','status']):raise ValidationError('Run binding mismatch')
    if manifest['status']!='succeeded':return result,manifest,{'changed':[],'invalid':[],'action':'failed'}
    required={'input/model.idf','input/weather.epw','input/case.json','input/carbon_profile.json','output/eplusout.sql','output/eplusout.err','result.json'}
    if not required.issubset(manifest.get('artifact_hashes',{})):raise ValidationError('Incomplete evidence manifest')
    for rel,expected in manifest['artifact_hashes'].items():
        if sha(relative_file(rd,rel))!=expected:raise ValidationError('Evidence hash mismatch: '+rel)
    plan={'changed':[],'invalid':[],'action':'reuse'}
    if check_current:
        case=load_case(manifest['case_id']);scheme=get_scheme(case,manifest['scheme_id']);profile=get_profile(manifest['factor_profile_id']);engine=engine_path()
        current=source_fingerprints(case,scheme,profile,engine)
        if manifest.get('engine_idd_hash') != (sha(engine.parent/'Energy+.idd') if (engine.parent/'Energy+.idd').is_file() else None):current['engine']='idd_changed'
        plan=invalidation(manifest['fingerprints'],current)
        if plan['changed']:
            result={**result,'status':'stale','invalidation':plan}
            if 'energy' in plan['invalid']:result['metrics']=None
            if 'operating_carbon' in plan['invalid']:result['carbon']=None
    return result,manifest,plan

def recalculate_carbon(source_dir,dest_dir,profile_id):
    source_dir=Path(source_dir);dest_dir=Path(dest_dir)
    result,manifest,plan=read_validated(source_dir)
    if result['status'] not in {'succeeded','stale'} or any(k!='factor' for k in plan['changed']):raise ValidationError('Only factor-only changes may reuse energy')
    profile=get_profile(profile_id);case=read_json(source_dir/'input/case.json')
    carbon=calculate_carbon(result['metrics']['energy_by_carrier_kwh'],profile,case['region'])
    dest_dir.mkdir(parents=True,exist_ok=False)
    for rel in manifest['artifact_hashes']:
        if rel=='result.json':continue
        target=dest_dir/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(relative_file(source_dir,rel),target)
    write_json(dest_dir/'input/carbon_profile.json',profile)
    manifest={**manifest,'run_id':dest_dir.name,'source_run_id':source_dir.name,'factor_profile_id':profile_id,'started_at':now(),'finished_at':now(),'engine_calls_executed':0,'operation':'carbon_recalculation','fingerprints':{**manifest['fingerprints'],'factor':hash_json(profile)}}
    result={**result,'run_id':dest_dir.name,'source_run_id':source_dir.name,'status':'succeeded','carbon':carbon,'started_at':manifest['started_at'],'finished_at':manifest['finished_at']}
    result.pop('invalidation',None);write_json(dest_dir/'result.json',result)
    manifest['artifact_hashes']={p.relative_to(dest_dir).as_posix():sha(p) for p in dest_dir.rglob('*') if p.is_file()}
    write_json(dest_dir/'manifest.json',manifest)
    return result

def compare_runs(run_dirs):
    if len(run_dirs)<2:raise ValidationError('Select baseline and at least one retrofit')
    records=[read_validated(p) for p in run_dirs]
    if any(r['status']!='succeeded' for r,_,_ in records):raise ValidationError('Failed/stale runs cannot be compared')
    results=[r for r,_,_ in records];manifests=[m for _,m,_ in records]
    if len({r['scheme_id'] for r in results})!=len(results):raise ValidationError('Duplicate scheme in comparison')
    bases=[r for r in results if r['scheme_id']=='baseline']
    if len(bases)!=1:raise ValidationError('Exactly one baseline required')
    base=bases[0]
    if len({r['case_id'] for r in results})!=1:raise ValidationError('Different cases cannot be compared')
    for key in ['case','weather','engine','code','factor']:
        if len({m['fingerprints'][key] for m in manifests})!=1:raise ValidationError('Comparison context differs: '+key)
    if any(abs(r['metrics']['area_m2']-base['metrics']['area_m2'])>.01 for r in results):raise ValidationError('Area mismatch')
    for r in results:
        e=base['metrics']['annual_energy_kwh'];c=base['carbon']['operating_carbon_kg'];rc=r['carbon']['operating_carbon_kg']
        r['saving_rate_pct']=(1-r['metrics']['annual_energy_kwh']/e)*100 if e>0 else None
        r['engineering_reduction_kg']=c-rc if c is not None and rc is not None else None
    return {'schema_version':'vra.compare.v2','case_id':base['case_id'],'baseline_run_id':base['run_id'],'results':results,'energy_order':[r['scheme_id'] for r in sorted(results,key=lambda r:r['metrics']['annual_energy_kwh'])],'recommendation':'仅按全年场地能耗排序，不等于综合最优；还需比较舒适度、费用、材料适用条件和工程约束。','ccer_note':'工程减排差值不是已核证或签发的CCER。'}

def cost_scenario(energy,tariffs,investment,horizon,discount):
    if not isinstance(energy,dict) or not isinstance(tariffs,dict):raise ValidationError('Energy and tariffs must be objects')
    for key,value in energy.items():number(value,key)
    investment=number(investment,'investment');horizon=number(horizon,'horizon',positive=True);discount=number(discount,'discount')
    if int(horizon)!=horizon or horizon>100 or discount>1:raise ValidationError('Horizon 1..100 integer; discount 0..1')
    missing=[k for k,v in energy.items() if v>0 and k not in tariffs]
    if missing:return {'status':'incomplete','missing':missing,'annual_energy_cost_yuan':None,'npv_total_cost_yuan':None}
    annual=sum(number(v,k)*number(tariffs.get(k,0),k+' tariff') for k,v in energy.items())
    return {'status':'scenario','annual_energy_cost_yuan':annual,'npv_total_cost_yuan':investment+sum(annual/(1+discount)**i for i in range(1,int(horizon)+1)),'investment_yuan':investment,'horizon_years':int(horizon),'discount_rate':discount,'exclusions':['maintenance','replacement','residual value','tax','carbon credit revenue'],'note':'用户输入的价格情景，不是工程报价。'}

def carbon_value_scenario(quantity_t,price,development_cost,monitoring_cost,eligibility_evidence):
    for name,v in [('quantity_t',quantity_t),('price',price),('development_cost',development_cost),('monitoring_cost',monitoring_cost)]:number(v,name)
    if not isinstance(eligibility_evidence,str) or not eligibility_evidence.strip():raise ValidationError('必须说明资格与数量依据；不能直接把工程减排量视为可签发数量')
    return {'status':'hypothetical_not_issued','gross_yuan':quantity_t*price,'net_yuan':quantity_t*price-development_cost-monitoring_cost,'eligibility_evidence':eligibility_evidence,'issued_credits_t':None,'note':'纯经济情景；不判断正式资格，不形成信用或收益承诺。'}

def evidence_gaps(items):
    if not isinstance(items,list):raise ValidationError('items must be a list')
    allowed={'measured','documented','assumed','missing'}
    gaps=[]
    for item in items:
        if not isinstance(item,dict):raise ValidationError('Evidence item must be an object')
        if item.get('status') not in allowed:raise ValidationError('Unknown evidence status')
        if not item.get('name'):raise ValidationError('Missing parameter name')
        if item['status'] in {'measured','documented'} and not item.get('source'):raise ValidationError('Measured/documented parameters require source')
        if item['status'] in {'assumed','missing'}:gaps.append({'name':item['name'],'status':item['status'],'priority':'high' if item.get('decision_sensitive') else 'review','next_action':item.get('next_action') or '补充资料或由工程师确认参数范围'})
    return {'status':'needs_confirmation' if gaps else 'documented','gaps':gaps,'note':'人工辅助资料缺口登记，尚不具备任意残图自动识别或补测最优性证明。'}
