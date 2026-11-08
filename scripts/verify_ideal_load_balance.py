"""Independent steady moist-air balance probes for pinned EnergyPlus 9.0.1.

Freeze first, run second. Preserves failures and never edits native SQL or old inputs.
This is synthetic controlled validation, not measured buildings or sizing approval.
"""
import argparse
import json
import math
import re
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import core
from backend.execution import Policy,supervise
from backend.private_storage import private_mkdir

GROUPS={'zone':'Zone','supply':'Supply Air','outdoor':'Outdoor Air','recovery':'Heat Recovery'}
VARIABLES={f'{group}_{part}_{mode}_W':f'Zone Ideal Loads {label} {part.title()} {mode.title()} Rate'
           for group,label in GROUPS.items() for mode in ('heating','cooling') for part in ('sensible','latent','total')}
VARIABLES.update(outdoor_mass_kg_s='Zone Ideal Loads Outdoor Air Mass Flow Rate',supply_mass_kg_s='Zone Ideal Loads Supply Air Mass Flow Rate')


def psat(t):
    """ASHRAE saturation pressure equation in SI, independent Python evaluation."""
    k=t+273.15
    if t>=0:return math.exp(-5800.2206/k+1.3914993-.048640239*k+.000041764768*k*k-1.4452093e-8*k**3+6.5459673*math.log(k))
    return math.exp(-5674.5359/k+6.3925247-.009677843*k+.00000062215701*k*k+2.0747825e-9*k**3-9.484024e-13*k**4+4.1635019*math.log(k))


def humidity(t,rh):
    pressure=psat(t)*rh
    return .621945*pressure/(101325-pressure)


def enthalpy(t,w):return 1004.84*t+w*(2500940+1858.95*t)


def oracle(s):
    ti,to=s['indoor_C'],s['outdoor_C'];wi=humidity(ti,s['rh']);wo=humidity(s['dewpoint_C'],1.)
    cp=1004.84+1858.95*wi;hg=2500940+1858.95*ti
    gains=s['gains_W'];latent=gains*s['latent_fraction'];moisture=latent/hg
    q=110*(ti-to)/(1.6+.1+.04)-gains*(1-s['latent_fraction'])
    limit=50. if q>0 else 14.
    rho=101325/(287*293.15*(1+1.6077687e-5))
    oa=s['oa_m3_s']*rho
    m=max(abs(q)/(cp*abs(limit-ti)),moisture/(wi-.004),oa)
    ts=ti+q/(m*cp);ws=wi-moisture/m
    assert 14-1e-10<=ts<=50+1e-10 and 0<ws<humidity(ts,1.),'Oracle supply state unsupported'
    tr=to+s['recovery_sensible']*(ti-to);wr=wo+s['recovery_latent']*(wi-wo)
    assert wr<humidity(tr,1.),'Oracle heat recovery condensation not covered'
    hm=((m-oa)*enthalpy(ti,wi)+oa*enthalpy(tr,wr))/m
    wm=((m-oa)*wi+oa*wr)/m;tm=(hm-2500940*wm)/(1004.84+1858.95*wm)
    qsupply=m*(1004.84+1858.95*wm)*(ts-tm)
    pairs={'zone':(q,m*(enthalpy(ts,ws)-enthalpy(ti,wi))-q),
           'supply':(qsupply,m*(enthalpy(ts,ws)-hm)-qsupply),
           'outdoor':(oa*cp*(to-ti),oa*(enthalpy(to,wo)-enthalpy(ti,wi))-oa*cp*(to-ti)),
           'recovery':(oa*(1004.84+1858.95*wo)*(tr-to),oa*(enthalpy(tr,wr)-enthalpy(to,wo))-oa*(1004.84+1858.95*wo)*(tr-to))}
    expected={'outdoor_mass_kg_s':oa,'supply_mass_kg_s':m}
    for group,(sensible,latent) in pairs.items():
        for mode,sign in [('heating',1),('cooling',-1)]:
            for part,val in [('sensible',sensible),('latent',latent)]:
                if group=='outdoor':
                    active=pairs['supply'][0 if part=='sensible' else 1]*sign>0
                    value=max(-sign*val,0.) if active else 0.
                else:value=max(sign*val,0.)
                expected[f'{group}_{part}_{mode}_W']=value
            expected[f'{group}_total_{mode}_W']=sum(expected[f'{group}_{part}_{mode}_W'] for part in ('sensible','latent'))
    scale=s['zone_multiplier']*s['list_multiplier']
    expected={k:v*scale for k,v in expected.items()}
    return {'expected_native_including_multipliers':expected,'conditions':{'indoor_C':ti,'indoor_humidity':wi,'outdoor_humidity':wo,'supply_C':ts,'supply_humidity':ws,'source_moisture_kg_s':moisture*scale},
            'equations':'UA*(Ti-To)-Qconv; G=Qlatent/hg(Ti); m*(wz-ws)=G; h=cp_dry*T+w*hg(T); mixing and recovery energy conservation. Directional native outputs are clipped separately.',
            'tolerances':{'rate_absolute_W':1.,'rate_relative':.005,'mass_absolute_kg_s':2e-6,'mass_relative':.005,'temperature_K':.02,'humidity_absolute':2e-6}}


def cases():
    base={'indoor_C':24.,'outdoor_C':32.,'dewpoint_C':20.,'rh':.5,'gains_W':800.,'latent_fraction':.4,'oa_m3_s':0.,'recovery_sensible':0.,'recovery_latent':0.,'zone_multiplier':1,'list_multiplier':1}
    rows=[]
    for name,changes in [('dry_no_oa',{'latent_fraction':0.}),('humid_no_oa',{}),('humid_oa',{'oa_m3_s':.02}),('humid_enthalpy_recovery',{'oa_m3_s':.02,'recovery_sensible':.65,'recovery_latent':.55}),('humid_sensible_recovery',{'oa_m3_s':.02,'recovery_sensible':.65}),('winter_oa',{'indoor_C':22.,'outdoor_C':-2.,'dewpoint_C':-5.,'rh':.4,'gains_W':400.,'latent_fraction':.25,'oa_m3_s':.02}),('winter_enthalpy_recovery',{'indoor_C':22.,'outdoor_C':-2.,'dewpoint_C':-5.,'rh':.4,'gains_W':400.,'latent_fraction':.25,'oa_m3_s':.02,'recovery_sensible':.65,'recovery_latent':.55}),('multiplied_humid_oa',{'oa_m3_s':.02,'zone_multiplier':3,'list_multiplier':2})]:
        rows.append({'name':name,**base,**changes})
    return rows


def model(base,s):
    data=[]
    for part in re.sub(r'!.*','',base).split(';'):
        if not part.strip():continue
        row=[v.strip() for v in part.split(',')];kind=row[0].lower()
        if kind.startswith('output:') or kind.startswith('sizing:') or kind=='designspecification:outdoorair':continue
        if kind=='sizingperiod:designday':
            if row[1]=='Synthetic winter':continue
            row[1]='Independent moist balance';row[5]=str(s['outdoor_C']);row[10]=str(s['dewpoint_C'])
        if kind=='simulationcontrol':row=['SimulationControl','No','No','No','Yes','No']
        if kind=='material:nomass':row[3]='1.6'
        if kind=='zone':row[7]=str(s['zone_multiplier'])
        if kind=='schedule:constant' and row[1] in ('Heat','Cool'):
            target=s['indoor_C'];heating=s['outdoor_C']<target
            row[3]=str(target if (row[1]=='Heat')==heating else target+(2 if row[1]=='Cool' else -2))
        if kind=='zonehvac:idealloadsairsystem':
            recovery='Enthalpy' if s['recovery_latent'] else 'Sensible' if s['recovery_sensible'] else 'None'
            row=['ZoneHVAC:IdealLoadsAirSystem','Ideal','','Supply','','','50','14','.015','.004','NoLimit','','','NoLimit','','','','','Humidistat','','Humidistat','Explicit OA' if s['oa_m3_s'] else '','Outdoor air' if s['oa_m3_s'] else '','None','NoEconomizer',recovery,str(s['recovery_sensible']),str(s['recovery_latent'])]
        data.append(row)
    data.extend([['Schedule:Constant','Moist target','Any',str(100*s['rh'])],['Schedule:Constant','Always','Any','1'],['ZoneControl:Humidistat','Explicit humidistat','Box','Moist target','Moist target'],['OtherEquipment','Declared moisture and heat','None','Box','Always','EquipmentLevel',str(s['gains_W']),'','',str(s['latent_fraction']),'0','0'],['Output:SQLite','SimpleAndTabular']])
    if s['oa_m3_s']:data.extend([['DesignSpecification:OutdoorAir','Explicit OA','Flow/Zone','0','0',str(s['oa_m3_s']),'0'],['OutdoorAir:Node','Outdoor air','0']])
    if s['list_multiplier']!=1:data.extend([['ZoneList','Explicit list','Box'],['ZoneGroup','Explicit group','Explicit list',str(s['list_multiplier'])]])
    names=list(VARIABLES.values())+['Zone Air Temperature','Zone Air Humidity Ratio','Zone Air Relative Humidity','System Node Temperature','System Node Humidity Ratio','System Node Mass Flow Rate']
    data.extend([['Output:Variable','*',n,'Hourly'] for n in names])
    return '\n'.join(','.join(r)+';' for r in data)+'\n'


def freeze(path):
    if path.exists():raise ValueError('Frozen input destination already exists')
    private_mkdir(path);base=json.loads((ROOT/'fixtures/test/native_zone_sizing_projection.json').read_text())['model_idf'];rows=[]
    for s in cases():
        work=private_mkdir(path/s['name']);idf=model(base,s);(work/'input.idf').write_text(idf,encoding='ascii')
        rows.append({'spec':s,'oracle':oracle(s),'model_sha256':core.sha(work/'input.idf')})
    core.write_json(path/'frozen.json',{'scope':'Controlled steady synthetic box; no solar, infiltration or real device efficiency. Strict independent moisture and enthalpy balance, not field validation.','script_sha256':core.sha(Path(__file__)),'source_fixture_sha256':core.sha(ROOT/'fixtures/test/native_zone_sizing_projection.json'),'cases':rows})
    print('Frozen '+str(len(rows))+' new cases: '+core.sha(path/'frozen.json'))


def run(inputs,output,selected=None):
    if output.exists():raise ValueError('Output already exists; preserve previous run')
    private_mkdir(output);frozen=core.read_json(inputs/'frozen.json');receipt={'frozen_sha256':core.sha(inputs/'frozen.json'),'selected_cases':selected,'cases':[]}
    if selected and not set(selected).issubset({r['spec']['name'] for r in frozen['cases']}):raise ValueError('Unknown selected case')
    for row in frozen['cases']:
        spec=row['spec']
        if selected and spec['name'] not in selected:continue
        work=private_mkdir(output/spec['name']);source=inputs/spec['name']/'input.idf'
        assert core.sha(source)==row['model_sha256'];(work/'input.idf').write_bytes(source.read_bytes())
        record={'name':spec['name'],'status':'not_run','model_sha256':row['model_sha256']}
        try:
            native=private_mkdir(work/'output');record['execution']=supervise([core.engine_path(),'-d',native,work/'input.idf'],work,private_mkdir(work/'logs'),Policy(),90,output=native)
            err=(native/'eplusout.err').read_text(errors='replace');record['warning_lines']=[x for x in err.splitlines() if '** Warning **' in x]
            assert not re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*',err,re.I),'Native severe/fatal'
            con=sqlite3.connect((native/'eplusout.sql').as_uri()+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
            dictionary=[dict(r) for r in con.execute('SELECT * FROM ReportDataDictionary')];values={}
            for key,variable in VARIABLES.items():
                match=[d for d in dictionary if d['Name']==variable and d['KeyValue']=='IDEAL' and d['ReportingFrequency']=='Hourly'];assert len(match)==1,(key,match)
                did=match[0]['ReportDataDictionaryIndex'];data=[r[0] for r in con.execute('SELECT r.Value FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex WHERE ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=1 AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(did,))];assert len(data)==24,(key,len(data));values[key]=data
            conditions={}
            for key,variable,entity in [('indoor_C','Zone Air Temperature','BOX'),('indoor_humidity','Zone Air Humidity Ratio','BOX'),('supply_C','System Node Temperature','SUPPLY'),('supply_humidity','System Node Humidity Ratio','SUPPLY')]:
                d=[d for d in dictionary if d['Name']==variable and d['KeyValue']==entity];assert len(d)==1
                conditions[key]=[r[0] for r in con.execute('SELECT r.Value FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex WHERE ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=1 AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(d[0]['ReportDataDictionaryIndex'],))]
                assert len(conditions[key])==24
            con.close();gold=row['oracle'];checks=[]
            for key,expected in gold['expected_native_including_multipliers'].items():
                mass=key.endswith('kg_s');tol=max(gold['tolerances']['mass_absolute_kg_s' if mass else 'rate_absolute_W'],abs(expected)*gold['tolerances']['mass_relative' if mass else 'rate_relative']);error=max(abs(v-expected) for v in values[key]);checks.append({'key':key,'expected':expected,'max_error':error,'tolerance':tol,'passed':error<=tol})
            for key,vals in conditions.items():
                expected=gold['conditions'][key];tol=gold['tolerances']['temperature_K' if key.endswith('_C') else 'humidity_absolute'];error=max(abs(v-expected) for v in vals);checks.append({'key':key,'expected':expected,'max_error':error,'tolerance':tol,'passed':error<=tol})
            water=[values['supply_mass_kg_s'][i]*(conditions['indoor_humidity'][i]-conditions['supply_humidity'][i]) for i in range(24)];expected=gold['conditions']['source_moisture_kg_s'];error=max(abs(v-expected) for v in water);tol=max(1e-8,abs(expected)*.005);checks.append({'key':'independent_water_balance_kg_s','expected':expected,'max_error':error,'tolerance':tol,'passed':error<=tol})
            core.write_json(work/'native-projection.json',{'dictionary':dictionary,'series':values,'conditions':conditions,'sql_sha256':core.sha(native/'eplusout.sql')})
            record.update(status='passed' if all(x['passed'] for x in checks) else 'numerical_mismatch',checks=checks,sql_sha256=core.sha(native/'eplusout.sql'))
        except Exception as exc:record.update(status='failed',error=type(exc).__name__+': '+str(exc))
        core.write_json(work/'record.json',record);receipt['cases'].append(record);core.write_json(output/'receipt.json',receipt)
        print(json.dumps({'name':record['name'],'status':record['status'],'failures':[c for c in record.get('checks',[]) if not c['passed']],'error':record.get('error')},ensure_ascii=False),flush=True)
    receipt['all_passed']=all(r['status']=='passed' for r in receipt['cases']);core.write_json(output/'receipt.json',receipt)
    return receipt


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',type=Path);ap.add_argument('--inputs',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--case',action='append');a=ap.parse_args()
    if a.freeze:freeze(a.freeze.resolve())
    elif a.inputs and a.output:run(a.inputs.resolve(),a.output.resolve(),a.case)
    else:ap.error('Use --freeze NEW_DIR or --inputs FROZEN_DIR --output NEW_DIR')
