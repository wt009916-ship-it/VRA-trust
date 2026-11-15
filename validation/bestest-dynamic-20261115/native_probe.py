"""Actual pinned engine compatibility and independent SQL observations."""
import argparse,hashlib,json,math,re,shutil,sqlite3,sys,tempfile,time
from pathlib import Path
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
BASE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from backend.execution import Policy,supervise
from backend.hourly_thermal import inspect_hourly_thermal
from backend.private_storage import private_mkdir
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,r):Path(p).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def extract(sql,zones):
    con=sqlite3.connect(sql.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        con.execute('PRAGMA trusted_schema=OFF');assert con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        envs=con.execute('SELECT EnvironmentPeriodIndex FROM EnvironmentPeriods WHERE EnvironmentType=3').fetchall();assert len(envs)==1
        values={};identity={}
        for zone in zones:
            values[zone]={}
            for key,name,unit in [('temperature','Zone Air Temperature','C'),('heating','Zone Air System Sensible Heating Rate','W'),('cooling','Zone Air System Sensible Cooling Rate','W')]:
                rows=con.execute('SELECT ReportDataDictionaryIndex,Units FROM ReportDataDictionary WHERE KeyValue=? AND Name=? AND ReportingFrequency=?',(zone,name,'Hourly')).fetchall()
                assert len(rows)==1 and rows[0][1]==unit,(zone,name,rows)
                data=con.execute('SELECT r.Value,t.Month,t.Day,t.Hour,t.Interval FROM ReportData r JOIN Time t ON r.TimeIndex=t.TimeIndex WHERE r.ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=? AND COALESCE(t.WarmupFlag,0)=0 ORDER BY t.TimeIndex',(rows[0][0],envs[0][0])).fetchall()
                assert len(data)==8760 and len({r[1:4] for r in data})==8760 and all(r[4]==60 and math.isfinite(r[0]) for r in data)
                values[zone][key]=[r[0] for r in data];identity[zone+'/'+key]={'dictionary_index':rows[0][0],'unit':unit,'samples':len(data)}
        combined={key:[sum(values[z][key][i] for z in zones) for i in range(8760)] for key in ['heating','cooling']}
        temperature=values['SUN ZONE' if 'SUN ZONE' in values else zones[0]]['temperature']
        metrics={'heating_mwh':math.fsum(combined['heating'])/1e6,'cooling_mwh':math.fsum(combined['cooling'])/1e6,
          'peak_heating_kw':max(combined['heating'])/1000,'peak_cooling_kw':max(combined['cooling'])/1000,
          'temperature_min_c':min(temperature),'temperature_max_c':max(temperature),'temperature_mean_c':math.fsum(temperature)/8760}
        return metrics,identity
    finally:con.close()
def run(selected,outname,preparation=None):
    frozen=json.loads((BASE/'reference-frozen-v2.json').read_text());out=BASE/outname;out.mkdir(exist_ok=False)
    engine=Path('F:/EnergyPlusV9-0-1/energyplus.exe');assert sha(engine)==frozen['engine_sha256']
    weather=BASE/'public-reference'/frozen['weather']['path'];assert sha(weather)==frozen['weather']['sha256']
    receipt={'reference_sha256':sha(BASE/'reference-frozen-v2.json'),'script_sha256':sha(__file__),'engine_sha256':sha(engine),'cases':[],
             'scope':'Real native engine and current parser, not actual HTTP/project acceptance or real-building validation.'}
    prepared={}
    if preparation:
        prep=json.loads((BASE/preparation).read_text());assert prep['reference_sha256']==receipt['reference_sha256']
        prepared={c['case']:c for c in prep['cases']};receipt['input_preparation_sha256']=sha(BASE/preparation)
    for case in frozen['cases']:
        if case['case'] not in selected:continue
        output=out/case['case'];output.mkdir()
        if prepared:
            item=prepared[case['case']];assert item['source_sha256']==case['source_sha256'];model=Path(item['path']);assert sha(model)==item['derived_sha256']
        else:
            model=BASE/'frozen-inputs-v2'/('Case'+case['case']+'.idf');assert sha(model)==case['derived_sha256']
        work=Path(tempfile.mkdtemp(prefix='vra-bestest-native-'));assert str(work).isascii()
        shutil.copy2(model,work/'input.idf');shutil.copy2(weather,work/'weather.epw');native=private_mkdir(work/'native');logs=private_mkdir(work/'logs')
        row={'case':case['case'],'native_workspace':str(work),'status':'not_run','model_sha256':sha(model)};begin=time.monotonic()
        try:
            row['execution']=supervise([engine,'-d',native,'-w',work/'weather.epw',work/'input.idf'],work,logs,Policy(),120,output=native)
            err=(native/'eplusout.err').read_text(errors='replace')
            row['warnings']=len(re.findall(r'\*\*\s*Warning\s*\*\*',err,re.I));row['severe_or_fatal']=len(re.findall(r'\*\*\s*(?:Severe|Fatal)\s*\*\*',err,re.I))
            assert row['severe_or_fatal']==0 and 'EnergyPlus Completed Successfully' in err,'Native severe/fatal or unsuccessful'
            metrics,identity=extract(native/'eplusout.sql',case['zones']);row['metrics']=metrics;row['native_identity']=identity
            row['comparisons']=[{**{k:m[k] for k in ('key','minimum','maximum')},'actual':metrics[m['key']],'within_range':m['minimum']<=metrics[m['key']]<=m['maximum']} for m in case['metrics']]
            parsed=inspect_hourly_thermal(native/'eplusout.sql',work/'input.idf');save(output/'current-parser.json',parsed);row['parser_status']=parsed['status'];row['parser_reason']=parsed.get('reason')
            row['status']='within_all_reference_ranges' if all(x['within_range'] for x in row['comparisons']) else 'comparative_discrepancy'
        except Exception as exc:row.update(status='failed',error=type(exc).__name__+': '+str(exc))
        row['seconds']=time.monotonic()-begin
        for name in ['eplusout.err','eplusout.end']:
            if (native/name).is_file():shutil.copy2(native/name,output/name)
        shutil.copytree(logs,output/'logs')
        row['raw_files']={p.relative_to(work).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in work.rglob('*') if p.is_file()}
        save(output/'record.json',row);receipt['cases'].append(row);save(out/'receipt.json',receipt)
        print(json.dumps({k:row.get(k) for k in ['case','status','seconds','error','warnings','parser_status','parser_reason','comparisons']},ensure_ascii=False),flush=True)
        if row['status']=='failed':break  # Do not repeat a shared format failure across17 models.
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cases',nargs='+',required=True);parser.add_argument('--output',required=True);parser.add_argument('--preparation');args=parser.parse_args();run(args.cases,args.output,args.preparation)
