"""Predeclared variants of the untouched first analytic benchmark."""
import copy,hashlib,json,re,sqlite3,sys,tempfile,uuid
from pathlib import Path
repo=Path(__file__).resolve().parents[2];sys.path.insert(0,str(repo))
from backend.execution import Policy,supervise
from backend.private_storage import private_mkdir
base=json.loads((Path(__file__).parent/'steady-probe-v1.json').read_text())
original=Path(base['root'])/'input.idf';raw=original.read_bytes()
assert hashlib.sha256(raw).hexdigest()==base['model_sha256']
parsed=[[f.strip() for f in o.split(',')] for o in re.sub(r'!.*','',raw.decode()).split(';') if o.strip()]
root=Path(tempfile.gettempdir())/('vra-load-matrix-'+uuid.uuid4().hex);private_mkdir(root)
specs=[{'id':'insulated','R':4}, {'id':'temperature','winter':-20,'summer':40},
       {'id':'thermal_mass','mass':True}, {'id':'zone_multiplier','multiplier':3},
       {'id':'user_sizing','heating_factor':1.25,'cooling_factor':1.15}]
for spec in specs:
 spec.setdefault('R',2);spec.setdefault('winter',-10);spec.setdefault('summer',35)
 spec.setdefault('multiplier',1);spec.setdefault('heating_factor',1);spec.setdefault('cooling_factor',1)
 spec['expected_W']={kind:110*delta/(.1+spec['R']+.04)*spec['multiplier']
                     for kind,delta in [('Heating',20-spec['winter']),('Cooling',spec['summer']-25)]}
 spec['tolerance']='max(1 W, expected*0.005); same as original pre-run criterion'
with (root/'predeclared.json').open('x') as f:json.dump(specs,f,indent=2)
records=[]
for spec in specs:
 case=root/spec['id'];private_mkdir(case);private_mkdir(case/'output');private_mkdir(case/'logs')
 objs=copy.deepcopy(parsed)
 for o in objs:
  if o[0]=='Material:NoMass':
   if spec.get('mass'):o[:]=['Material','R2','Smooth','0.2',str(.2/spec['R']),'1000','1000','.9','.7','.7']
   else:o[3]=str(spec['R'])
  if o[0]=='SizingPeriod:DesignDay':
   winter=o[1]=='Synthetic winter';o[5]=str(spec['winter'] if winter else spec['summer'])
   if winter:o[10]=str(spec['winter'])
  if o[0]=='Zone':o[7]=str(spec['multiplier'])
  if o[0]=='Sizing:Zone':o[11]=str(spec['heating_factor']);o[12]=str(spec['cooling_factor'])
 model=case/'input.idf';model.write_text('\n'.join(','.join(o)+';' for o in objs),encoding='ascii')
 record={'spec':spec,'root':str(case),'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest()}
 try:
  record['execution']=supervise(['F:/EnergyPlusV9-0-1/energyplus.exe','-d',str(case/'output'),str(model)],
                                 case,case/'logs',Policy(),60,output=case/'output')
  with sqlite3.connect('file:'+(case/'output/eplusout.sql').as_posix()+'?mode=ro',uri=True) as con:
   con.row_factory=sqlite3.Row;record['sizes']=[dict(r) for r in con.execute('SELECT * FROM ZoneSizes')]
   record['zones']=[dict(r) for r in con.execute('SELECT * FROM Zones')]
   record['tables']=[dict(r) for r in con.execute("SELECT * FROM TabularDataWithStrings WHERE ReportName='HVACSizingSummary'")]
  checks=[]
  for row in record['sizes']:
   expected=spec['expected_W'][row['LoadType']]
   for key,factor in [('CalcDesLoad',1),('UserDesLoad',spec['heating_factor'] if row['LoadType']=='Heating' else spec['cooling_factor'])]:
    value=expected*factor;error=abs(row[key]-value)
    checks.append({'type':row['LoadType'],'column':key,'expected_W':value,'actual_W':row[key],
                   'error_W':error,'pass':error<=max(1,.005*value)})
  record['checks']=checks;record['status']='passed' if len(checks)==4 and all(c['pass'] for c in checks) else 'failed_numeric'
 except Exception as exc:record['status']='failed_execution';record['error']=type(exc).__name__+': '+str(exc)
 records.append(record)
 with (case/'record.json').open('x') as f:json.dump(record,f,indent=2)
 print(json.dumps({'id':spec['id'],'status':record['status'],'checks':record.get('checks'),'error':record.get('error')}),flush=True)
with (Path(__file__).parent/'steady-matrix-v1.json').open('x') as f:json.dump({'root':str(root),'records':records},f,indent=2)
assert all(r['status']=='passed' for r in records),'Raw failures preserved; no retrospective tolerance changes'
