"""Freeze independent utility intervals and native calendar reference cases before implementation."""
import argparse,calendar,csv,hashlib,json,re,sqlite3,sys
from datetime import datetime,timedelta
from decimal import Decimal,localcontext
from fractions import Fraction as F
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import core
from backend.execution import Policy,supervise
ELECTRIC=[900,1100,1000,1300,1600,1800,2100,1700,1450,1200,900,850]
GAS=[3200,2800,2100,1400,700,300,180,240,600,1300,2200,2900]


def rows(text):return [[v.strip() for v in r.split(',')] for r in re.sub(r'!.*','',text).split(';') if r.strip()]
def emit(data):return '! Synthetic interval reference; not a measured building.\n'+'\n'.join(','.join(map(str,r))+';' for r in data)+'\n'
def statistics(actual,predicted):
    # Independent exact fractions; no product statistics module is imported.
    errors=[F(s)-F(m) for m,s in zip(actual,predicted)];n=len(errors);total=sum(map(F,actual));squared=sum(e*e for e in errors)
    with localcontext() as ctx:
        ctx.prec=60
        decimal=lambda x:Decimal(x.numerator)/Decimal(x.denominator)
        rmse=decimal(squared/n).sqrt()
        return {'mbe_pct':str(decimal(100*sum(errors)/total)) if total else None,'rmse_kwh':str(rmse),'cvrmse_pct':str(100*rmse/decimal(total/n)) if total else None,'n':n}


def freeze(dest,public_projection):
    dest.mkdir(parents=True,exist_ok=False);base=json.loads((ROOT/'fixtures/test/native_zone_sizing_projection.json').read_text())['model_idf'];weather=(ROOT/'fixtures/demo/reference_5zone/weather.epw').read_text().splitlines();cases=[]
    for year,dst in [(2019,False),(2020,False),(2019,True)]:
        ident=str(year)+('-dst' if dst else '');work=dest/ident;work.mkdir();data=[]
        for r in rows(base):
            k=r[0].casefold()
            if k.startswith(('output:','sizing:','sizingperiod:','zonehvac:','zonecontrol:','thermostatsetpoint:','runperiod')) or k=='designspecification:outdoorair':continue
            if k=='simulationcontrol':r=['SimulationControl','No','No','No','No','Yes']
            if k=='buildingsurface:detailed':r[5:7]=['Adiabatic','']
            data.append(r)
        weekday=calendar.day_name[datetime(year,1,1).weekday()]
        data.append(['RunPeriod','Declared calendar',1,1,year,12,31,year,weekday,'No','Yes' if dst else 'No','No','Yes','Yes'])
        if dst:data.append(['RunPeriodControl:DaylightSavingTime','3/10','11/3'])
        for name,powers in [('ElectricProfile',ELECTRIC),('GasProfile',GAS)]:
            schedule=['Schedule:Compact',name,'Any']
            for month,power in enumerate(powers,1):schedule.extend(['Through:'+str(month)+'/'+str(calendar.monthrange(year,month)[1]),'For:AllDays','Until:24:00',str(F(power,5000).numerator/F(power,5000).denominator)])
            data.append(schedule)
        data.extend([['ElectricEquipment','Metered electric','Box','ElectricProfile','EquipmentLevel',5000,'','',0,0,1],['GasEquipment','Metered gas','Box','GasProfile','EquipmentLevel',5000,'','',0,0,1],['Output:SQLite','SimpleAndTabular'],['Output:Table:SummaryReports','AnnualBuildingUtilityPerformanceSummary'],['Output:Meter','*','Hourly']])
        (work/'model.idf').write_bytes(emit(data).encode('ascii'))
        header=weather[:8];header[0]='LOCATION,Synthetic utility calendar,NA,NA,Synthetic,000000,0,0,0,0';header[4]='HOLIDAYS/DAYLIGHT SAVINGS,'+('Yes' if calendar.isleap(year) else 'No')+',0,0,0';header[7]='DATA PERIODS,1,1,Data,'+weekday+',1/1,12/31'
        byday={}
        for line in weather[8:]:
            r=line.split(',');byday.setdefault((int(r[1]),int(r[2])),[]).append(r)
        out=list(header);at=datetime(year,1,1)
        while at.year==year:
            source=byday.get((at.month,at.day),byday[(2,28)])
            for row in source:
                r=list(row);r[0:3]=[str(year),str(at.month),str(at.day)];r[6:10]=['20','-12','10','101325'];r[12]='300'
                for i in range(13,22):r[i]='0'
                out.append(','.join(r))
            at+=timedelta(days=1)
        (work/'weather.epw').write_bytes(('\n'.join(out)+'\n').encode('ascii'))
        monthly=[]
        for month in range(1,13):
            start=datetime(year,month,1);end=datetime(year+1,1,1) if month==12 else datetime(year,month+1,1);hours=int((end-start).total_seconds()/3600)
            monthly.append({'start':start.isoformat(timespec='minutes'),'end':end.isoformat(timespec='minutes'),'hours':hours,'electricity_kwh':str(F(ELECTRIC[month-1]*hours,1000)),'gas_kwh':str(F(GAS[month-1]*hours,1000))})
        if not dst:
            for variant in ('matched','bias','cancellation','zero','gap','duplicate','power_unit','wrong_carrier','wrong_year'):
                path=work/(variant+'.csv');bill=[]
                for i,m in enumerate(monthly):
                    native=F(m['electricity_kwh']);value=native
                    if variant=='bias':value=native*F(10,11)
                    if variant=='cancellation':value=native+(F(90) if i%2 else F(-90))
                    if variant=='zero':value=F(0)
                    start,end=m['start'],m['end']
                    if variant=='wrong_year':start=start.replace(str(year),str(year+2),1);end=end.replace(str(year+1) if i==11 else str(year),str(year+3) if i==11 else str(year+2),1)
                    bill.append([start,end,str(float(value)),'kW' if variant=='power_unit' else 'kWh','Gas' if variant=='wrong_carrier' else 'Electricity'])
                if variant=='gap':bill.pop(4)
                if variant=='duplicate':bill.insert(3,bill[2])
                with path.open('w',encoding='utf8',newline='') as f:
                    w=csv.writer(f,lineterminator='\n');w.writerow(['start','end','energy','unit','carrier']);w.writerows(bill)
                if variant in ('matched','bias','cancellation','zero'):
                    expected=statistics([x[2] for x in bill],[m['electricity_kwh'] for m in monthly]);(work/(variant+'-expected.json')).write_text(json.dumps(expected,indent=2)+'\n')
        cases.append({'id':ident,'year':year,'dst_expected':dst,'model_sha256':core.sha(work/'model.idf'),'weather_sha256':core.sha(work/'weather.epw'),'monthly_expected':monthly,'hourly_absolute_kwh_tolerance':'0.00000001','scope':'Independent declared schedules, equipment energy entirely lost outside thermal zone; no equipment performance or building calibration assertion.'})
    # Official numerical facts retain worksheet/row locators; no native result is fabricated.
    public=json.loads(public_projection.read_text());sh='Utility Data-Cooling Cases';values=public['sheets'][sh][6:18];actual=[str(row[3]) for row in values];predicted=[str(F(v)*F(11,10)) for v in actual]
    (dest/'public-monthly-reference.json').write_text(json.dumps({'data_nature':'published_synthetic_reference','source_url':'https://docs.nlr.gov/docs/fy11osti/52414-01.zip','source_member':public['source_member'],'worksheet':sh,'cells':['D'+str(i) for i in range(7,19)],'raw_kwh':actual,'comparison_reference_not_native':predicted,'expected':statistics(actual,predicted),'exclusion':'The repeated January at source row19 is the following year; this test explicitly selects the first12 monthly rows. Original 3.1 IDF cannot be called a verified9.0 model; no conversion assumed.'},indent=2)+'\n')
    core.write_json(dest/'frozen.json',{'script_sha256':core.sha(Path(__file__)),'cases':cases,'method':'Before execution: E_month=P_month*hours/1000, rates independent of output; statistics use exact fraction errors and Decimal sqrt. CSV conversion is included before freezing expected metrics.','files':{p.relative_to(dest).as_posix():core.sha(p) for p in dest.rglob('*') if p.is_file()}})
    print('Frozen',core.sha(dest/'frozen.json'))


def run(inputs,out):
    out.mkdir(parents=True,exist_ok=False);f=core.read_json(inputs/'frozen.json');assert f['script_sha256']==core.sha(Path(__file__))
    for name,digest in f['files'].items():assert core.sha(inputs/name)==digest
    receipt={'cases':[],'frozen_sha256':core.sha(inputs/'frozen.json'),'engine_sha256':core.sha(core.engine_path())}
    for c in f['cases']:
        work=out/c['id'];work.mkdir();record={'id':c['id']}
        try:
            native=work/'output';native.mkdir();record['execution']=supervise([core.engine_path(),'-w',inputs/c['id']/'weather.epw','-d',native,inputs/c['id']/'model.idf'],work,work/'logs',Policy(),120,output=native)
            err=(native/'eplusout.err').read_text();assert not re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*',err,re.I),'Native severe/fatal'
            with sqlite3.connect(native/'eplusout.sql') as con:
                con.row_factory=sqlite3.Row;clock=[dict(r) for r in con.execute('SELECT * FROM Time WHERE IntervalType=1 ORDER BY TimeIndex')];checks=[];series={}
                assert len(clock)==(8784 if calendar.isleap(c['year']) else 8760)
                assert {r['Year'] for r in clock}=={c['year']};assert any(r['Dst'] for r in clock)==c['dst_expected']
                for resource,key in [('Electricity','electricity_kwh'),('Gas','gas_kwh')]:
                    ds=con.execute("SELECT * FROM ReportDataDictionary WHERE Name=? AND ReportingFrequency='Hourly'",(resource+':Facility',)).fetchall();assert len(ds)==1 and ds[0]['Units']=='J';d=dict(ds[0]);data=[dict(r) for r in con.execute('SELECT r.Value,t.Month,t.TimeIndex FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex WHERE r.ReportDataDictionaryIndex=? ORDER BY t.TimeIndex',(d['ReportDataDictionaryIndex'],))];assert len(data)==len(clock)
                    for month,m in enumerate(c['monthly_expected'],1):
                        actual=sum(F(str(x['Value'])) for x in data if x['Month']==month)/3600000;want=F(m[key]);error=abs(actual-want);checks.append({'meter':resource+':Facility','month':month,'expected_kwh':str(want),'actual_kwh':float(actual),'absolute_error_kwh':float(error),'passed':error<=F('0.00000001')})
                    series[resource]={'dictionary':d,'values':data}
                assert all(x['passed'] for x in checks),'Monthly energy mismatch'
                projection={'model_idf':(inputs/c['id']/'model.idf').read_text(),'mtd':(native/'eplusout.mtd').read_text(),'sql_sha256':core.sha(native/'eplusout.sql'),'clock':clock,'series':series}
                core.write_json(work/'projection.json',projection)
                record.update(status='passed',hours=len(clock),years=sorted({x['Year'] for x in clock}),dst_hours=sum(bool(x['Dst']) for x in clock),checks=checks,sql_sha256=projection['sql_sha256'])
        except Exception as exc:record.update(status='failed',error=type(exc).__name__+': '+str(exc))
        core.write_json(work/'record.json',record);receipt['cases'].append(record);core.write_json(out/'receipt.json',receipt);print(c['id'],record['status'],record.get('error'),flush=True)
    receipt['all_passed']=all(c['status']=='passed' for c in receipt['cases']);core.write_json(out/'receipt.json',receipt)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',type=Path);p.add_argument('--public-projection',type=Path);p.add_argument('--inputs',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.freeze:freeze(a.freeze.resolve(),a.public_projection)
    elif a.inputs and a.output:run(a.inputs.resolve(),a.output.resolve())
    else:p.error('freeze inputs or execute retained inputs')
