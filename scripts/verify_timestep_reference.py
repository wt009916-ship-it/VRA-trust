"""New frozen timestep cases; exact nonlinear air energy balance, no native fitting."""
import argparse
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import core
from backend.execution import Policy,supervise
from backend.private_storage import private_mkdir


def oracle(boundary,gains,steps):
    ua=112/(.1+.7+.04);w=1e-5
    s=76.8*70*101325*(1004.84+1858.95*w)/(287*(1+1.6077687*w))
    k=ua/s;temp=11.
    for _ in range(200):
        start=temp;values=[]
        for ext,gain in zip(boundary,gains):
            e=ext+gain/ua+273.15;hour=[]
            for _ in range(steps):
                temp=e/(1+(e/(temp+273.15)-1)*math.exp(-k*e*3600/steps))-273.15
                hour.append(temp)
            values.append(math.fsum(hour)/steps)
        if abs(start-temp)<1e-12:return values
    raise ValueError('Independent periodic solution failed')


def model(base,boundary,gains,steps):
    rows=[[v.strip() for v in s.split(',')] for s in re.sub(r'!.*','',base).split(';') if s.strip()];out=[]
    for r in rows:
        kind=r[0].lower()
        if kind=='schedule:compact':continue
        if kind=='timestep':r[1]=str(steps)
        if kind=='material:nomass':r[3]='.7'
        if kind=='zone':r[8:11]=['3.2','76.8','24']
        if kind=='zonecapacitancemultiplier:researchspecial':r[3]='70'
        if kind=='buildingsurface:detailed':
            for i in range(11,len(r)):
                r[i]=format(float(r[i])*([.8,1.2,3.2/3][(i-11)%3]),'.15g')
        out.append(r)
    def schedule(name,values):
        row=['Schedule:Compact',name,'Any','Through:12/31','For:AllDays','Interpolate:No']
        for h,value in enumerate(values,1):row.extend([f'Until:{h:02}:00',str(value)])
        return row
    out.extend([schedule('Boundary_1',boundary),schedule('Heat pulse',gains),['OtherEquipment','Declared convective pulse','None','Box_1','Heat pulse','EquipmentLevel','1','','','0','0','0']])
    return '\n'.join(','.join(r)+';' for r in out)+'\n'


def freeze(path):
    if path.exists():raise ValueError('Preserve prior frozen inputs')
    private_mkdir(path);base=(ROOT/'validation/freefloat-thermal-20261107/native-inputs/steady/input.idf').read_text()
    scenarios=[('steady',[11]*24,[0]*24),('daily_cycle',[8]*8+[18]*6+[11]*10,[0]*24),('convective_pulse',[9]*6+[16]*12+[10]*6,[0]*8+[900]*6+[0]*10)]
    cases=[]
    for name,boundary,gains in scenarios:
        for steps in (6,12,60):
            identity=f'{name}_{steps}';d=private_mkdir(path/identity);raw=model(base,boundary,gains,steps);(d/'input.idf').write_text(raw,encoding='ascii')
            cases.append({'name':identity,'family':name,'steps_per_hour':steps,'boundary_C':boundary,'gains_W':gains,'model_sha256':core.sha(d/'input.idf'),'independent_hourly_C':oracle(boundary,gains,steps),'temperature_tolerance_K':.02})
    core.write_json(path/'frozen.json',{'script_sha256':core.sha(Path(__file__)),'scope':'New 4 x 6 x 3.2 m air-only synthetic room; six faces 112 m2, R .7 + .1 + .04, air capacitance multiplier70; dry humidity floor. End-of-timestep hourly average convention; not continuous-hour mean or field validation.','equation':'C(T)dT/dt=UA(Text-T)+Q; C(T)=S/(T+273.15); exact constant-hour nonlinear solution, periodic limit <1e-12 K. Native outputs never read by oracle.','cases':cases,'comparison_declaration':{'purpose':'reference timestep sensitivity, not a standard','temperature_absolute_K':.01,'load_absolute_W':1,'load_relative_pct':1,'near_zero_W':1}})
    print(json.dumps({'frozen_sha256':core.sha(path/'frozen.json'),'cases':len(cases)}))


def run(inputs,output):
    if output.exists():raise ValueError('Keep previous results')
    private_mkdir(output);frozen=core.read_json(inputs/'frozen.json');receipt={'frozen_sha256':core.sha(inputs/'frozen.json'),'cases':[]}
    for spec in frozen['cases']:
        work=private_mkdir(output/spec['name']);source=inputs/spec['name']/'input.idf';assert core.sha(source)==spec['model_sha256'];(work/'input.idf').write_bytes(source.read_bytes())
        r={'name':spec['name'],'status':'not_run','model_sha256':spec['model_sha256']}
        try:
            native=private_mkdir(work/'output');r['execution']=supervise([core.engine_path(),'-d',native,work/'input.idf'],work,private_mkdir(work/'logs'),Policy(),120,output=native)
            err=(native/'eplusout.err').read_text(errors='replace');assert not re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*',err,re.I),'Native severe/fatal'
            series={}
            with sqlite3.connect((native/'eplusout.sql').as_uri()+'?mode=ro',uri=True) as con:
                for key,name in [('temperature_C','Zone Air Temperature'),('humidity','Zone Air Humidity Ratio'),('heating_W','Zone Air System Sensible Heating Rate'),('cooling_W','Zone Air System Sensible Cooling Rate')]:
                    data=con.execute('SELECT t.Month,t.Day,t.Hour,r.Value FROM ReportData r JOIN ReportDataDictionary d USING(ReportDataDictionaryIndex) JOIN Time t USING(TimeIndex) WHERE d.Name=? AND d.KeyValue=? AND d.ReportingFrequency=? AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(name,'BOX_1','Hourly')).fetchall();assert len(data)==24;series[key]=[x[3] for x in data]
            error=max(abs(a-b) for a,b in zip(series['temperature_C'],spec['independent_hourly_C']));dry=max(series['humidity'])<=1e-5+1e-16;zero=max(abs(v) for k in ('heating_W','cooling_W') for v in series[k])<1e-6
            r.update(status='passed' if error<=spec['temperature_tolerance_K'] and dry and zero else 'numerical_or_premise_mismatch',maximum_error_K=error,tolerance_K=spec['temperature_tolerance_K'],dry_verified=dry,zero_HVAC_verified=zero,sql_sha256=core.sha(native/'eplusout.sql'),native_hourly=series)
        except Exception as exc:r.update(status='failed',error=type(exc).__name__+': '+str(exc))
        core.write_json(work/'receipt.json',r);receipt['cases'].append(r);core.write_json(output/'receipt.json',receipt);print(json.dumps({k:v for k,v in r.items() if k not in ('execution','native_hourly')},ensure_ascii=False),flush=True)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',type=Path);p.add_argument('--inputs',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.freeze:freeze(a.freeze.resolve())
    elif a.inputs and a.output:run(a.inputs.resolve(),a.output.resolve())
    else:p.error('Use --freeze NEW_DIR or --inputs FROZEN_DIR --output NEW_DIR')