"""Explicit utility intervals against native hourly energy; no calibration declaration."""
import calendar,csv,io,math,re,sqlite3,time
from contextlib import closing
from datetime import datetime,timedelta
from decimal import Decimal,InvalidOperation,localcontext
from fractions import Fraction
from pathlib import Path
from typing import Literal
from pydantic import Field,StrictFloat
from . import core,end_use
from .hourly_thermal import bounded,environment_rows,HourlyEvidenceError
from .schema import Contract

METHOD='FEMP-5.0-2024-equations-4-1-to-4-4-n-denominator'
SCALES={'kWh':Fraction(1),'Wh':Fraction(1,1000),'MWh':Fraction(1000),'GJ':Fraction(2500,9),'MJ':Fraction(5,18),'J':Fraction(1,3600000)}
RESOURCES={v for values in end_use.CARRIERS.values() for v in values}
USES={end_use.METER_USES.get(v,v) for v in end_use.USES}
LIMITATIONS=[
 '仅比较声明账期与原生模拟能量，不自动校准模型，不证明实楼预测准确性或节能合规。',
 '数据性质、计量边界、来源与时间基准须人工复核；来源确认不使参考数据变成实测。',
 '误差按账期数等权计算，分母为n；不是按天加权，不采用n−p，不把月数据按小时阈值评价。',
 '仅支持本地标准时整点、完整单年度原生计量；夏令时、净负能量及跨多年度不支持。',
 '参考日历映射只对齐月日小时，不证明同年天气、运行条件或建筑一致。',
 '阈值是使用者声明的比较目标，满足阈值不等于获得任何认证。',
]


class ComparisonInput(Contract):
    name:str=Field(min_length=2,max_length=160)
    purpose:str=Field(min_length=15,max_length=2000)
    run_id:str=Field(pattern=r'^run_[a-f0-9]{32}$')
    bill_evidence_id:str=Field(pattern=r'^evidence_[a-f0-9]{32}$')
    meter:str=Field(min_length=3,max_length=200)
    bill_nature:Literal['measured','published_reference','synthetic']
    alignment:Literal['exact_calendar','calendar_pattern']
    period_kind:Literal['calendar_month','hour','custom']
    clock_source:str=Field(min_length=10,max_length=1000)
    boundary_note:str=Field(min_length=15,max_length=2000)
    max_abs_mbe_percent:StrictFloat=Field(ge=0,le=1000000)
    max_cvrmse_percent:StrictFloat=Field(ge=0,le=1000000)
    threshold_source:str=Field(min_length=10,max_length=1000)


def local_time(raw):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:00(?::00)?)?',raw):raise core.ValidationError('Use local standard time YYYY-MM-DD or YYYY-MM-DDTHH:00; timezone and non-hour boundaries unsupported')
    try:return datetime.fromisoformat(raw)
    except ValueError:raise core.ValidationError('Invalid utility calendar date') from None


def quantity(raw):
    if len(raw)>60 or not re.fullmatch(r'[+]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',raw):raise core.ValidationError('Utility energy requires an explicit finite nonnegative decimal')
    try:d=Decimal(raw)
    except InvalidOperation:raise core.ValidationError('Invalid utility energy') from None
    if not d.is_finite() or not 0<=d<=Decimal('1e12') or len(d.as_tuple().digits)>32 or not -24<=d.as_tuple().exponent<=18:raise core.ValidationError('Utility energy outside supported magnitude/precision')
    return Fraction(d)


def parse_bill(path,resource,kind):
    path=Path(path)
    if path.suffix.lower()!='.csv' or path.stat().st_size>2*1024**2:raise core.ValidationError('Use UTF-8 utility CSV up to2 MiB')
    digest=core.sha(path)
    try:
        text=path.read_text(encoding='utf-8-sig')
        if '\0' in text:raise core.ValidationError('NUL in utility CSV')
        reader=csv.DictReader(io.StringIO(text),strict=True)
        if reader.fieldnames!=['start','end','energy','unit','carrier']:raise core.ValidationError('Utility columns must be start,end,energy,unit,carrier')
        result=[]
        for raw in reader:
            if len(result)>=8784:raise core.ValidationError('Utility interval budget exceeded')
            if None in raw or any(v is None for v in raw.values()):raise core.ValidationError('Utility CSV row width mismatch')
            row={k:v.strip() for k,v in raw.items()};start,end=local_time(row['start']),local_time(row['end'])
            if end<=start:raise core.ValidationError('Utility interval must be start-inclusive/end-exclusive and positive')
            if result and start!=result[-1]['end']:raise core.ValidationError('Utility intervals overlap, duplicate, are out of order or have a gap')
            if row['carrier']!=resource:raise core.ValidationError('Utility energy carrier does not match selected native meter')
            if row['unit'] not in SCALES:raise core.ValidationError('Unsupported energy unit; power, volume and price are not energy')
            if kind=='hour' and end-start!=timedelta(hours=1):raise core.ValidationError('Hourly comparison requires one-hour intervals')
            if kind=='calendar_month':
                expected=datetime(start.year+1,1,1) if start.month==12 else datetime(start.year,start.month+1,1)
                if start.day!=1 or start.hour or end!=expected:raise core.ValidationError('Monthly comparison requires complete calendar months')
            result.append({'line':reader.line_num,'start':start,'end':end,'raw':row,'kwh':quantity(row['energy'])*SCALES[row['unit']]})
    except (UnicodeError,csv.Error) as exc:raise core.ValidationError('Malformed utility CSV: '+str(exc)) from None
    if len(result)<2:raise core.ValidationError('At least two contiguous utility intervals required')
    if core.sha(path)!=digest:raise core.ValidationError('Utility file changed while reading')
    return result


def meter_resource(name):
    parts=name.split(':')
    if len(parts)!=2:return None
    if parts[1]=='Facility':return 'Electricity' if parts[0]=='ElectricityPurchased' else parts[0] if parts[0] in RESOURCES else None
    return parts[1] if parts[0] in USES and parts[1] in RESOURCES else None


def native_meter(run_dir,name=None):
    try:return _native_meter(Path(run_dir),name)
    except (OSError,UnicodeError,sqlite3.Error,HourlyEvidenceError,OverflowError,ValueError,IndexError,StopIteration) as exc:raise core.ValidationError('Native utility evidence unavailable: '+str(exc)) from None


def _native_meter(rd,name):
    sql=rd/'output/eplusout.sql';model=rd/'input/model.idf';weather=rd/'input/weather.epw';mtd=rd/'output/eplusout.mtd';paths=[sql,model,weather,mtd]
    if sql.stat().st_size>512*1024**2 or weather.stat().st_size>8*1024**2:raise core.ValidationError('Native utility input budget exceeded')
    hashes=[core.sha(p) for p in paths];info=end_use.model_info(model);mapping=end_use.meter_sources(mtd)
    with closing(sqlite3.connect(sql.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)) as con:
        con.row_factory=sqlite3.Row;deadline=time.monotonic()+15;con.set_progress_handler(lambda:int(time.monotonic()>deadline),10000);con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024**2);con.execute('PRAGMA trusted_schema=OFF')
        schema=bounded(con,"SELECT type,name,sql FROM sqlite_master WHERE name IN ('Simulations','EnvironmentPeriods','Time','ReportDataDictionary','ReportData')",limit=5)
        if len(schema)!=5 or any(r['type']!='table' or not re.match(r'CREATE\s+TABLE\b',r['sql'] or '',re.I) for r in schema):raise core.ValidationError('Native utility requires physical SQLite tables')
        if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise core.ValidationError('Native SQLite integrity failure')
        version,env,clock,_,_=environment_rows(con,None);years={r['Year'] for r in clock}
        if len(years)!=1 or not 1900<=next(iter(years))<=2100:raise core.ValidationError('Native utility requires one explicit supported calendar year')
        year=next(iter(years))
        if len(clock)!=(8784 if calendar.isleap(year) else 8760):raise core.ValidationError('Native year and leap-day coverage disagree')
        if any(r['Dst'] for r in clock):raise core.ValidationError('Native daylight saving time is not supported for utility interval matching')
        dictionaries=bounded(con,"SELECT * FROM ReportDataDictionary WHERE IsMeter=1 AND ReportingFrequency='Hourly'",limit=10000);meters=[];lookup={}
        for r in dictionaries:
            resource=meter_resource(r['Name'])
            if resource is None:continue
            if r['Name'].upper() in lookup:raise core.ValidationError('Duplicate native energy meter')
            if r['Units']!='J' or r['Type']!='Sum' or r['ScheduleName'] not in (None,''):raise core.ValidationError('Unsupported native meter unit or aggregation')
            trace=mapping.get(r['Name'].upper())
            if not trace:raise core.ValidationError('Native energy meter has no MTD provenance')
            lookup[r['Name'].upper()]=r;meters.append({'name':r['Name'],'resource':resource,'dictionary_index':r['ReportDataDictionaryIndex'],'native_unit':'J','reporting_frequency':'Hourly','component_sources':trace})
        chosen=None;series=None
        if name is not None:
            chosen=next((m for m in meters if m['name'].upper()==name.upper()),None)
            if chosen is None:raise core.ValidationError('Requested hourly energy meter is missing or unsupported; do not substitute an annual total')
            objects=[r.split(',',1)[0].strip().casefold() for r in re.sub(r'!.*','',model.read_text()).split(';') if r.strip()]
            if chosen['name'].upper()=='ELECTRICITY:FACILITY' and any(k.startswith(('generator:','electricloadcenter:')) for k in objects):raise core.ValidationError('Onsite generation: gross facility electricity is not purchased utility energy; select an explicit purchased meter')
            values=bounded(con,'SELECT r.TimeIndex,r.Value FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex WHERE r.ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=? AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(chosen['dictionary_index'],env['EnvironmentPeriodIndex']))
            if [r['TimeIndex'] for r in values]!=[r['TimeIndex'] for r in clock]:raise core.ValidationError('Native meter has missing, duplicate or extra hours')
            energies=[core.number(r['Value'],'native hourly energy') for r in values]
            if any(v>1e18 for v in energies):raise core.ValidationError('Native hourly energy exceeds supported magnitude')
            series=[Fraction(str(v))/3600000 for v in energies]
    with weather.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.reader(f)
        for _ in range(8):next(reader)
        weather_years={int(r[0]) for r in reader}
    if [core.sha(p) for p in paths]!=hashes:raise core.ValidationError('Native utility source changed during inspection')
    return {'version':version,'year':year,'hours':len(clock),'clock_basis':'local_standard_time','weather_years':sorted(weather_years),'weather_calendar_matches_native':weather_years=={year},'ideal_systems':info['ideal_systems'],'meters':meters,'selected_meter':chosen,'series':series,'source_hashes':dict(zip(['sql','model','weather','mtd'],hashes))}


def statistics(measured,simulated):
    n=len(measured);total=sum(measured,Fraction());errors=[s-m for s,m in zip(simulated,measured)];squared=sum((e*e for e in errors),Fraction())
    with localcontext() as ctx:
        ctx.prec=50
        dec=lambda v:Decimal(v.numerator)/Decimal(v.denominator)
        rmse=(dec(squared)/n).sqrt();mbe=None if not total else dec(sum(errors,Fraction())*100/total);cv=None if not total else rmse*100/(dec(total)/n)
        return {'method':METHOD,'interval_count':n,'denominator':n,'bill_total_kwh':float(total),'native_total_kwh':float(sum(simulated,Fraction())),'mbe_percent':None if mbe is None else float(mbe),'rmse_kwh':float(rmse),'cvrmse_percent':None if cv is None else float(cv),'not_evaluable_reason':'zero_bill_total' if not total else None}


def compare(bills,native,body):
    year=native['year'];origin=datetime(year,1,1);end=datetime(year+1,1,1);bill_year=bills[0]['start'].year;prefix=[Fraction()]
    if body.alignment=='calendar_pattern' and calendar.isleap(year)!=calendar.isleap(bill_year):raise core.ValidationError('Reference and native leap calendars do not match')
    for v in native['series']:prefix.append(prefix[-1]+v)
    result=[];actual=[];predicted=[]
    for b in bills:
        start,finish=b['start'],b['end']
        if body.alignment=='calendar_pattern':
            if start.year!=bill_year or finish.year not in (bill_year,bill_year+1) or (finish.year==bill_year+1 and finish!=datetime(bill_year+1,1,1)):raise core.ValidationError('Reference mapping supports one calendar-year pattern only')
            try:start=start.replace(year=year);finish=finish.replace(year=year+finish.year-bill_year)
            except ValueError:raise core.ValidationError('Reference and native leap calendars do not match') from None
        if not origin<=start<finish<=end:raise core.ValidationError('Utility dates are outside the native year; choose explicit reference mapping only when appropriate')
        first=int((start-origin).total_seconds()/3600);last=int((finish-origin).total_seconds()/3600);value=prefix[last]-prefix[first];actual.append(b['kwh']);predicted.append(value)
        result.append({'source_line':b['line'],'original':b['raw'],'mapped_start':start.isoformat(timespec='minutes'),'mapped_end':finish.isoformat(timespec='minutes'),'native_hour_start_index':first,'native_hour_end_exclusive_index':last,'hours':last-first,'bill_kwh':float(b['kwh']),'native_kwh':float(value),'difference_kwh':float(value-b['kwh'])})
    stats=statistics(actual,predicted)
    if not all(v is None or not isinstance(v,float) or math.isfinite(v) for v in stats.values()):raise core.ValidationError('Non-finite utility statistic')
    within=None if stats['not_evaluable_reason'] else abs(stats['mbe_percent'])<=body.max_abs_mbe_percent and stats['cvrmse_percent']<=body.max_cvrmse_percent
    reasons=[]
    if body.bill_nature!='measured':reasons.append('bill_is_reference_or_synthetic')
    if body.alignment!='exact_calendar':reasons.append('month_day_mapping_not_same_year')
    if not native['weather_calendar_matches_native']:reasons.append('weather_years_differ_from_native_calendar')
    if native['selected_meter']['resource'] in ('DistrictHeating','DistrictCooling') and native['ideal_systems']:reasons.append('ideal_system_thermal_energy_not_verified_purchase')
    return {'status':'compared_reference' if reasons else 'compared_declared_measurements','calibration_status':'not_certified_or_automatically_calibrated','rows':result,'statistics':stats,'within_declared_tolerances':within,'context_reasons':reasons,'native':{k:v for k,v in native.items() if k not in ('series','meters')},'coverage':{'compared_hours':sum(r['hours'] for r in result),'native_year_hours':native['hours'],'complete_year':sum(r['hours'] for r in result)==native['hours'],'period_kind':body.period_kind},'limitations':LIMITATIONS}
