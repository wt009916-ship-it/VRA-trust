"""Scope/reason adversaries with real records; scripted protocol fixtures are not live model tests."""
import copy
import json
from typing import get_args

import pytest

from backend import agent_capabilities as cap
from backend.agent import Chat
from backend.engineering import Engineering, BeamInput
from test_api import create_project
from test_engineering import beam
from test_agent_contract import scripted, call, DONE
from test_agent_professional import create_record
from test_agent_semantics import delivery


def explanation(ids,finish=True):
    c=cap.catalog(ids)
    return {'catalog_hash':c['catalog_hash'],'claims':[{k:r[k] for k in ('capability_id','assessment','reason_code')} for r in c['capabilities']], 'finish':finish}


def tool(name,args):return call(name,json.dumps(args))


def test_catalog_covers_declared_ids_and_distinguishes_scope_from_readiness():
    assert set(get_args(cap.CapabilityId))==set(cap.ENTRIES)
    for key in cap.ENTRIES:
        row=cap.catalog([key])['capabilities'][0]
        assert row['project_readiness']=='NOT_ASSESSED' and row['source_hash']
        assert row['assessment']==('supported_with_limits' if cap.ENTRIES[key][2] else 'not_supported')
    for ids in (None,[],['beam_analysis']*2,['unknown'],list(cap.ENTRIES)[:5]):
        with pytest.raises(ValueError):cap.catalog(ids)


def test_existing_complete_beam_cannot_unlock_safety_certificate(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    r=Engineering(a.domain).save(pid,BeamInput.model_validate(beam()))
    assert r['status']=='calculated' and r['result']['structural_safety']=='NOT_ASSESSED'
    ids=['beam_analysis','structural_safety_certification']
    scripted(a,monkeypatch,[tool('capability_lookup',{'capability_ids':ids}),tool('capability_explain',{'capability_explanation':explanation(ids)})])
    task=a.start(pid,Chat(message='有完整梁记录，是否能认证安全？',mode='provider'),background=False)
    assert task['status']=='succeeded' and task['answer']['task_completion']=='partial'
    rows=task['answer']['capability_assessments']
    assert [r['assessment'] for r in rows]==['supported_with_limits','not_supported']
    assert rows[1]['reason_code']=='outside_application_scope' and '齐全' in rows[1]['scope']
    assert task['events'][-1]['tool']=='capability_lookup' and not task['answer']['can_recommend']
    assert len(a.store.list('engineering',pid))==1


@pytest.mark.parametrize('change',[{'assessment':'supported_with_limits'},{'reason_code':'implemented_bounded_method'}])
def test_model_cannot_misclassify_unsupported_or_change_reason(client,monkeypatch,change):
    pid=create_project(client)['project_id'];a=client.app.state.agent;ids=['carbon_credit_issuance']
    good=explanation(ids);wrong=copy.deepcopy(good);wrong['claims'][0].update(change)
    captured=scripted(a,monkeypatch,[tool('capability_lookup',{'capability_ids':ids}),
        tool('capability_explain',{'capability_explanation':wrong}),tool('capability_explain',{'capability_explanation':good})])
    task=a.start(pid,Chat(message='数据齐全后签发碳信用',mode='provider'),background=False)
    assert task['status']=='succeeded' and task['recovery_attempts']==1
    correction=json.loads(captured[2][-1]['content'])['corrections'][0]['expected']
    assert correction=={'assessment':'not_supported','reason_code':'outside_application_scope'}
    assert task['answer']['capability_assessments'][0]['assessment']=='not_supported'


def test_missing_data_is_not_a_valid_reason_for_unsupported_capability():
    payload=explanation(['structural_safety_certification']);payload['claims'][0]['reason_code']='missing_project_data'
    with pytest.raises(ValueError):cap.Explanation.model_validate(payload)
    payload=explanation(['thermal_resistance']);payload['claims'][0].update(assessment='not_supported',reason_code='outside_application_scope')
    with pytest.raises(cap.CapabilityMismatch):cap.check(cap.Explanation.model_validate(payload))


def test_lookup_required_and_other_read_does_not_authorize_claim(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    for sequence in ([tool('capability_explain',{'capability_explanation':explanation(['carbon_credit_issuance'])}),DONE],
        [tool('capability_lookup',{'capability_ids':['beam_analysis']}),tool('capability_explain',{'capability_explanation':explanation(['structural_safety_certification'])}),DONE]):
        scripted(a,monkeypatch,sequence)
        t=a.start(pid,Chat(message='Skip reading capability scope',mode='provider'),background=False)
        assert not t.get('capability_delivery') and not t['answer'].get('capability_assessments')


def test_history_revalidates_catalog_without_rewriting_old_answer(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;ids=['drawing_structural_reconstruction']
    scripted(a,monkeypatch,[tool('capability_lookup',{'capability_ids':ids}),tool('capability_explain',{'capability_explanation':explanation(ids)})])
    t=a.start(pid,Chat(message='Infer missing structural drawing facts',mode='provider'),background=False)
    old=a.store.get('agent',t['agent_id']);original=cap.catalog
    def changed(ids):return {**original(ids),'catalog_hash':'0'*64}
    monkeypatch.setattr(cap,'catalog',changed)
    current=a.view(pid,t['agent_id'])
    assert current['answer']['task_completion']=='incomplete' and not current['answer']['capability_assessments']
    assert current['historical_task_completion']=='partial' and a.store.get('agent',t['agent_id'])==old


def test_final_catalog_read_failure_does_not_repeat_unverified_scope(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;ids=['site_safety_approval']
    scripted(a,monkeypatch,[tool('capability_lookup',{'capability_ids':ids}),tool('capability_explain',{'capability_explanation':explanation(ids)})])
    original=a.call;lookups=0
    def failed(pid,name,args,allow,**kw):
        nonlocal lookups
        if name=='capability_lookup':
            lookups+=1
            if lookups==2:raise ValueError('Catalog temporarily unavailable')
        return original(pid,name,args,allow,**kw)
    monkeypatch.setattr(a,'call',failed)
    t=a.start(pid,Chat(message='Approve site safety',mode='provider'),background=False)
    assert t['status']=='succeeded' and not t['answer']['capability_assessments']
    assert t['answer']['task_completion']=='not_assessed'
    assert not t['answer']['verification'][-1]['passed']


def test_mixed_numerical_delivery_and_boundary_are_separately_verified(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    ids=['energy_compliance_certification'];d=delivery(r);d['finish']=True
    calls=[tool('professional_deliver',{'delivery':d})['tool_calls'][0],tool('capability_explain',{'capability_explanation':explanation(ids)})['tool_calls'][0]]
    calls[1]['id']='second'
    scripted(a,monkeypatch,[tool('capability_lookup',{'capability_ids':ids}),tool('thermal_read',{'thermal_id':r['thermal_id']}),{'role':'assistant','tool_calls':calls}])
    t=a.start(pid,Chat(message='R result and can it certify the whole building?',mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['checked_statements'][0]['facts'][0]['value']=='1.97'
    assert t['answer']['capability_assessments'][0]['assessment']=='not_supported'
    assert len(t['events'])<=15 and all(c['passed'] for c in t['answer']['verification'])


@pytest.mark.parametrize('objective',['inspect_evidence','inspect_thermal','inspect_lifecycle','inspect_material_cost'])
def test_explicit_read_only_objective_cannot_be_replaced_with_capability_explanation(client,monkeypatch,objective):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('capability_lookup',{'capability_ids':['beam_analysis']})])
    t=a.start(pid,Chat(message='change task',mode='provider',objective=objective),background=False)
    assert t['status']=='failed' and not t.get('capability_delivery')


def test_dynamic_schema_only_allows_capabilities_actually_read(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;captured=[];ids=['beam_analysis','structural_safety_certification']
    def complete(messages,tools):
        captured.append(tools)
        return tool('capability_lookup',{'capability_ids':ids}) if len(captured)==1 else tool('capability_explain',{'capability_explanation':explanation(ids)})
    monkeypatch.setattr(a.gateway,'public',lambda:{'enabled':True,'key_configured':True});monkeypatch.setattr(a.gateway,'complete',complete)
    t=a.start(pid,Chat(message='梁分析与安全认证有何区别',mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert not any(x['function']['name']=='capability_explain' for x in captured[0])
    schema=next(x['function']['parameters'] for x in captured[1] if x['function']['name']=='capability_explain')
    assert schema['$defs']['Claim']['properties']['capability_id']['enum']==sorted(ids)
    assert 'finish' in schema['$defs']['Explanation']['required']


def test_read_then_prose_requests_actual_model_delivery_once(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;ids=['carbon_credit_issuance']
    captured=scripted(a,monkeypatch,[tool('capability_lookup',{'capability_ids':ids}),DONE,
        tool('capability_explain',{'capability_explanation':explanation(ids)})])
    t=a.start(pid,Chat(message='Can the app issue a credit?',mode='provider'),background=False)
    assert t['status']=='succeeded' and t['capability_delivery_reminded']
    assert len(captured)==3 and 'capability_explain' in captured[2][-1]['content']
    assert t['answer']['capability_assessments'][0]['assessment']=='not_supported'
    assert sum(e['tool']=='capability_explain' and e['origin']=='model' for e in t['events'])==1
    assert t['llm_commentary']==DONE['content'] and 'invented' not in json.dumps(t['answer'])
