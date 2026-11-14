"""Pinned native end-use ledger with rounded table and optional hourly meter checks."""
from contextlib import closing
from decimal import Decimal, InvalidOperation
import fnmatch
import math
from pathlib import Path
import re
import sqlite3
from . import core
from .hourly_thermal import bounded, environment_rows, HourlyEvidenceError

POLICY='native-end-use-9.0.1-v1'
USES={'Heating':'供暖','Cooling':'制冷','Interior Lighting':'室内照明','Exterior Lighting':'室外照明','Interior Equipment':'室内设备','Exterior Equipment':'室外设备','Fans':'风机','Pumps':'水泵','Heat Rejection':'散热设备','Humidification':'加湿','Heat Recovery':'热回收','Water Systems':'生活热水/用水系统','Refrigeration':'冷冻冷藏','Generators':'发电辅助耗能'}
METER_USES={'Interior Lighting':'InteriorLights','Exterior Lighting':'ExteriorLights','Interior Equipment':'InteriorEquipment','Exterior Equipment':'ExteriorEquipment','Heat Rejection':'HeatRejection','Humidification':'Humidifier','Heat Recovery':'HeatRecovery','Water Systems':'WaterSystems','Generators':'Cogeneration'}
CARRIERS={'Electricity':('Electricity',),'Natural Gas':('Gas',),'Additional Fuel':('FuelOil#1','FuelOil#2','Gasoline','Coal','Propane','Diesel','OtherFuel1','OtherFuel2'),'District Cooling':('DistrictCooling',),'District Heating':('DistrictHeating','Steam')}
SCALES={'kWh':Decimal(1),'GJ':Decimal(1000)/Decimal('3.6'),'MJ':Decimal(1)/Decimal('3.6'),'J':Decimal(1)/Decimal(3600000)}
LIMITATIONS=[
 '原生模拟的用途分项，不是实测能耗、设备选型或合规结论。电、燃气及区域冷热量分别保留，不能统称耗电。',
 '理想系统可能计入区域供热/供冷；有理想系统时不能把该载体当成真实采购量或按猜测COP换成电耗。',
 '表格按原生显示精度舍入，零表示表格舍入为零；完整逐时计量可用时单独显示积分，缺计量不补零。',
 'MTD映射列出计量归属的原生变量，不提供每台设备的独立用量分摊；一个总表及其子表不能重复相加。',
 '仅支持9.0.1、完整单年度和载体与场地总量可核对的运行；不扩展现有核心对现场发电/净购电口径的支持。',
]


def model_info(path):
    if path.stat().st_size>2*1024**2:raise core.ValidationError('End-use model exceeds 2 MiB')
    text=path.read_text(encoding='utf-8-sig');data=[[v.strip() for v in r.split(',')] for r in re.sub(r'!.*','',text).split(';') if r.strip()]
    ideal=[r[1] for r in data if r[0].casefold()=='zonehvac:idealloadsairsystem' and len(r)>1]
    requested=[r[1].upper() for r in data if len(r)>=3 and r[0].casefold()=='output:meter' and r[2].casefold()=='hourly']
    return {'ideal_systems':ideal,'requested_hourly_meters':requested}


def meter_sources(path):
    if path is None:return None
    if path.stat().st_size>20*1024**2:raise core.ValidationError('Meter provenance exceeds 20 MiB')
    result={};current=None
    for number,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        m=re.fullmatch(r'\s*Meters for (\d+),(.+) \[([^]]+)\]\s*',line)
        if m:current={'native_variable_index':int(m[1]),'variable':m[2],'unit':m[3],'line':number};continue
        m=re.fullmatch(r'\s*OnMeter=(.+) \[([^]]+)\]\s*',line)
        if m:
            if current is None:raise core.ValidationError('Orphan meter provenance')
            if m[2]=='J' and current['unit']=='J':result.setdefault(m[1].upper(),[]).append(current.copy())
        elif not line.strip():current=None
        if number>300000:raise core.ValidationError('Meter provenance line budget exceeded')
    return result


def cell(rows,table,row,column):
    selected=[r for r in rows if (r['TableName'],r['RowName'],r['ColumnName'])==(table,row,column)]
    if len(selected)!=1:raise core.ValidationError('Missing/duplicate end-use cell: '+str((table,row,column)))
    r=selected[0];raw=r['Value'].strip()
    if len(raw)>40 or not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',raw) or r['Units'] not in SCALES:raise core.ValidationError('Invalid end-use number/unit')
    try:v=Decimal(raw);scale=SCALES[r['Units']];value=v*scale;half=Decimal(10)**v.as_tuple().exponent*scale/2
    except InvalidOperation:raise core.ValidationError('Invalid decimal end-use value') from None
    if not value.is_finite() or not 0<=value<=Decimal('1e12'):raise core.ValidationError('End-use value outside supported range')
    return {'kwh':float(value),'rounding_half_width_kwh':float(half),'locator':{'report':core.REPORT_NAME,'for':'Entire Facility','table':table,'row':row,'column':column,'unit':r['Units'],'raw_value':raw}}


def inspect(sql,model,mtd=None):
    try:return _inspect(sql,model,mtd)
    except (HourlyEvidenceError,sqlite3.Error,UnicodeError,OSError) as exc:
        raise core.ValidationError("End-use evidence unavailable: "+str(exc)) from None


def _inspect(sql,model,mtd=None):
    paths=[Path(sql),Path(model)]+([Path(mtd)] if mtd else []);hashes=[core.sha(x) for x in paths]
    annual=core.parse_sql(sql);info=model_info(Path(model));sources=meter_sources(Path(mtd) if mtd else None)
    with closing(sqlite3.connect(Path(sql).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        version,env,clocks,_,_=environment_rows(con,None);indices=[r['TimeIndex'] for r in clocks]
        rows=bounded(con,'SELECT TableName,RowName,ColumnName,Units,Value FROM TabularDataWithStrings WHERE ReportName=? AND ReportForString=?',(core.REPORT_NAME,'Entire Facility'),limit=10000)
        cols={r['ColumnName'] for r in rows if r['TableName']=='End Uses'}-{'Water'}
        if cols!=set(CARRIERS):raise core.ValidationError('Unsupported or missing end-use carrier columns')
        if {r['RowName'] for r in rows if r['TableName']=='End Uses'}-{'','Total End Uses'}!=set(USES):raise core.ValidationError('Unsupported or missing end-use categories')
        dictionary=bounded(con,"SELECT * FROM ReportDataDictionary WHERE IsMeter=1 AND ReportingFrequency='Hourly'",limit=10000)
        matrix=[];totals={c:cell(rows,'End Uses','Total End Uses',c) for c in CARRIERS}
        for use,label in USES.items():
            values={}
            for carrier,resources in CARRIERS.items():
                tab=cell(rows,'End Uses',use,carrier);names=[METER_USES.get(use,use)+':'+r for r in resources];trace=[];integrals=[];missing=[];present=[]
                for name in names:
                    entries=[d for d in dictionary if d['Name'].upper()==name.upper()]
                    if len(entries)>1:raise core.ValidationError('Duplicate hourly meter: '+name)
                    bindings=(sources or {}).get(name.upper(),[]);trace.extend([{'meter':name,**x} for x in bindings])
                    if not entries:
                        if bindings and any(fnmatch.fnmatchcase(name.upper(),pattern) for pattern in info['requested_hourly_meters']):raise core.ValidationError('Requested meter missing: '+name)
                        if bindings:missing.append(name)
                        continue
                    d=entries[0]
                    if sources is not None and not bindings:raise core.ValidationError('Hourly meter lacks provenance: '+name)
                    if d['Units']!='J':raise core.ValidationError('Hourly energy meter must be J')
                    values_native=bounded(con,'SELECT r.TimeIndex,r.Value FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex WHERE r.ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=? AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(d['ReportDataDictionaryIndex'],env['EnvironmentPeriodIndex']))
                    if [v['TimeIndex'] for v in values_native]!=indices:raise core.ValidationError('Missing/duplicate/reordered meter hour: '+name)
                    energy=[core.number(v['Value'],'meter energy') for v in values_native];integrals.append(math.fsum(energy)/3600000);present.append({'meter':name,'dictionary_index':d['ReportDataDictionaryIndex'],'unit':'J','hours':len(clocks)})
                # Complete registry is needed before combining multiple fuel meters.
                complete=bool(present) and not missing and sources is not None
                native=math.fsum(integrals) if complete else None
                if native is not None and abs(native-tab['kwh'])>tab['rounding_half_width_kwh']+max(1e-7,native*1e-10):raise core.ValidationError('Hourly meter/table disagreement: '+use+'/'+carrier)
                if sources is not None and not trace and tab['kwh']>tab['rounding_half_width_kwh']:raise core.ValidationError('Positive end-use lacks meter provenance: '+use+'/'+carrier)
                values[carrier]={'tabulated':tab,'hourly_meter_kwh':native,'meter_status':'checked' if complete else 'not_available','meters':present,'component_sources':trace,'source_mapping_available':sources is not None}
            matrix.append({'end_use':use,'label':label,'carriers':values})
        reconciliation=[]
        for carrier,total in totals.items():
            cells=[r['carriers'][carrier]['tabulated'] for r in matrix];summed=math.fsum(x['kwh'] for x in cells);tolerance=math.fsum(x['rounding_half_width_kwh'] for x in cells)+total['rounding_half_width_kwh']+1e-7
            if abs(summed-total['kwh'])>tolerance:raise core.ValidationError('End-use rows do not reconcile: '+carrier)
            reconciliation.append({'carrier':carrier,'rows_sum_kwh':summed,'native_total':total,'difference_kwh':summed-total['kwh'],'rounding_tolerance_kwh':tolerance})
        site=cell(rows,'Site and Source Energy','Total Site Energy','Total Energy');difference=math.fsum(x['kwh'] for x in totals.values())-site['kwh'];tolerance=math.fsum(x['rounding_half_width_kwh'] for x in totals.values())+site['rounding_half_width_kwh']+1e-7
        if abs(difference)>tolerance:raise core.ValidationError('Site total differs beyond displayed rounding precision')
    if [core.sha(x) for x in paths]!=hashes:raise core.ValidationError('Source changed during end-use inspection')
    return {'policy':POLICY,'engine_version':version,'environment':dict(env),'hours':len(clocks),'area_m2':annual['area_m2'],'rows':matrix,'carrier_totals':totals,'reconciliation':reconciliation,'site_total':site,'site_reconciliation':{'difference_kwh':difference,'rounding_tolerance_kwh':tolerance},'model':info,'source_hashes':dict(zip(['sql_sha256','model_sha256','mtd_sha256'],hashes)),'limitations':LIMITATIONS}
