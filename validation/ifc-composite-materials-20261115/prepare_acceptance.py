from pathlib import Path
from decimal import Decimal as D
import json, shutil
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
p=root/'scenario-reference-frozen.json';assert not p.exists()
mass=[D(v)*D('.5')*D('1.1')*D('1000') for v in ['12','10']]
reference={'procurement_kg':[str(x) for x in mass],
 'cost_USD':str(sum(m/D(1000)*p for m,p in zip(mass,[D(100),D(200)]))),
 'carbon_kgCO2e':str(sum(m*f for m,f in zip(mass,[D(2),D(3)]))),
 'replacement_cost_USD':str(sum(m/D(1000)*p for m,p in zip(mass,[D(80),D(160)]))),
 'replacement_carbon_kgCO2e':str(sum(m*f for m,f in zip(mass,[D('1.5'),D('2.25')])))}
p.write_text(json.dumps(reference,indent=2)+'\n')
shutil.copy2(root/'test_ifc_composite_workflow.py',repo/'tests/test_ifc_composite_workflow.py')
source=(root.parent/'ifc-member-materials-20261115/http_acceptance.py').read_text(encoding='utf-8')
source=source.replace('from test_ifc_member_quantities import member','from test_ifc_composite_materials import composite')
source=source.replace("_,_,element,_,input_path=member(runtime,'IfcColumn','MILLI')","_,element,_,_,profiles,_,input_path=composite(runtime,'MILLI','one_sided_opening')")
source=source.replace('vra-member-http-','vra-composite-http-').replace('synthetic-column.ifc','synthetic-composite.ifc')
source=source.replace("for a in b['alternatives']:a['layers'][0]['evidence_ids']=[ev['evidence_id']]","""for a in b['alternatives']:
   for row in a['layers']:row['evidence_ids']=[ev['evidence_id']]
   a['layers'][1]['quote']['unit_price']*=2
   a['layers'][1]['factor']['value']*=1.5""")
source=source.replace('1210','1760').replace('24200','29700')
needle="  ev=c.post(base+'/evidence'"
insert="""  check('distinct_material_quantities',all(abs(x['envelope_volume_m3']-v)<1e-8 for x,v in zip(r['result']['layers'],[12,10])),[x['envelope_volume_m3'] for x in r['result']['layers']])
  check('source_profile_ids',[x['layer_id'] for x in r['result']['layers']]==[p.id() for p in profiles],[x['layer_id'] for x in r['result']['layers']])
  original=c.get(base+'/files/'+f['file_id']);check('uploaded_original_preserved',original.content==source,hashlib.sha256(original.content).hexdigest())
  ev=c.post(base+'/evidence'"""
assert source.count(needle)==1;source=source.replace(needle,insert).replace('len(checks)==12','len(checks)==15')
(root/'http_acceptance.py').write_text(source,encoding='utf-8')
print(json.dumps(reference))
