import hashlib,json,sys,time
from pathlib import Path
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');sys.path[:0]=[str(repo),str(repo/'tests')]
from test_ifc_composite_materials import composite
from backend import parser_runtime
root=Path(__file__).parent;out=root/'curved-native';out.mkdir(exist_ok=False)
doc,element,_,_,mp,solid,path=composite(out,case='adjacent')
outer=doc.create_entity('IfcCircleHollowProfileDef',ProfileType='AREA',Radius=.3,WallThickness=.03)
inner=doc.create_entity('IfcCircleProfileDef',ProfileType='AREA',Radius=.27)
solid.SweptArea.Profiles=[outer,inner]
for row,profile in zip(mp,[outer,inner]):row.Profile=profile
doc.write(str(path));before=hashlib.sha256(path.read_bytes()).hexdigest()
expected=json.loads((root/'curved-reference-frozen.json').read_text())
start=time.monotonic()
with parser_runtime.run('cad',path,options={'operation':'ifc_layers','product_id':element.id()}) as scope:
    result=json.loads((scope['work']/'result.json').read_text(encoding='utf-8'));limits=scope['resource_limits']
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
assert result['status']=='measured',result
actual=[r['envelope_volume_m3'] for r in result['layers']]
errors=[abs(a-b)/b for a,b in zip(actual,expected['expected_m3'])]
receipt={'expected':expected,'actual_m3':actual,'relative_errors':errors,'elapsed_s':time.monotonic()-start,
 'source_sha256_before':before,'source_sha256_after':hashlib.sha256(path.read_bytes()).hexdigest(),
 'resource_limits':limits,'passed':len(actual)==2 and max(errors)<=.005,'public_or_real_building':False}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert receipt['passed'] and receipt['source_sha256_before']==receipt['source_sha256_after']
print(json.dumps(receipt))
