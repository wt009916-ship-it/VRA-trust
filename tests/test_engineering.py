"""Closed-form Fraction oracles plus an independently assembled beam FEM solver."""
import copy
from fractions import Fraction as F
import numpy as np
import pytest
from pydantic import ValidationError
from backend.engineering import BeamInput, calculate
from test_api import create_project


def beam():
    return {'name':'Independent beam example','support':'simply_supported','span':6,'span_unit':'m',
        'width':200,'depth':300,'section_unit':'mm','elastic_modulus':30,'modulus_unit':'GPa',
        'geometry_source':'Independent synthetic geometry','material_source':'Synthetic modulus, not measured material',
        'support_basis':'Ideal pin and roller supports for calculation test','analysis_basis':'Constant EI, linear elastic small-deflection synthetic test; no safety assessment.',
        'loads':[{'type':'uniform','name':'Audit UDL','magnitude':10,'unit':'kN/m','start':0,'end':6,'position_unit':'m','source':'Independent synthetic load, self-weight excluded'}]}


def fem(span,e,inertia,points,uniforms,support):
    """Direct stiffness assembly using Hermite beam elements and consistent nodal loads.

    Does not call production normalization, integration, extrema or reaction functions.
    All point loads and patch boundaries become mesh nodes. Downward translations positive.
    """
    xs=np.array(sorted({float(x) for x in np.linspace(0,span,25)}|{a for p,a in points}|{x for q,a,b in uniforms for x in (a,b)}))
    k=np.zeros((2*len(xs),2*len(xs))); force=np.zeros(2*len(xs))
    for i,(a,b) in enumerate(zip(xs,xs[1:])):
        length=b-a
        local=e*inertia/length**3*np.array([[12,6*length,-12,6*length],
            [6*length,4*length**2,-6*length,2*length**2],[-12,-6*length,12,-6*length],
            [6*length,2*length**2,-6*length,4*length**2]])
        ids=np.arange(2*i,2*i+4); k[np.ix_(ids,ids)]+=local
        q=sum(q for q,start,end in uniforms if start<=a and end>=b)
        force[ids]+=q*length/2*np.array([1,length/6,1,-length/6])
    for p,a in points: force[2*list(xs).index(a)]+=p
    fixed=[0,2*(len(xs)-1)] if support=='simply_supported' else [0,1]
    free=[i for i in range(len(force)) if i not in fixed]
    displacement=np.zeros(len(force)); displacement[free]=np.linalg.solve(k[np.ix_(free,free)],force[free])
    reactions=k@displacement-force
    return xs,displacement[::2],displacement[1::2],reactions


@pytest.mark.parametrize('support',['simply_supported','cantilever'])
@pytest.mark.parametrize('kind',['uniform','point'])
def test_fraction_closed_forms_and_boundary_conditions(support,kind):
    b=beam(); b['support']=support
    if kind=='point': b['loads']=[{'type':'point','name':'Point test','magnitude':10,'unit':'kN','position':3 if support=='simply_supported' else 6,'position_unit':'m','source':'Independent synthetic point force'}]
    r=calculate(BeamInput(**b)); m=r['metrics']; inertia=F(1,5)*F(3,10)**3/12; ei=30*10**9*inertia
    if kind=='uniform':
        expected_d=F(5,384)*10000*6**4/ei if support=='simply_supported' else F(1,8)*10000*6**4/ei
        expected_m=45000 if support=='simply_supported' else 180000
    else:
        expected_d=F(1,48)*10000*6**3/ei if support=='simply_supported' else F(1,3)*10000*6**3/ei
        expected_m=15000 if support=='simply_supported' else 60000
    assert m['inertia_m4']==pytest.approx(float(inertia),rel=1e-12)
    assert m['max_deflection_m']==pytest.approx(float(expected_d),rel=1e-12)
    assert m['max_abs_moment_nm']==pytest.approx(expected_m,rel=1e-12)
    assert m['max_elastic_bending_stress_pa']==pytest.approx(expected_m*F(3,20)/inertia)
    assert r['samples'][0]['deflection_down_m']==0
    if support=='simply_supported': assert r['samples'][-1]['deflection_down_m']==0
    else: assert r['samples'][0]['rotation_down_rad']==0
    assert r['samples'][-1]['moment_nm']==pytest.approx(0,abs=1e-9)
    assert abs(r['equilibrium_residual']['force_n'])<1e-9 and abs(r['equilibrium_residual']['moment_nm'])<1e-9
    assert r['structural_safety']==r['code_compliance']=='NOT_ASSESSED'


@pytest.mark.parametrize('support',['simply_supported','cantilever'])
def test_patch_and_eccentric_load_superposition_against_independent_fem(support):
    b=beam(); b['support']=support
    b['loads']=[{'type':'point','name':'P1','magnitude':7.3,'unit':'kN','position':1.75,'position_unit':'m','source':'Independent test source'},
        {'type':'point','name':'P2','magnitude':2.1,'unit':'kN','position':4.25,'position_unit':'m','source':'Independent test source'},
        {'type':'uniform','name':'Q1','magnitude':3.2,'unit':'kN/m','start':.5,'end':3.5,'position_unit':'m','source':'Independent test source'},
        {'type':'uniform','name':'Q2','magnitude':1.7,'unit':'kN/m','start':2,'end':5,'position_unit':'m','source':'Independent test source'}]
    r=calculate(BeamInput(**b)); xs,ys,rotations,reactions=fem(6,30e9,.2*.3**3/12,[(7300,1.75),(2100,4.25)],[(3200,.5,3.5),(1700,2,5)],support)
    # Compare exact shared mesh/curve positions, including all load discontinuities.
    for row in r['samples']:
        matches=np.where(np.isclose(xs,row['x_m'],atol=1e-12,rtol=0))[0]
        if len(matches):
            index=matches[0]
            assert row['deflection_down_m']==pytest.approx(ys[index],rel=2e-8,abs=1e-10)
            assert row['rotation_down_rad']==pytest.approx(rotations[index],rel=2e-8,abs=1e-10)
    assert r['metrics']['left_reaction_n']==pytest.approx(-reactions[0],rel=2e-8)
    assert r['metrics']['right_reaction_n']==pytest.approx(-reactions[-2],abs=1e-6)
    assert r['metrics']['max_deflection_m']>=max(ys)-1e-10
    assert r['metrics']['max_deflection_m']<max(ys)*1.003


def test_force_discontinuities_and_loads_applied_directly_at_supports():
    b=beam(); b['loads']=[{'type':'point','name':'P','magnitude':10,'unit':'kN','position':3,'position_unit':'m','source':'Synthetic position test'}]
    r=calculate(BeamInput(**b)); center=next(x for x in r['samples'] if x['x_m']==3)
    assert center['shear_left_n']==5000 and center['shear_right_n']==-5000
    b['loads'][0]['position']=0; r=calculate(BeamInput(**b))
    assert r['metrics']['left_reaction_n']==10000 and r['metrics']['max_abs_shear_n']==0
    assert r['metrics']['max_abs_moment_nm']==r['metrics']['max_deflection_m']==0
    b['loads'][0]['position']=6; r=calculate(BeamInput(**b))
    assert r['metrics']['right_reaction_n']==10000 and r['metrics']['max_abs_shear_n']==0


def test_unit_equivalence_and_zero_explicit_load():
    b=beam(); expected=calculate(BeamInput(**b))['metrics']
    b.update(span=600,span_unit='cm',elastic_modulus=30000,modulus_unit='MPa')
    b['loads'][0].update(unit='N/mm',start=0,end=6000,position_unit='mm')
    assert calculate(BeamInput(**b))['metrics']==expected
    b['loads'][0]['magnitude']=0; r=calculate(BeamInput(**b))
    assert r['metrics']['max_deflection_m']==0 and r['metrics']['max_abs_moment_nm']==0


@pytest.mark.parametrize('field',['span','width','depth','elastic_modulus'])
def test_missing_properties_do_not_become_zero(field):
    b=beam(); b[field]=None; r=calculate(BeamInput(**b))
    assert r['status']=='incomplete' and r['metrics'] is None and r['missing']


@pytest.mark.parametrize('field,value',[('span',-1),('width',0),('depth',True),('elastic_modulus',0),('span','6'),('span',float('nan')),('span',1e-9)])
def test_invalid_properties_rejected(field,value):
    with pytest.raises(ValidationError): BeamInput(**{**beam(),field:value})


def test_missing_wrong_unit_reversed_and_out_of_span_loads():
    for patch in [{'magnitude':-1},{'unit':'kg'},{'start':5,'end':4},{'end':6000,'position_unit':'m'},{'magnitude':True}]:
        b=beam(); b['loads'][0].update(patch)
        with pytest.raises(ValidationError): BeamInput(**b)
    b=beam(); b['loads'][0]['magnitude']=None
    assert calculate(BeamInput(**b))['metrics'] is None


def test_model_screening_keeps_safety_unassessed():
    b=beam(); b['depth']=1000
    r=calculate(BeamInput(**b)); assert r['status']=='outside_model_screen' and r['model_screening']
    b=beam();b['elastic_modulus']=.01
    r=calculate(BeamInput(**b));assert r['status']=='outside_model_screen' and r['structural_safety']=='NOT_ASSESSED'


def test_api_history_exports_project_staleness_and_cross_project_refusal(client):
    project=create_project(client); base='/api/projects/'+project['project_id']; b=beam()
    response=client.post(base+'/beam-analyses',json=b); assert response.status_code==201,response.text
    r=response.json(); eid=r['engineering_id']; assert r['result']['metrics']['max_deflection_m']==pytest.approx(.0125)
    url=base+'/beam-analyses/'+eid
    assert client.get(url+'/report.html').status_code==200
    b['name']='<script>alert(1)</script>'; x=client.post(base+'/beam-analyses',json=b).json()
    assert '<script>' not in client.get(base+'/beam-analyses/'+x['engineering_id']+'/report.html').text
    other='/api/projects/'+create_project(client)['project_id']
    assert client.get(other+'/beam-analyses/'+eid).status_code==409
    domain=client.app.state.domain; raw=domain.store.get('project',project['project_id'])
    domain.store.put('project',raw,raw['revision'])
    assert client.get(url).json()['result'] is None
    assert domain.store.get('engineering',eid)['result']['metrics']
    client.cookies.clear(); assert client.get(url).status_code==401


def test_evidence_revision_file_tamper_and_immutability(client):
    p=create_project(client)['project_id']; base='/api/projects/'+p; domain=client.app.state.domain
    fid=client.post(base+'/files',files={'file':('source.csv',b'property,value\nE,30GPa\n')}).json()['file_id']
    ev=client.post(base+'/evidence',json={'type':'manual_input','name':'Beam material','source_file':fid,'source_locator':'row2',
        'value':30,'unit':'GPa','authority':'Synthetic author','permission':'Independent test only','status':'IMPORTED',
        'acquisition_method':'Independent synthetic test','responsible_person':'Audit fixture author'}).json()
    b=beam();b['evidence_ids']=[ev['evidence_id']]
    response=client.post(base+'/beam-analyses',json=b); assert response.status_code==201,response.text
    old=response.json(); domain.store.put('evidence',{**ev,'review_state':'rejected','review_note':'Synthetic source review withdrawn'},ev['revision'])
    assert client.get(base+'/beam-analyses/'+old['engineering_id']).json()['status']=='stale'
    assert client.post(base+'/beam-analyses',json=b).status_code==409
    withdrawn=domain.store.get('evidence',ev['evidence_id'])
    domain.store.put('evidence',{**withdrawn,'review_state':'confirmed','review_note':'New explicit review for tamper test'},withdrawn['revision'])
    r=client.post(base+'/beam-analyses',json=b).json()
    _,path=domain.file_record(p,fid);path.write_bytes(b'changed source')
    assert client.get(base+'/beam-analyses/'+r['engineering_id']).json()['status']=='stale'
    assert client.post(base+'/beam-analyses',json=b).status_code==409
    other='/api/projects/'+create_project(client)['project_id']
    assert client.post(other+'/beam-analyses',json=b).status_code==409


def test_superposition_and_short_patch_stability():
    b=beam(); a=calculate(BeamInput(**b))
    b['loads'].append(copy.deepcopy(b['loads'][0])); c=calculate(BeamInput(**b))
    assert c['metrics']['max_deflection_m']==pytest.approx(2*a['metrics']['max_deflection_m'])
    b['support']='cantilever'; b['loads']=b['loads'][:1];b['loads'][0].update(start=.2,end=.20000001,magnitude=1e8,unit='N/m')
    r=calculate(BeamInput(**b)); assert r['metrics']['max_deflection_m']>0
    assert r['metrics']['total_downward_load_n']==pytest.approx(1,rel=1e-7)


def test_eccentric_point_extremum_is_between_samples():
    import math
    b=beam();b['loads']=[{'type':'point','name':'Eccentric force','magnitude':10,'unit':'kN','position':2,'position_unit':'m','source':'Independent exact derivation'}]
    r=calculate(BeamInput(**b));m=r['metrics']
    expected_x=6-math.sqrt((6**2-2**2)/3)
    assert m['max_deflection_at_m']==pytest.approx(expected_x,abs=1e-12)
    assert m['max_moment_at_m']==2 and m['max_abs_moment_nm']==pytest.approx(10000*2*4/6)


def test_agent_reads_current_calculation_and_refuses_foreign_project(client):
    from backend.agent import ToolRefusal
    pid=create_project(client)['project_id']; base='/api/projects/'+pid
    r=client.post(base+'/beam-analyses',json=beam()).json();agent=client.app.state.agent
    assert agent.call(pid,'beam_analysis_list',{},False)['records'][0]['engineering_id']==r['engineering_id']
    read=agent.call(pid,'beam_analysis_read',{'engineering_id':r['engineering_id']},False)
    assert read['result']['metrics']['max_deflection_m']==pytest.approx(.0125)
    assert read['result']['structural_safety']=='NOT_ASSESSED'
    other=create_project(client)['project_id']
    with pytest.raises(ToolRefusal): agent.call(other,'beam_analysis_read',{'engineering_id':r['engineering_id']},False)


@pytest.mark.parametrize('a',[1e-8,1e-12,1e-16])
def test_near_clamp_deflection_avoids_catastrophic_cancellation(a):
    b=beam();b['support']='cantilever';b['loads']=[{'type':'point','name':'Near support','magnitude':10000,'unit':'N','position':a,'position_unit':'m','source':'Independent extreme position test'}]
    r=calculate(BeamInput(**b)); position=F(str(a))
    expected=float(F(10000)*position**2*(18-position)/(6*F(13500000)))
    assert r['samples'][-1]['deflection_down_m']==pytest.approx(expected,rel=2e-14,abs=0)
    assert r['metrics']['max_deflection_m']==pytest.approx(expected,rel=2e-14,abs=0)


@pytest.mark.parametrize('side',['left','right'])
@pytest.mark.parametrize('distance',[1e-8,1e-12])
def test_simply_supported_near_support_moment_and_midspan_deflection(side,distance):
    a=distance if side=='left' else 6-distance
    b=beam();b['loads']=[{'type':'point','name':'Near support','magnitude':10000,'unit':'N','position':a,'position_unit':'m','source':'Independent support limit test'}]
    r=calculate(BeamInput(**b));a_exact=F(a);distance=a_exact if side=='left' else F(6)-a_exact
    # Load on either side, observed at the symmetric midspan.
    expected_m=float(F(10000)*distance/2)
    expected_d=float(F(10000)*distance*3*(36-distance**2-9)/(36*F(13500000)))
    mid=next(row for row in r['samples'] if row['x_m']==3)
    assert mid['moment_nm']==pytest.approx(expected_m,rel=2e-14,abs=0)
    assert mid['deflection_down_m']==pytest.approx(expected_d,rel=2e-14,abs=0)


def test_sub_ulp_patch_at_left_support_retains_deflection_and_rotation():
    b=beam();b['loads'][0].update(magnitude=10000,unit='N/m',start=1e-16,end=2e-16)
    r=calculate(BeamInput(**b));a,c=F(1,10**16),F(2,10**16)
    ei=F(13500000);q=F(10000)
    expected_d=float(q*3/(6*6*ei)*(F(27)*(c*c-a*a)/2-(c**4-a**4)/4))
    expected_rotation=float(q/(6*6*ei)*(2*36*(c*c-a*a)/2-3*6*(c**3-a**3)/3+(c**4-a**4)/4))
    mid=next(row for row in r['samples'] if row['x_m']==3)
    assert mid['deflection_down_m']==pytest.approx(expected_d,rel=2e-14,abs=0)
    assert r['samples'][0]['rotation_down_rad']==pytest.approx(expected_rotation,rel=2e-14,abs=0)


def test_one_ulp_patch_at_right_support_preserves_reaction_and_boundary_shear():
    import math
    start=math.nextafter(6.0,0)
    b=beam();b['loads'][0].update(start=start,end=6.,magnitude=10000,unit='N/m')
    r=calculate(BeamInput(**b));expected=float(F(10000)*(F(6)-F(start))**2/(2*6))
    assert r['metrics']['left_reaction_n']==pytest.approx(expected,rel=2e-14,abs=0)
    assert r['samples'][0]['shear_right_n']==pytest.approx(expected,rel=2e-14,abs=0)
