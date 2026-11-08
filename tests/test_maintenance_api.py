import concurrent.futures
import pytest
from fastapi.testclient import TestClient
from backend import core
from backend.maintenance import Maintenance, OrderAction
from test_api import create_project
from test_maintenance_recheck import record


def setup(client,tmp_path):
    pid=create_project(client)['project_id'];base='/api/projects/'+pid
    operations=[]
    for name,hour,values in [('before',0,[25,33,34,35,25]),('after',1,[28,27,26,27])]:
        fixture=record(tmp_path,name,hour=hour,values=values)
        f=client.post(base+'/files',files={'file':(name+'.csv',(tmp_path/(name+'.csv')).read_bytes())})
        assert f.status_code==201,f.text
        body=fixture['input'];body['file_id']=f.json()['file_id']
        r=client.post(base+'/operations',json=body);assert r.status_code==201,r.text
        operations.append(r.json())
    evidence=client.post(base+'/evidence',json={'type':'literature','name':'Synthetic repair and mapping record','source_locator':'test journal',
        'authority':'Synthetic technician','permission':'test only','acquisition_method':'synthetic','responsible_person':'Technician','status':'ASSUMED'}).json()
    r=client.post(base+'/maintenance-orders',json={'name':'Synthetic maintenance','operation_id':operations[0]['operation_id'],'rule_id':'hot','event_index':0,'minimum_observation_seconds':120,'observation_basis':'Synthetic predeclared observation window with unchanged sensor and conditions','responsible_person':'Technician'})
    assert r.status_code==201,r.text
    return pid,base,operations,evidence,r.json()


def payload(order,action,**extra):
    return {'expected_revision':order['revision'],'action':action,'note':'Independent synthetic maintenance review, not a field repair certificate','responsible_person':'Technician',**extra}


def act(client,base,order,action,**extra):
    r=client.post(base+'/maintenance-orders/'+order['maintenance_id']+'/actions',json=payload(order,action,**extra))
    assert r.status_code==200,r.text
    return r.json()


def work(client,base,order,evidence):
    order=act(client,base,order,'triage')
    return act(client,base,order,'record_work',evidence_ids=[evidence['evidence_id']],work_completed_at='2026-01-01T00:30:00Z')


def close(client,base,order,ops,evidence):
    order=work(client,base,order,evidence)
    order=act(client,base,order,'recheck',after_operation_id=ops[1]['operation_id'])
    assert order['state']=='rechecked'
    return act(client,base,order,'close',evidence_ids=[evidence['evidence_id']],same_equipment_and_conditions=True)


def test_real_api_full_history_report_and_reopen(client,tmp_path):
    pid,base,ops,ev,initial=setup(client,tmp_path)
    closed=close(client,base,initial,ops,ev)
    assert closed['state']=='closed_under_declared_rule' and closed['revision']==5
    assert closed['recheck']['data_nature']=='synthetic' and closed['equipment_health']=='NOT_ASSESSED'
    assert not closed['cause_confirmed']
    assert len({a['actor_user_id'] for a in closed['actions']})==1
    assert closed['actions'][0]['actor_user_id']!='Technician'
    assert client.app.state.domain.store.get('maintenance',initial['maintenance_id'],1)['state']=='open'
    report=client.get(base+'/maintenance-orders/'+closed['maintenance_id']+'/report.html')
    assert report.status_code==200 and '不是设备健康' in report.text
    reopened=act(client,base,closed,'reopen')
    assert reopened['state']=='triaged' and reopened['recheck'] is None and reopened['work_completed_at'] is None


@pytest.mark.parametrize('fault',['jump','no_evidence','forged_actor','csrf','wrong_revision','cross_project'])
def test_mutation_guards(client,tmp_path,fault):
    pid,base,ops,ev,order=setup(client,tmp_path)
    url=base+'/maintenance-orders/'+order['maintenance_id']+'/actions';body=payload(order,'triage');expected=422
    if fault=='jump':body=payload(order,'close',same_equipment_and_conditions=True,evidence_ids=[ev['evidence_id']]);expected=409
    elif fault=='no_evidence':body=payload(order,'record_work',work_completed_at='2026-01-01T00:30:00Z')
    elif fault=='forged_actor':body['actor_user_id']='someone-else'
    elif fault=='csrf':client.headers.pop('X-CSRF-Token');expected=403
    elif fault=='wrong_revision':body['expected_revision']=100;expected=409
    elif fault=='cross_project':url='/api/projects/'+create_project(client)['project_id']+'/maintenance-orders/'+order['maintenance_id']+'/actions';expected=409
    r=client.post(url,json=body);assert r.status_code==expected,r.text
    assert client.app.state.domain.store.get('maintenance',order['maintenance_id'])['revision']==1


@pytest.mark.parametrize('source',['evidence','original_file','recheck_file'])
def test_closed_current_result_revoked_without_erasing_history(client,tmp_path,source):
    pid,base,ops,ev,order=setup(client,tmp_path);closed=close(client,base,order,ops,ev)
    if source=='evidence':
        r=client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected','responsible_person':'Auditor','review_note':'Synthetic maintenance evidence withdrawn'})
        assert r.status_code==200
    else:
        op=ops[0 if source=='original_file' else 1]
        _,path=client.app.state.domain.file_record(pid,op['input']['file_id']);path.write_bytes(b'corrupt source')
    url=base+'/maintenance-orders/'+closed['maintenance_id']
    stale=client.get(url).json();assert stale['status']=='stale' and stale['recheck'] is None and stale['stale_reasons']
    stored=client.app.state.domain.store.get('maintenance',closed['maintenance_id'])
    assert stored['state']=='closed_under_declared_rule' and stored['recheck']['eligible_for_human_closure']
    assert client.post(url+'/actions',json=payload(closed,'reopen')).status_code==409


def test_concurrent_actions_have_one_winner(client,tmp_path):
    pid,base,ops,ev,order=setup(client,tmp_path);service=Maintenance(client.app.state.domain)
    action=OrderAction(**payload(order,'triage'))
    def attempt():
        try:return service.act(pid,order['maintenance_id'],action,'test-service-actor')['revision']
        except core.ValidationError:return 'conflict'
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
    assert sorted(results,key=str)==[2,'conflict']
    assert len(service.view(pid,order['maintenance_id'])['actions'])==2


def test_other_account_and_anonymous_denied(client,tmp_path):
    pid,base,ops,ev,order=setup(client,tmp_path);url=base+'/maintenance-orders/'+order['maintenance_id']
    other=TestClient(client.app)
    assert other.get(url).status_code==401
    login=other.post('/api/auth/register',json={'username':'other_owner','display_name':'Other owner','password':'Other-test-only-password-2026'})
    assert login.status_code==200,login.text
    other.headers['X-CSRF-Token']=login.json()['csrf_token']
    assert other.get(url).status_code==404
    assert other.get(url+'/report.html').status_code==404
    assert other.post(url+'/actions',json=payload(order,'triage')).status_code==404
    other.close()


@pytest.mark.parametrize('fault',['source_race','changed_rule','reused_original'])
def test_write_boundary_refuses_changed_sources_or_fake_recheck(client,tmp_path,monkeypatch,fault):
    pid,base,ops,ev,order=setup(client,tmp_path);order=work(client,base,order,ev)
    target=ops[1]['operation_id']
    if fault=='changed_rule':
        body=ops[1]['input'];body['rules'][0]['upper']=40
        fresh=client.post(base+'/operations',json=body);assert fresh.status_code==201
        target=fresh.json()['operation_id']
    elif fault=='reused_original':target=ops[0]['operation_id']
    else:
        original=Maintenance._put
        def raced(service,con,record,expected):
            _,path=service.domain.file_record(pid,ops[1]['input']['file_id']);path.write_bytes(b'changed between compare and persist')
            return original(service,con,record,expected)
        monkeypatch.setattr(Maintenance,'_put',raced)
    result=client.post(base+'/maintenance-orders/'+order['maintenance_id']+'/actions',json=payload(order,'recheck',after_operation_id=target))
    assert result.status_code==409,result.text
    saved=client.app.state.domain.store.get('maintenance',order['maintenance_id'])
    assert saved['revision']==3 and saved['state']=='work_recorded' and saved['recheck'] is None
