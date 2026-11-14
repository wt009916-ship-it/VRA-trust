"""Same-model native hourly timestep sensitivity; never a convergence certificate."""
from contextlib import ExitStack,closing
import hashlib
import itertools
import math
from pathlib import Path
import re
import sqlite3
import time
from . import core,hourly_thermal as hourly,ideal_loads as ideal

STEPS=(1,2,3,4,5,6,10,12,15,20,30,60)
LIMITATIONS=[
 '只比较声明模型、环境与输出的时间步敏感性；两个数值接近不证明真值精度、一般收敛或实楼校准。',
 '时间步变化也改变原生小时平均的子步采样；差异不全等同于积分算法误差。',
 '阈值由使用者声明，不是规范限值。热负荷不是实际设备耗电或选型容量。',
 '按原生本地年月日/小时/DST对齐，不按SQL行号对齐；峰值位移为样本小时数，不是UTC时间差。',
 '温度按分区比较；显热含原生声明倍率；可选理想系统比较24项热率，不判定空气流量或未覆盖其他HVAC的稳定性。',
]


def model_identity(raw):
    if len(raw)>2*1024**2:raise core.ValidationError('Time-step model exceeds 2 MiB')
    try:text=raw.decode('utf-8')
    except UnicodeError:raise core.ValidationError('Time-step model must be UTF-8') from None
    masked=re.sub(r'!.*',lambda m:' '*len(m[0]),text)
    if not masked.rstrip().endswith(';'):raise core.ValidationError('Unterminated IDF')
    objects=[];step=None;span=None
    for m in re.finditer(r'[^;]*;',masked):
        r=[f.strip().lstrip('\ufeff') for f in m[0][:-1].split(',')]
        if not r[0]:raise core.ValidationError('Empty IDF object')
        if r[0].casefold()=='timestep':
            if step is not None or len(r)!=2 or not r[1].isdigit() or int(r[1]) not in STEPS:raise core.ValidationError('Require one explicit supported Timestep')
            step=int(r[1]);field=re.search(r'(?i)\btimestep\s*,\s*(\d+)\s*;',m[0]);span=(m.start()+field.start(1),m.start()+field.end(1));r[1]='<EXPLICIT_TIMESTEP>'
        objects.append(r)
    versions=[r for r in objects if r[0].casefold()=='version']
    if len(versions)!=1 or versions[0][1:]!=['9.0'] or step is None:raise core.ValidationError('Explicit IDF9.0 and Timestep are required')
    return {'steps_per_hour':step,'physical_fields_sha256':core.hash_json(objects),'timestep_span':span}


def derivative(raw,steps):
    if isinstance(steps,bool) or steps not in STEPS:raise core.ValidationError('Unsupported Timestep')
    before=model_identity(raw)
    if before['steps_per_hour']==steps:raise core.ValidationError('Choose a different explicit Timestep')
    text=raw.decode('utf-8');a,b=before['timestep_span'];result=(text[:a]+str(steps)+text[b:]).encode('utf-8');after=model_identity(result)
    if before['physical_fields_sha256']!=after['physical_fields_sha256']:raise core.ValidationError('Physical model changed')
    return result,{'source_sha256':hashlib.sha256(raw).hexdigest(),'derivative_sha256':hashlib.sha256(result).hexdigest(),'from_steps_per_hour':before['steps_per_hour'],'to_steps_per_hour':steps,'physical_fields_sha256':before['physical_fields_sha256']}


def source(sql,model,include_ideal,environment_index=None):
    sql,model=Path(sql),Path(model);identity=model_identity(model.read_bytes());thermal=hourly.inspect_hourly_thermal(sql,model,environment_index=environment_index)
    if thermal['status']!='calculated_model_scenario':raise core.ValidationError('Hourly source unavailable: '+thermal.get('reason','unknown'))
    plans={}
    for zone in thermal['summary']['zones']:
        for metric,locator in zone['locators'].items():plans[('zone',zone['zone_name'],metric)]={**locator,'category':'temperature' if metric=='temperature_C' else 'load'}
    ideal_receipt=None
    if include_ideal:
        ideal_receipt=ideal.inspect_ideal_loads(sql,model,environment_index=environment_index)
        if ideal_receipt['status']!='calculated_model_scenario':raise core.ValidationError('Declared ideal outputs unavailable: '+ideal_receipt.get('reason','unknown'))
        for system in ideal_receipt['summary']['systems']:
            for metric,locator in system['locators'].items():
                if metric.endswith('_W'):plans[('ideal',system['system_name'],metric)]={**locator,'category':'load'}
    return {'model':model,'sql':sql,'identity':identity,'receipt':thermal,'ideal':ideal_receipt,'plans':plans}


def series_difference(coarse,fine,stamps,category,tolerances):
    if not coarse or len(coarse)!=len(fine) or len(coarse)!=len(stamps):raise core.ValidationError('Aligned complete hourly samples required')
    errors=[abs(a-b) for a,b in zip(coarse,fine)];at=max(range(len(errors)),key=errors.__getitem__)
    temp=category=='temperature';limits=[tolerances['temperature_absolute_K'] if temp else max(tolerances['load_absolute_W'],abs(v)*tolerances['load_relative_pct']/100 if abs(v)>=tolerances['near_zero_W'] else 0) for v in fine]
    evaluated=[] if temp else [100*e/abs(v) for e,v in zip(errors,fine) if abs(v)>=tolerances['near_zero_W']]
    peak_a=max(range(len(coarse)),key=coarse.__getitem__);peak_b=max(range(len(fine)),key=fine.__getitem__)
    return {'maximum_absolute_difference':errors[at],'difference_unit':'K' if temp else 'W','maximum_difference_time':stamps[at],'coarse_at_maximum':coarse[at],'fine_at_maximum':fine[at],
            'hours_exceeding_threshold':sum(e>limit for e,limit in zip(errors,limits)),'max_relative_pct':max(evaluated) if evaluated else None,'relative_evaluable_hours':len(evaluated),
            'reference_denominator':'absolute finer-step value per hour; relative undefined below declared near-zero threshold',
            'coarse_peak':{'value':coarse[peak_a],'time':stamps[peak_a]},'fine_peak':{'value':fine[peak_b],'time':stamps[peak_b]},'peak_sample_offset_hours':peak_a-peak_b,
            'coarse_energy_kWh':None if temp else math.fsum(coarse)/1000,'fine_energy_kWh':None if temp else math.fsum(fine)/1000,
            'energy_difference_kWh':None if temp else (math.fsum(coarse)-math.fsum(fine))/1000}


def compare(sources,tolerances):
    if len(sources) not in (2,3):raise core.ValidationError('Compare two or three distinct timesteps')
    sources=sorted(sources,key=lambda s:s['identity']['steps_per_hour']);steps=[s['identity']['steps_per_hour'] for s in sources]
    if len(set(steps))!=len(steps):raise core.ValidationError('Duplicate timestep; no sensitivity comparison')
    if len({s['identity']['physical_fields_sha256'] for s in sources})!=1:raise core.ValidationError('Models differ beyond Timestep; not a numerical sensitivity study')
    keys=set(sources[0]['plans'])
    if any(set(s['plans'])!=keys for s in sources):raise core.ValidationError('Output/entity coverage differs')
    pairs=[{'coarse_steps_per_hour':steps[i],'fine_steps_per_hour':steps[j],'results':[]} for i,j in itertools.combinations(range(len(sources)),2)]
    pair_indices=list(itertools.combinations(range(len(sources)),2));aggregate=[{} for s in sources];deadline=time.monotonic()+60
    with ExitStack() as stack:
        connections=[];clocks=[];indices=[];environments=[]
        for s in sources:
            con=stack.enter_context(closing(sqlite3.connect(s['sql'].resolve().as_uri()+'?mode=ro',uri=True,timeout=2)));con.row_factory=sqlite3.Row
            con.set_progress_handler(lambda:int(time.monotonic()>deadline),10000);con.execute('PRAGMA trusted_schema=OFF');con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024**2)
            _,env,_,mapping,times=hourly.environment_rows(con,s['receipt']['summary']['environment']['EnvironmentPeriodIndex'])
            clocks.append([{k:v for k,v in t.items() if k!='time_index'} for t in times]);indices.append(list(mapping));environments.append((env['EnvironmentName'],env['EnvironmentType']));connections.append(con)
        if any(c!=clocks[0] for c in clocks) or len(set(environments))!=1:raise core.ValidationError('Native calendar/environment mismatch')
        def append_results(key,values,category,locators):
            for row,(i,j) in zip(pairs,pair_indices):row['results'].append({'scope':key[0],'entity':key[1],'metric':key[2],'coarse_locator':locators[i],'fine_locator':locators[j],**series_difference(values[i],values[j],clocks[0],category,tolerances)})
        for key in sorted(keys):
            values=[];locators=[]
            for index,(s,con) in enumerate(zip(sources,connections)):
                loc=s['plans'][key];did=loc['dictionary_index'];env_id=s['receipt']['summary']['environment']['EnvironmentPeriodIndex']
                rows=hourly.bounded(con,'SELECT r.TimeIndex,r.Value FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex WHERE r.ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=? AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(did,env_id))
                if [r['TimeIndex'] for r in rows]!=indices[index]:raise core.ValidationError('Hourly source changed or incomplete')
                low,high=(-100,150) if loc['category']=='temperature' else (0,1e12)
                data=[hourly.finite(r['Value'],'native value',low,high)*loc['scale_applied'] for r in rows];values.append(data);locators.append(loc)
                if loc['category']=='load':
                    group=(key[0],key[2]);old=aggregate[index].setdefault(group,[0.]*len(data));aggregate[index][group]=[a+b for a,b in zip(old,data)]
            append_results(key,values,sources[0]['plans'][key]['category'],locators)
        for scope,metric in sorted(aggregate[0]):append_results((scope+'_aggregate','covered_entities_same_hour',metric),[a[(scope,metric)] for a in aggregate],'load',[{'operation':'sum_same_hour','scope':scope} for s in sources])
    for s in sources:
        if core.sha(s['sql'])!=s['receipt']['sql_sha256'] or core.sha(s['model'])!=s['receipt']['model_sha256']:raise core.ValidationError('Source changed during comparison')
    for row in pairs:row['verdict']='exceeds_declared_threshold' if any(r['hours_exceeding_threshold'] for r in row['results']) else 'within_declared_threshold'
    return {'verdict':'exceeds_declared_threshold' if any(r['verdict']=='exceeds_declared_threshold' for r in pairs) else 'within_declared_threshold','hours':len(clocks[0]),'environment':{'name':environments[0][0],'type':environments[0][1]},'steps_per_hour':steps,'pairs':pairs,'limitations':LIMITATIONS,'threshold_rule':'temperature <= declared K; load <= max(declared W, abs(finer hourly W)*declared pct), relative disabled below near_zero_W'}