"""Raw STEP Decimal profile area and perpendicular layer depth, no IFC/mesh library."""
from pathlib import Path
from decimal import Decimal as D
import re,json,hashlib
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-slab-layers-20261108')
raw=Path('D:/稀土agent-稀土制暖全流程/outputs/vra-m2-intake-20261108/Duplex_A_20110907.ifc').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed'
definitions=(R/'validation/ifc-union-20261107/public_oracle_v2.py').read_text(encoding='utf-8').split("types={'IFCWALL'")[0]
scope={'raw':raw,'re':re,'D':D};exec(definitions[definitions.index('def fields(s):'):],scope)
rows,ref,refs,vec,axis=[scope[k] for k in ['rows','ref','refs','vec','axis']]
def polygon(curve):
    k,a=ref(curve);assert k=='IFCPOLYLINE'
    points=[vec(p) for p in refs(a[0])];assert len(points)>=4 and points[0]==points[-1] and all(len(p)==2 for p in points)
    # Fixed reference source; require axis-aligned edges and reject crossing polygon edges.
    for p,q in zip(points,points[1:]):assert (p[0]==q[0])!=(p[1]==q[1])
    area=abs(sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(points,points[1:])))/2
    assert area>0
    return area
cases=[];excluded=[]
for ident,(kind,a) in sorted(rows.items()):
    if kind not in {'IFCSLAB','IFCPLATE'}:continue
    try:
        assert '#'+str(ident) not in scope['hosts'],'opening not in simple profile oracle'
        _,shape=ref(a[6]);bodies=[ref(r)[1] for r in refs(shape[2]) if ref(r)[1][1]=="'Body'"]
        assert len(bodies)==1 and len(refs(bodies[0][3]))==1,'non-unique body'
        solid_id=refs(bodies[0][3])[0];k,e=ref(solid_id);assert k=='IFCEXTRUDEDAREASOLID','not a direct extrusion'
        direction=vec(e[2]);assert direction==(0,0,1),'non-normal extrusion outside this public oracle'
        axis(e[1]) # Validate the position is an orthonormal axis permutation.
        pk,profile=ref(e[0])
        if pk=='IFCRECTANGLEPROFILEDEF':area=D(profile[3])*D(profile[4]);axis(profile[2])
        elif pk=='IFCARBITRARYCLOSEDPROFILEDEF':area=polygon(profile[2])
        elif pk=='IFCARBITRARYPROFILEDEFWITHVOIDS':area=polygon(profile[2])-sum(polygon(c) for c in refs(profile[3]))
        else:raise AssertionError('profile not in independent oracle: '+pk)
        bindings=[v for k,v in rows.values() if k=='IFCRELASSOCIATESMATERIAL' and '#'+str(ident) in refs(v[4])]
        assert len(bindings)==1,'missing or ambiguous material association'
        k,u=ref(bindings[0][5]);assert k=='IFCMATERIALLAYERSETUSAGE' and u[1]=='.AXIS3.'
        k,ls=ref(u[0]);assert k=='IFCMATERIALLAYERSET'
        cursor=D(u[3]);layers=[]
        for lid in refs(ls[0]):
            k,layer=ref(lid);assert k=='IFCMATERIALLAYER' and D(layer[1])>0
            k,m=ref(layer[0]);assert k=='IFCMATERIAL'
            end=cursor+D(layer[1])*(1 if u[2]=='.POSITIVE.' else -1)
            lo,hi=sorted((cursor,end));cursor=end
            assert 0<=lo<hi<=D(e[3]),'layers outside extrusion'
            layers.append({'layer_id':int(lid[1:]),'material_id':int(layer[0][1:]),'bounds_m':[lo,hi],'volume_m3':area*(hi-lo)})
        assert sum(r['volume_m3'] for r in layers)==area*D(e[3]),'layer conservation mismatch'
        cases.append({'id':ident,'type':kind,'predefined_type':a[-1],'solid_id':int(solid_id[1:]),'profile_type':pk,'area_m2':area,'depth_m':D(e[3]),'host_volume_m3':area*D(e[3]),'layers':layers})
    except (AssertionError,KeyError,ValueError,IndexError) as exc:excluded.append({'id':ident,'reason':str(exc) or 'Independent oracle eligibility not established'})
record={'source_sha256':hashlib.sha256(raw).hexdigest(),'selection':'All slab/plate entities examined before application execution, no selection by success','cases':cases,'excluded':excluded,'absolute_tolerance_m3':'1e-7','method':'Raw STEP profile shoelace area times each perpendicular layer depth; no mesh volume proportional split','limits':'Public geometry only; polygon holes and oblique/opening behavior tested independently in synthetic inputs; material properties unvalidated'}
path=OUT/'frozen-public-gold.json'
with path.open('x',encoding='utf-8') as f:json.dump(record,f,default=str,indent=2)
print(json.dumps({'eligible':len(cases),'excluded':excluded,'layer_count':sum(len(c['layers']) for c in cases),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
