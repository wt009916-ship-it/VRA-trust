"""Source-bound native ideal HVAC heat/moisture-related delivery, not electricity.

9.0.1 PurchasedAirManager rates/flows ALREADY include zone/list multipliers.
This differs from Zone Air System Sensible rates; never reuse their scaling.
"""
from contextlib import closing
import math
from pathlib import Path
import re
import sqlite3
import time

from .core import sha
from .hourly_thermal import HourlyEvidenceError, bounded, environment_rows, finite, integer, model_zones

POLICY='native-ideal-load-boundaries-9.0.1-v1'
MAX_SYSTEMS=64
GROUPS={'zone':'Zone','supply':'Supply Air','outdoor':'Outdoor Air','recovery':'Heat Recovery'}
VARIABLES={f'{group}_{part}_{mode}_W':(f'Zone Ideal Loads {label} {part.title()} {mode.title()} Rate','W')
           for group,label in GROUPS.items() for mode in ('heating','cooling') for part in ('sensible','latent','total')}
VARIABLES.update(outdoor_mass_kg_s=('Zone Ideal Loads Outdoor Air Mass Flow Rate','kg/s'),
                 supply_mass_kg_s=('Zone Ideal Loads Supply Air Mass Flow Rate','kg/s'))
LIMITATIONS=[
    '仅覆盖模型明确连接的理想空调系统；区内交付、供风处理、新风和热回收是不同边界，不能相加冒充全楼总耗能。',
    '原生负荷与流量已经包含分区及分组倍率，本工具不再次相乘；温度、湿度也不能按倍率放大。',
    '单位为逐时平均W、期间kWh热量和kg/s空气流量；不是耗电、实际设备容量、当地规范设计或实楼校准。',
    '新风方向负荷受原生运行状态和正负截断影响；零值不证明全天无新风负荷，分项之间不强制伪造一般能量守恒。',
    '显热/潜热按原生焓口径分解；潜热交付不一定等于输入散湿功率。不同边界的单项峰值也可能不同时发生。',
    '每个环境全部小时及全部声明理想系统必须完整；缺变量或单位/绑定错误不填零，不自动替代为仅显热。',
]


class NoIdealSystem(HourlyEvidenceError):
    pass


def model_systems(path):
    zones=model_zones(path)
    text=re.sub(r'!.*','',Path(path).read_text(encoding='utf-8-sig'))
    objects=[[f.strip() for f in part.split(',')] for part in text.split(';') if part.strip()]
    if len(objects)>100000:raise HourlyEvidenceError('IDF object budget exceeded')
    def named(kind):
        result={}
        for row in objects:
            if row[0].casefold()!=kind:continue
            if len(row)<2 or not row[1] or row[1].upper() in result:raise HourlyEvidenceError('Missing/duplicate '+kind+' name')
            result[row[1].upper()]=row
        return result
    ideal=named('zonehvac:idealloadsairsystem')
    if not ideal:raise NoIdealSystem('Model contains no declared ideal loads air systems')
    if len(ideal)>MAX_SYSTEMS:raise HourlyEvidenceError('Ideal system budget exceeded')
    lists=named('zonehvac:equipmentlist');connections=named('zonehvac:equipmentconnections');nodes=named('nodelist')
    mapped={};other=[];used_lists=set();supply_owners=set()
    for zone,connection in connections.items():
        if zone not in zones or len(connection)<6:raise HourlyEvidenceError('Invalid zone equipment connection')
        list_name=connection[2].upper()
        if list_name in used_lists or list_name not in lists:raise HourlyEvidenceError('Missing/shared zone equipment list')
        used_lists.add(list_name);equipment=lists[list_name]
        if len(equipment)<7 or (len(equipment)-3)%4:raise HourlyEvidenceError('Unsupported equipment list fields')
        inlet=connection[3].upper();inlets={n.upper() for n in nodes[inlet][2:]} if inlet in nodes else {inlet}
        if not inlet or '' in inlets:raise HourlyEvidenceError('Missing zone supply inlet')
        for at in range(3,len(equipment),4):
            kind,name=equipment[at].casefold(),equipment[at+1].upper()
            if kind!='zonehvac:idealloadsairsystem':
                other.append({'zone_name':zone,'type':equipment[at],'name':name});continue
            if name not in ideal or name in mapped:raise HourlyEvidenceError('Missing/ambiguous ideal system mapping')
            row=ideal[name]
            if len(row)<4 or row[3].upper() not in inlets:raise HourlyEvidenceError('Ideal supply node does not match its zone')
            supply=row[3].upper()
            if supply in supply_owners:raise HourlyEvidenceError('Ideal systems share an ambiguous supply node')
            supply_owners.add(supply)
            field=lambda index,default:row[index] if len(row)>index and row[index] else default
            mapped[name]={'system_name':name,'zone_name':zone,'equipment_list_name':list_name,'supply_node':row[3],
                          'dehumidification_control':field(18,'ConstantSensibleHeatRatio'),'humidification_control':field(20,'None'),
                          'outdoor_air_specification':field(21,None),'heat_recovery_type':field(25,'None')}
    if set(mapped)!=set(ideal):raise HourlyEvidenceError('Every ideal system must bind to exactly one declared zone')
    return zones,mapped,other


def _read(con,basis,environment_index):
    names,mapped,other=basis
    sql_version,env,clocks,clock_map,stamps=environment_rows(con,environment_index);env_id=env['EnvironmentPeriodIndex']
    zones=bounded(con,'SELECT ZoneName,Multiplier,ListMultiplier FROM Zones',limit=64)
    if len(zones)!=len(names) or any(not isinstance(r['ZoneName'],str) for r in zones) or {r['ZoneName'].upper() for r in zones}!=names:
        raise HourlyEvidenceError('Native/model zone coverage mismatch')
    scales={r['ZoneName'].upper():(finite(r['Multiplier'],'zone multiplier',1,1e6),finite(r['ListMultiplier'],'list multiplier',1,1e6)) for r in zones}
    placeholders=','.join('?' for _ in VARIABLES)
    dictionary=bounded(con,'SELECT * FROM ReportDataDictionary WHERE Name IN ('+placeholders+') AND ReportingFrequency=?',tuple(v[0] for v in VARIABLES.values())+('Hourly',),limit=MAX_SYSTEMS*len(VARIABLES))
    lookup={}
    for row in dictionary:
        key=(row['KeyValue'],row['Name'])
        if key in lookup or row['KeyValue'] not in mapped:raise HourlyEvidenceError('Duplicate/unbound ideal output dictionary')
        lookup[key]=row
    if len(lookup)!=len(mapped)*len(VARIABLES):raise HourlyEvidenceError('Missing ideal hourly rate/flow outputs; request explicit diagnostic variables in a new model')
    aggregate={k:[0.]*len(clocks) for k in VARIABLES};systems=[]
    def peak(values,unit):
        at=max(range(len(values)),key=values.__getitem__)
        return {'value':values[at],'unit':unit,'time':stamps[at],'first_of_ties':True}
    def summaries(values):
        return {k:{'peak':peak(v,VARIABLES[k][1]),**({'energy_kWh':math.fsum(v)/1000} if k.endswith('_W') else {'air_mass_kg':math.fsum(v)*3600})} for k,v in values.items()}
    for name,system in sorted(mapped.items()):
        values={};locators={}
        for key,(variable,unit) in VARIABLES.items():
            d=lookup[(name,variable)]
            if (d['IsMeter'],d['Type'],d['IndexGroup'],d['TimestepType'],d['Units'])!=(0,'Avg','System','Zone',unit) or d['ScheduleName'] not in (None,''):
                raise HourlyEvidenceError('Unsupported ideal output semantics or unit')
            did=integer(d['ReportDataDictionaryIndex'],'dictionary index',1,2**31-1)
            data=bounded(con,'SELECT r.TimeIndex,r.Value FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex WHERE r.ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=? AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(did,env_id))
            if len(data)!=len(clocks) or [r['TimeIndex'] for r in data]!=list(clock_map):raise HourlyEvidenceError('Missing/duplicate/extra ideal hourly samples')
            values[key]=[finite(r['Value'],variable,0,1e12 if unit=='W' else 1e8) for r in data]
            locators[key]={'dictionary_index':did,'variable':variable,'key_value':name,'unit':unit,'native_includes_zone_and_list_multipliers':True,'scale_applied':1}
            aggregate[key]=[a+b for a,b in zip(aggregate[key],values[key])]
        for group in GROUPS:
            for mode in ('heating','cooling'):
                for sensible,latent,total in zip(*(values[f'{group}_{part}_{mode}_W'] for part in ('sensible','latent','total'))):
                    if not math.isclose(sensible+latent,total,rel_tol=1e-8,abs_tol=1e-4):raise HourlyEvidenceError('Native total differs from sensible plus latent')
        a,b=scales[system['zone_name']]
        systems.append({**system,'zone_multiplier':a,'zone_list_multiplier':b,'results':summaries(values),'locators':locators})
    totals=summaries(aggregate);profiles=[]
    for mode in ('heating','cooling'):
        at=clock_map[totals[f'supply_total_{mode}_W']['peak']['time']['time_index']];start=at//24*24
        profiles.append({'selected_for':'covered_systems_supply_total_'+mode+'_peak','times':stamps[start:start+24],'covered_systems':{k:v[start:start+24] for k,v in aggregate.items()}})
    covered={v['zone_name'] for v in mapped.values()}
    return {'engine_sql_version':sql_version,'environment':dict(env),'hour_count':len(clocks),'systems':systems,
            'coverage':{'scope':'declared_ideal_systems_only','ideal_system_count':len(mapped),'model_zone_count':len(names),'covered_zones':sorted(covered),'uncovered_zones':sorted(names-covered),'other_equipment':other},
            'aggregate':totals,'peak_day_profiles':profiles,'aggregation':'same_hour_sum_of_covered_ideal_systems_no_extra_multiplier'}


def inspect_ideal_loads(sql_path,model_path,*,environment_index=None):
    sql_path,model_path=Path(sql_path),Path(model_path)
    receipt={'status':'unavailable','policy_version':POLICY,'parser_sha256':sha(Path(__file__)),
             'clock_parser_sha256':sha(Path(__file__).with_name('hourly_thermal.py')),
             'model_sha256':sha(model_path),'sql_sha256':sha(sql_path),'summary':None,'limitations':list(LIMITATIONS)}
    try:
        if sql_path.stat().st_size>512*1024**2:raise HourlyEvidenceError('Native SQL exceeds inspection budget')
        basis=model_systems(model_path)
        with closing(sqlite3.connect(sql_path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)) as con:
            con.row_factory=sqlite3.Row;deadline=time.monotonic()+30
            con.set_progress_handler(lambda:int(time.monotonic()>deadline),10000);con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024**2);con.execute('PRAGMA trusted_schema=OFF')
            schema=bounded(con,"SELECT type,name,sql FROM sqlite_master WHERE name IN ('Simulations','EnvironmentPeriods','Time','Zones','ReportDataDictionary','ReportData')",limit=6)
            if len(schema)!=6 or any(r['type']!='table' or not re.match(r'CREATE\s+TABLE\b',r['sql'] or '',re.I) for r in schema):raise HourlyEvidenceError('Expected native physical tables')
            if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise HourlyEvidenceError('Native SQL integrity failure')
            summary=_read(con,basis,environment_index)
        if sha(model_path)!=receipt['model_sha256'] or sha(sql_path)!=receipt['sql_sha256']:raise HourlyEvidenceError('Ideal source changed during inspection')
        receipt.update(status='calculated_model_scenario',summary=summary)
    except NoIdealSystem as exc:receipt.update(status='not_applicable',reason=str(exc))
    except (HourlyEvidenceError,sqlite3.Error,UnicodeError,KeyError,IndexError) as exc:receipt['reason']=str(exc)
    return receipt


def diagnostic_model(raw):
    """Append explicit hourly output requests; the original byte prefix is untouched."""
    if len(raw)>2*1024**2:raise HourlyEvidenceError('Diagnostic source exceeds 2 MiB')
    text=re.sub(r'!.*','',raw.decode('utf-8-sig'))
    if not text.rstrip().endswith(';'):raise HourlyEvidenceError('Unterminated IDF source')
    objects=[[f.strip() for f in part.split(',')] for part in text.split(';') if part.strip()]
    versions=[r for r in objects if r[0].casefold()=='version']
    if versions!=[['Version','9.0']] and not (len(versions)==1 and len(versions[0])==2 and versions[0][1]=='9.0'):
        raise HourlyEvidenceError('Only explicit IDF 9.0 output configuration is supported')
    sqlite=[r for r in objects if r[0].casefold()=='output:sqlite']
    if len(sqlite)!=1 or len(sqlite[0])<2 or sqlite[0][1].casefold()!='simpleandtabular':
        raise HourlyEvidenceError('Source must request one SimpleAndTabular SQLite output')
    requested=[]
    for variable,_unit in VARIABLES.values():
        matches=[r for r in objects if r[0].casefold()=='output:variable' and len(r)>=4 and r[2].casefold()==variable.casefold() and r[3].casefold()=='hourly']
        if matches and (len(matches)!=1 or matches[0][1]!='*' or any(matches[0][4:])):
            raise HourlyEvidenceError('Existing partial/conditional diagnostic request requires model-author review: '+variable)
        if not matches:requested.append('Output:Variable,*,'+variable+',Hourly;')
    import hashlib
    header='\n! VRA hourly ideal-load diagnostics; source SHA256 '+hashlib.sha256(raw).hexdigest()+'\n! Output requests only; not a calibrated or approved building model.\n'
    return raw+header.encode('ascii')+('\n'.join(requested)+'\n').encode('ascii'),len(requested)


def register_diagnostics(app,domain):
    from fastapi import Query, Response
    from . import core

    @app.get('/api/projects/{project_id}/files/{file_id}/ideal-load-output.idf')
    def download(project_id:str,file_id:str,expected_source_hash:str=Query(pattern=r'^[a-f0-9]{64}$')):
        record,path=domain.file_record(project_id,file_id)
        if record['hash']!=expected_source_hash or path.suffix.lower()!='.idf':
            raise core.ValidationError('Model source changed or is not IDF; refresh the source record')
        if record['size']>2*1024**2:raise core.ValidationError('Diagnostic source exceeds 2 MiB')
        try:
            model_systems(path)
            raw=path.read_bytes();derived,count=diagnostic_model(raw)
        except (HourlyEvidenceError,UnicodeError) as exc:raise core.ValidationError(str(exc)) from None
        import hashlib
        if hashlib.sha256(raw).hexdigest()!=record['hash'] or core.sha(path)!=record['hash']:
            raise core.ValidationError('Model changed while creating output configuration')
        return Response(derived,media_type='application/octet-stream',headers={
            'Content-Disposition':'attachment; filename="ideal-diagnostics-'+record['hash'][:12]+'.idf"',
            'X-Content-Type-Options':'nosniff','X-VRA-Source-SHA256':record['hash'],
            'X-VRA-Derivative-SHA256':hashlib.sha256(derived).hexdigest(),'X-VRA-Added-Output-Requests':str(count),
            'Cache-Control':'no-store'})
