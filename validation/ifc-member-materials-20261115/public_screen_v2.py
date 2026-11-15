import hashlib,json,sys,time,math
from pathlib import Path
import ifcopenshell

repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');sys.path.insert(0,str(repo))
from backend import parser_runtime
root=Path('C:/Users/18483/AppData/Local/Temp/vra-ifc-beam-reference-20261108')
out=Path(__file__).parent/'public-screen-v2';out.mkdir(exist_ok=False)
acquisition=json.loads((repo/'validation/ifc-beam-handoff-20261108/public-acquisition.json').read_text())
# Independent analytic areas: rectangle decomposition + four root fillets or
# annular disk. No product profile/geometry function supplies expected volume.
rows=[]
for entry in acquisition['files']:
    if entry['file'] not in ['beam-extruded-solid.ifc','beam-varying-profiles.ifc']:continue
    path=root/entry['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
    doc=ifcopenshell.open(str(path))
    for beam in doc.by_type('IfcBeam'):
        bodies=[b for b in beam.Representation.Representations if b.RepresentationIdentifier=='Body']
        assert len(bodies)==1 and len(bodies[0].Items)==1
        solid=bodies[0].Items[0];p=solid.SweptArea
        if p.is_a('IfcIShapeProfileDef'):
            area=2*p.OverallWidth*p.FlangeThickness+(p.OverallDepth-2*p.FlangeThickness)*p.WebThickness+(4-math.pi)*(p.FilletRadius or 0)**2
        elif p.is_a('IfcCircleHollowProfileDef'):
            area=math.pi*(p.Radius**2-(p.Radius-p.WallThickness)**2)
        else:raise ValueError('unfrozen reference profile')
        # Original public documents explicitly use millimetres.
        units=doc.by_type('IfcProject')[0].UnitsInContext.Units
        length=[u for u in units if u.UnitType=='LENGTHUNIT'];assert len(length)==1 and length[0].Name=='METRE' and length[0].Prefix=='MILLI'
        expected=area*solid.Depth/1e9
        rows.append({'file':entry['file'],'sha256':entry['sha256'],'product_id':beam.id(),'expected_m3':expected,'relative_tolerance':.005})
(out/'expected-before-run.json').write_text(json.dumps(rows,indent=2)+'\n')
results=[]
for ref in rows:
    start=time.monotonic()
    with parser_runtime.run('cad',root/ref['file'],options={'operation':'ifc_layers','product_id':ref['product_id']}) as scope:
        r=json.loads((scope['work']/'result.json').read_text(encoding='utf-8'))
    (out/(ref['file']+'-'+str(ref['product_id'])+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    value=r.get('total_layer_envelope_m3')
    error=abs(value-ref['expected_m3'])/ref['expected_m3'] if value is not None else None
    results.append({**ref,'status':r.get('status'),'reason':r.get('reason',r.get('error')),'actual_m3':value,'relative_error':error,
                    'seconds':time.monotonic()-start,'passed':r.get('status')=='measured' and error<=ref['relative_tolerance']})
(out/'assessment.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
