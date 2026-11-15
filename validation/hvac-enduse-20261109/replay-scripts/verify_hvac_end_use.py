"""Frozen independent equipment-energy cases; synthetic, not measured buildings."""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import re
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import core
from backend.execution import Policy,supervise
from backend.private_storage import private_mkdir


def rows(text):return [[v.strip() for v in s.split(',')] for s in re.sub(r'!.*','',text).split(';') if s.strip()]
def emit(data):return '! Independent equipment reference. No real-building claim.\n'+'\n'.join(','.join(map(str,r))+';' for r in data)+'\n'


def specifications():
    return [
      {'id':'C01','type':'cool','gain':1000,'flow':.25,'pressure':180,'fan_eff':.6,'cop':3.,'outside':24,'inside':24},
      {'id':'C02','type':'cool','gain':1650,'flow':.31,'pressure':240,'fan_eff':.62,'cop':4.2,'outside':24,'inside':24},
      {'id':'H01','type':'gas','gain':250,'flow':.24,'pressure':200,'fan_eff':.6,'eff':.83,'outside':-4,'inside':21},
      {'id':'H02','type':'electric','gain':170,'flow':.27,'pressure':210,'fan_eff':.63,'eff':.95,'outside':-8,'inside':22},
      {'id':'P01','type':'plant','load':5000,'flow':.001,'power':150,'motor':.85,'eff':.8,'outside':20},
      {'id':'P02','type':'plant','load':8300,'flow':.0018,'power':290,'motor':.9,'eff':.91,'outside':20},
      {'id':'Z01','type':'off','gain':0,'flow':.25,'pressure':180,'fan_eff':.6,'cop':3.,'outside':20,'inside':24},
      {'id':'M01','type':'mixed','gain':1110,'flow':.28,'pressure':170,'fan_eff':.68,'cop':3.4,'outside':24,'inside':24,'ideal_gain':1730},
    ]


def oracle(s):
    f=lambda x:F(str(x));expected={}
    if s['type']=='plant':
        expected={'Pumps:Electricity':f(s['power']),'Heating:NaturalGas':(f(s['load'])-f(s['power'])*f(s['motor']))/f(s['eff'])}
    else:
        fan=f(s['flow'])*f(s['pressure'])/f(s['fan_eff']) if s['type']!='off' else F(0)
        expected={'Fans:Electricity':fan,'InteriorEquipment:Electricity':f(s['gain'])}
        if s['type'] in ('cool','mixed'):expected['Cooling:Electricity']=(f(s['gain'])+fan)/f(s['cop'])
        if s['type']=='mixed':expected['Cooling:DistrictCooling']=f(s['ideal_gain'])
        if s['type'] in ('gas','electric'):
            heat=F(110)*(f(s['inside'])-f(s['outside']))/(F('1.73')+F('.1')+F('.04'))-f(s['gain'])-fan
            expected['Heating:'+('NaturalGas' if s['type']=='gas' else 'Electricity')]=heat/f(s['eff'])
        if s['type']=='off':expected.update({'Cooling:Electricity':F(0),'Heating:Electricity':F(0)})
    return {'expected_power_W':{k:str(v) for k,v in expected.items()},'expected_24h_kWh':{k:str(v*24/1000) for k,v in expected.items()},'absolute_W':1.0,'relative':.005,
      'equations':'Fan=q*deltaP/total_eff; cooling=(gain+fan)/COP with unit performance curves and PLF=1; heating=(110*(Ti-To)/(1.73+.1+.04)-gain-fan)/eff; plant gas=(load-pump_power*motor_eff)/boiler_eff. All schedules constant; ideal zone separate thermal load.'}


def model(s,base):
    data=[];adiabatic=s['type'] in ('cool','mixed','off','plant')
    for r in rows(base):
        k=r[0].casefold()
        if k.startswith(('output:','sizing:','zonehvac:','zonecontrol:','thermostatsetpoint:')) or k=='designspecification:outdoorair':continue
        if k=='sizingperiod:designday':
            if r[1]!='Synthetic summer':continue
            r[1]='Equipment reference';r[5]=str(s['outside']);r[10]=str(min(-12,s['outside']-5))
        if k=='simulationcontrol':r=['SimulationControl','No','No','No','Yes','No']
        if k=='material:nomass':r[3]='1.73'
        if k=='buildingsurface:detailed' and adiabatic:r[5:7]=['Adiabatic','']
        if k=='schedule:constant' and r[1] in ('Heat','Cool'):
            heating=s['type'] in ('gas','electric');target=s.get('inside',24)
            r[3]=str(target if (r[1]=='Heat')==heating else target+(4 if r[1]=='Cool' else -4))
        data.append(r)
    data.extend([['Schedule:Constant','On','Any','1'],['Schedule:Constant','Off','Any','0']])
    if s['type']=='plant':
        data.extend([
         ['Schedule:Constant','PlantLoad','Any',s['load']],['Schedule:Constant','PlantTemp','Any',60],
         ['SetpointManager:Scheduled','PlantSetpoint','Temperature','PlantTemp','SupplyOut'],
         ['PlantLoop','Loop','Water','','Ops','SupplyOut',100,0,s['flow'],0,'Autocalculate','SupplyIn','SupplyOut','SupplyBranches','','DemandIn','DemandOut','DemandBranches','','SequentialLoad'],
         ['BranchList','SupplyBranches','SupplyBranch'],['BranchList','DemandBranches','DemandBranch'],
         ['Branch','SupplyBranch','','Pump:ConstantSpeed','Pump','SupplyIn','PumpOut','Boiler:HotWater','Boiler','PumpOut','SupplyOut'],
         ['Branch','DemandBranch','','LoadProfile:Plant','Load','DemandIn','DemandOut'],
         ['Pump:ConstantSpeed','Pump','SupplyIn','PumpOut',s['flow'],50000,s['power'],s['motor'],0,'Continuous'],
         ['Boiler:HotWater','Boiler','NaturalGas',20000,s['eff'],'','',s['flow'],0,1,1,'PumpOut','SupplyOut',99,'ConstantFlow',0,1],
         ['LoadProfile:Plant','Load','DemandIn','DemandOut','PlantLoad',s['flow'],'On'],
         ['PlantEquipmentOperationSchemes','Ops','PlantEquipmentOperation:HeatingLoad','HeatingOps','On'],
         ['PlantEquipmentOperation:HeatingLoad','HeatingOps',0,1e9,'Equipment'],['PlantEquipmentList','Equipment','Boiler:HotWater','Boiler']])
    else:
        avail='Off' if s['type']=='off' else 'On';heatkind='Coil:Heating:Fuel' if s['type']=='gas' else 'Coil:Heating:Electric'
        heat=['Coil:Heating:Fuel','HeatCoil',avail,'NaturalGas',s.get('eff',1),6000,'CoolOut','Supply'] if s['type']=='gas' else ['Coil:Heating:Electric','HeatCoil',avail,s.get('eff',1),6000,'CoolOut','Supply']
        data.extend([
         ['ThermostatSetpoint:DualSetpoint','Setpoints','Heat','Cool'],['ZoneControl:Thermostat','Control','Box','Control','ThermostatSetpoint:DualSetpoint','Setpoints'],
         ['ZoneHVAC:EquipmentConnections','Box','Equipment','Supply','Return','Zone air','UnusedReturn'],
         ['ZoneHVAC:EquipmentList','Equipment','SequentialLoad','ZoneHVAC:PackagedTerminalAirConditioner','PTAC',1,1],
         ['ZoneHVAC:PackagedTerminalAirConditioner','PTAC',avail,'Return','Supply','','',s['flow'],s['flow'],s['flow'],0,0,0,'Fan:OnOff','Fan',heatkind,'HeatCoil','Coil:Cooling:DX:SingleSpeed','CoolCoil','BlowThrough','On'],
         ['Fan:OnOff','Fan',avail,s['fan_eff'],s['pressure'],s['flow'],.9,1,'Return','FanOut'],heat,
         ['Coil:Cooling:DX:SingleSpeed','CoolCoil',avail,6000,1,s.get('cop',3),s['flow'],'','FanOut','CoolOut','UnitTemp','UnitFlow','UnitTemp','UnitFlow','UnitFlow'],
         ['Curve:Biquadratic','UnitTemp',1,0,0,0,0,0,-100,100,-100,100],['Curve:Quadratic','UnitFlow',1,0,0,0,1],
         ['ElectricEquipment','Declared gain','Box','On','EquipmentLevel',s['gain'],'','',0,0,0],
        ])
        if s['type']=='mixed':
            for r in list(data):
                k=r[0].casefold()
                if k=='zone':r=r.copy();r[1]='IdealBox';data.append(r)
                elif k=='buildingsurface:detailed':
                    r=r.copy();r[1]='I'+r[1];r[4]='IdealBox'
                    for i in range(11,len(r),3):r[i]=str(float(r[i])+10)
                    data.append(r)
                elif k=='surfaceproperty:convectioncoefficients':r=r.copy();r[1]='I'+r[1];data.append(r)
            data.extend([
             ['ZoneControl:Thermostat','IControl','IdealBox','Control','ThermostatSetpoint:DualSetpoint','Setpoints'],
             ['ZoneHVAC:EquipmentConnections','IdealBox','IEquipment','ISupply','','IZone air','IReturn'],
             ['ZoneHVAC:EquipmentList','IEquipment','SequentialLoad','ZoneHVAC:IdealLoadsAirSystem','Ideal',1,1],
             ['ZoneHVAC:IdealLoadsAirSystem','Ideal','','ISupply','','',50,12,.009,.009,'NoLimit','','','NoLimit','','','','','None','','None'],
             ['OtherEquipment','Ideal heat','None','IdealBox','On','EquipmentLevel',s['ideal_gain'],'','',0,0,0]])
    data.extend([['Output:SQLite','SimpleAndTabular'],['Output:Table:SummaryReports','AnnualBuildingUtilityPerformanceSummary'],['Output:Meter','*','Hourly'],['Output:Variable','*','Zone Mean Air Temperature','Hourly'],['Output:Variable','*','Pump Electric Power','Hourly'],['Output:Variable','*','Pump Fluid Heat Gain Rate','Hourly']])
    return emit(data)


def freeze(path):
    if path.exists():raise ValueError('Do not overwrite frozen inputs')
    private_mkdir(path);base=json.loads((ROOT/'fixtures/test/native_zone_sizing_projection.json').read_text())['model_idf'];cases=[]
    for spec in specifications():
        d=private_mkdir(path/spec['id']);(d/'input.idf').write_text(model(spec,base),encoding='ascii')
        cases.append({'spec':spec,'oracle':oracle(spec),'model_sha256':core.sha(d/'input.idf')})
    core.write_json(path/'frozen.json',{'cases':cases,'script_sha256':core.sha(Path(__file__)),'scope':'Eight new synthetic controlled design days; no annual claim; performance curves fixed by declaration, no measured efficiency.'})
    print('Frozen '+str(len(cases))+' cases: '+core.sha(path/'frozen.json'))


def run(inputs,output,selected=None):
    if output.exists():raise ValueError('Do not overwrite a run')
    private_mkdir(output);frozen=core.read_json(inputs/'frozen.json');assert frozen['script_sha256']==core.sha(Path(__file__))
    receipt={'frozen_sha256':core.sha(inputs/'frozen.json'),'engine':str(core.engine_path()),'engine_sha256':core.sha(core.engine_path()),'cases':[]}
    for case in frozen['cases']:
        spec=case['spec']
        if selected and spec['id'] not in selected:continue
        work=private_mkdir(output/spec['id']);src=inputs/spec['id']/'input.idf';assert core.sha(src)==case['model_sha256'];(work/'input.idf').write_bytes(src.read_bytes());record={'id':spec['id'],'model_sha256':case['model_sha256']}
        try:
            native=private_mkdir(work/'output');record['execution']=supervise([core.engine_path(),'-d',native,work/'input.idf'],work,private_mkdir(work/'logs'),Policy(),120,output=native)
            err=(native/'eplusout.err').read_text(errors='replace');record['warnings']=[x for x in err.splitlines() if '** Warning **' in x];assert not re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*',err,re.I),'Native severe/fatal'
            con=sqlite3.connect((native/'eplusout.sql').as_uri()+'?mode=ro',uri=True);con.row_factory=sqlite3.Row;dictionary=[dict(r) for r in con.execute('SELECT * FROM ReportDataDictionary')];checks=[];series={}
            for name,want in case['oracle']['expected_power_W'].items():
                found=[d for d in dictionary if d['Name'].casefold()==name.replace(':NaturalGas',':Gas').casefold() and d['ReportingFrequency']=='Hourly' and d['IsMeter']==1]
                assert len(found)==1,(name,'missing/duplicate meter');d=found[0];assert d['Units']=='J'
                data=[dict(r) for r in con.execute('SELECT r.Value,t.Interval FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex WHERE r.ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=1 AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(d['ReportDataDictionaryIndex'],))];assert len(data)==24
                watts=[r['Value']/(r['Interval']*60) for r in data];expected=float(F(want));tol=max(case['oracle']['absolute_W'],abs(expected)*case['oracle']['relative']);error=max(abs(x-expected) for x in watts)
                checks.append({'meter':name,'expected_W':expected,'maximum_error_W':error,'tolerance_W':tol,'passed':error<=tol});series[name]={'dictionary':d,'hourly_W':watts}
            con.close();record.update(status='passed' if all(x['passed'] for x in checks) else 'numerical_mismatch',checks=checks,sql_sha256=core.sha(native/'eplusout.sql'));core.write_json(work/'projection.json',series)
        except Exception as exc:record.update(status='failed',error=type(exc).__name__+': '+str(exc))
        core.write_json(work/'record.json',record);receipt['cases'].append(record);core.write_json(output/'receipt.json',receipt);print(json.dumps({'id':spec['id'],'status':record['status'],'error':record.get('error'),'failed_checks':[x for x in record.get('checks',[]) if not x['passed']]}),flush=True)
    receipt['all_passed']=all(x['status']=='passed' for x in receipt['cases']);core.write_json(output/'receipt.json',receipt)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',type=Path);ap.add_argument('--inputs',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--case',action='append');a=ap.parse_args()
    if a.freeze:freeze(a.freeze.resolve())
    elif a.inputs and a.output:run(a.inputs.resolve(),a.output.resolve(),a.case)
    else:ap.error('Freeze or execute frozen inputs')
