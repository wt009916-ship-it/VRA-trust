"""Public IFC geometry + declared synthetic loads through an isolated local HTTP server."""
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    reference=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=False)
    acquisition=json.loads((reference/'acquisition.json').read_text())
    for row in acquisition['files']:
        assert hashlib.sha256((reference/row['file']).read_bytes()).hexdigest()==row['sha256']
    # Independently inspected STEP entities, before invoking the new application chain.
    expected={'beam-extruded-solid.ifc':{70:'extracted'},'beam-revolved-solid.ifc':{70:'unsupported'},
              'beam-varying-profiles.ifc':{210:'extracted',307:'extracted'},
              'beam-varying-extrusion-paths.ifc':{210:'extracted',230:'unsupported'}}
    (out/'expected.json').write_text(json.dumps(expected,indent=2),encoding='utf-8')
    oracle=json.loads((ROOT/'fixtures/test/ifc_beam_oracle.json').read_text())
    runtime=Path(tempfile.mkdtemp(prefix='vra-ifc-beam-http-'))
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    checks=[];responses=[];profiles=[]
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    with (out/'server.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env={**os.environ,'VRA_DATA_DIR':str(runtime/'server'),'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=60,event_hooks={'response':[lambda r:responses.append({'method':r.request.method,'path':r.request.url.path,'status':r.status_code})]}) as client:
                for _ in range(100):
                    try:
                        if client.get('/api/health').status_code==200:break
                    except httpx.ConnectError:time.sleep(.1)
                else:raise RuntimeError('Server unavailable')
                login=client.post('/api/auth/register',json={'username':'ifc_profile_http_test','display_name':'Public IFC reference test','password':secrets.token_urlsafe(32)})
                check('isolated registration',login.status_code==200);client.headers['X-CSRF-Token']=login.json()['csrf_token']
                response=client.post('/api/projects',json={'name':'Public geometry with explicitly synthetic beam loads','building':{'use':'reference','location':'not a surveyed building','region':'reference','area_m2':100}})
                check('isolated project',response.status_code==201);project=response.json();base='/api/projects/'+project['project_id']
                for name,ids in expected.items():
                    raw=(reference/name).read_bytes();uploaded=client.post(base+'/files',files={'file':(name,raw)})
                    check(name+' uploaded',uploaded.status_code==201);fid=uploaded.json()['file_id']
                    response=client.post(base+'/cad-inspections',json={'file_id':fid})
                    check(name+' native CAD inspection',response.status_code==201);cad=response.json()
                    for entity,status in ids.items():
                        response=client.post(base+'/ifc-beam-profiles',json={'cad_id':cad['cad_id'],'product_id':entity})
                        check(name+f' entity {entity} profile status',response.status_code==201 and response.json().get('status')==status)
                        profile=response.json();profiles.append(profile)
                        if status=='extracted':
                            check(name+f' entity {entity} mechanics remain missing',all(profile['result'][k] is None for k in ('engineering_span_m','elastic_modulus_pa','supports','loads')))
                        if name=='beam-extruded-solid.ifc':
                            primary=profile
                            for key in ('area_m2','ix_m4','iy_m4'):
                                check('public IPE600 independent '+key,math.isclose(profile['result']['section_properties'][key],oracle[key],rel_tol=1e-10))
                    check(name+' original preserved',client.get(base+'/files/'+fid).content==raw)
                (out/'profiles.json').write_text(json.dumps(profiles,ensure_ascii=False,indent=2),encoding='utf-8')
                evidence=client.post(base+'/evidence',json={'type':'assumption','name':'Declared synthetic loading and supports','source_locator':'Independent acceptance only','authority':'test author','permission':'test only','acquisition_method':'explicit synthetic declaration','responsible_person':'Test author','status':'ASSUMED'})
                check('synthetic mechanical source recorded',evidence.status_code==201);eid=evidence.json()['evidence_id']
                input_body={'name':'Public IPE600 with declared 8m span and 10kN centre load','support':'simply_supported','span':8.,'span_unit':'m','width':None,'depth':None,'section_unit':'m','elastic_modulus':210.,'modulus_unit':'GPa','geometry_source':'Public IPE600 profile; 8m support span is a separate synthetic declaration','material_source':'Synthetic 210GPa modulus, not extracted from material name','support_basis':'Synthetic pin and roller supports, not model connectivity','analysis_basis':'Synthetic constant EI reference calculation, no design resistance or compliance assessment','evidence_ids':[eid],'loads':[{'type':'point','name':'Synthetic centre force','magnitude':10.,'unit':'kN','position':4.,'position_unit':'m','source':'Synthetic test force, no self weight or load combinations'}]}
                body={'expected_profile_hash':primary['hash'],'bending_axis':'x','geometry_reviewed':True,'review_basis':'Independent profile dimensions and local axes checked; mechanical assumptions explicitly synthetic.','analysis':input_body}
                route=base+'/ifc-beam-profiles/'+primary['beamprofile_id']+'/analyses'
                response=client.post(route,json=body);check('reviewed handoff creates actual beam analysis',response.status_code==201)
                calculated=response.json();metric=calculated['result']['metrics'];exact=10000*8**3/(48*210e9*oracle['ix_m4'])
                check('independent beam deflection',math.isclose(metric['max_deflection_m'],exact,rel_tol=1e-10))
                check('beam metrics preserve actual nonrectangular section area',math.isclose(metric['area_m2'],oracle['area_m2'],rel_tol=1e-10))
                check('independent reactions and maximum moment',metric['left_reaction_n']==5000 and metric['right_reaction_n']==5000 and metric['max_abs_moment_nm']==20000)
                check('real actor and no safety certification',calculated['ifc_profile_snapshot']['actor_user_id']==client.get('/api/auth/me').json()['user']['id'] and calculated['result']['structural_safety']=='NOT_ASSESSED')
                eroute=base+'/beam-analyses/'+calculated['engineering_id'];report=client.get(eroute+'/report.html')
                check('source-bound HTML report',report.status_code==200 and primary['hash'] in report.text)
                (out/'calculated.json').write_text(json.dumps(calculated,ensure_ascii=False,indent=2),encoding='utf-8');(out/'report.html').write_text(report.text,encoding='utf-8')
                csrf=client.headers.pop('X-CSRF-Token');check('CSRF enforced',client.post(route,json=body).status_code==403);client.headers['X-CSRF-Token']=csrf
                rejected=client.patch(base+'/evidence/'+eid,json={'expected_revision':1,'review_state':'rejected','responsible_person':'Auditor','review_note':'Synthetic mechanical assumptions withdrawn for acceptance'})
                check('mechanical assumption withdrawn',rejected.status_code==200)
                stale=client.get(eroute).json();check('current engineering result revoked',stale['status']=='stale' and stale['result'] is None)
                check('withdrawn source cannot generate new analysis',client.post(route,json=body).status_code==409)
                (out/'stale.json').write_text(json.dumps(stale,ensure_ascii=False,indent=2),encoding='utf-8')
                client.cookies.clear();check('anonymous report denied',client.get(eroute+'/report.html').status_code==401)
        finally:
            process.terminate();process.wait(timeout=15)
            receipt={'checks':checks,'all_passed':len(checks)>=30 and all(x['passed'] for x in checks),'http_responses':responses,'server_stopped':process.poll() is not None,'scope':'Public IFC reference geometry, synthetic mechanics; not surveyed structures or browser acceptance'}
            (out/'summary.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
            print(json.dumps({'checks':len(checks),'all_passed':receipt['all_passed'],'responses':len(responses),'server_stopped':receipt['server_stopped']}))


if __name__=='__main__':main()
