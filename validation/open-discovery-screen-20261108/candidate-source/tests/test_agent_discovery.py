"""Application protocol and scope guards, never claims about real model ability."""
import copy
import pytest
from pydantic import ValidationError
from backend import agent_discovery as discovery
from backend.agent import Chat
from test_standards import setup, save
from test_agent_contract import scripted, DONE
from test_agent_capabilities import tool


def selection(question,domain='standards',purpose='lookup'):
    return {'scope_selection':{'scopes':[{'domain':domain,'request_quote':question,'purpose':purpose}]}}


def test_frozen_scope_needs_literal_current_question_and_distinct_domains():
    question='Read the wall record'
    body=discovery.Selection.model_validate(selection(question,'thermal','results')['scope_selection'])
    result=discovery.freeze(question,body)
    assert result['origin']=='model_inferred' and not result['intent_coverage_verified']
    with pytest.raises(ValueError):discovery.freeze('Different user request',body)
    with pytest.raises(ValidationError):discovery.Selection(scopes=body.scopes*2)
    with pytest.raises(ValidationError):Chat(message='read',discover_tools=True)


def test_actual_catalog_query_and_revocation_keep_inferred_scope_qualified(client,monkeypatch):
    pid,base,b=setup(client);source=save(client,base,b);a=client.app.state.agent
    question='Read TEST 100 clause 1.0.1 on 2025-01-01'
    captured=scripted(a,monkeypatch,[tool('task_scope_select',selection(question)),tool('standards_catalog',{}),
        tool('standards_search',{'standards_query':{'standard_code':'TEST 100','clause_id':'1.0.1','as_of':'2025-01-01'}}),DONE])
    task=a.start(pid,Chat(message=question,mode='provider',discover_tools=True),background=False)
    assert task['status']=='succeeded',task.get('error')
    answer=task['answer'];assert answer['checked_standards'][0]['result']['citations'][0]['standard_id']==source['standard_id']
    assert answer['task_completion']=='partial'
    assert answer['tool_scope_progress'][0]['state']=='selected_scope_observed'
    assert not answer['tool_scope_progress'][0]['pairing_and_applicability_verified']
    assert '先且只调用task_scope_select' in captured[0][0]['content']
    client.post(base+'/standards/'+source['standard_id']+'/review',json={'expected_revision':source['revision'],'state':'rejected','basis':'Withdraw the test source to verify current answer and scope status.'})
    current=a.view(pid,task['agent_id'])['answer']
    assert not current['checked_standards'] and current['task_completion']=='incomplete'
    assert current['tool_scope_progress'][0]['state']=='pending'


@pytest.mark.parametrize('name,args',[
    ('evidence_validate',{}),
    ('professional_inventory',{'kinds':['thermal']}),
    ('simulation_create',{'scheme_id':'baseline'}),
])
def test_model_cannot_escape_frozen_domain_or_compute_authorization(client,monkeypatch,name,args):
    pid,_,_=setup(client);a=client.app.state.agent;question='Read TEST 100'
    scripted(a,monkeypatch,[tool('task_scope_select',selection(question)),tool(name,args)])
    task=a.start(pid,Chat(message=question,mode='provider',discover_tools=True),background=False)
    assert task['status']=='failed' and not a.store.jobs(pid)
    assert not any(e['tool']==name and e['status']=='succeeded' for e in task['events'])


def test_full_source_code_guard_does_not_convert_prefix_to_missing_result(client,monkeypatch):
    pid,_,b=setup(client);save(client,'/api/projects/'+pid,b);a=client.app.state.agent
    question='Read TEST 100 clause 1.0.1'
    scripted(a,monkeypatch,[tool('task_scope_select',selection(question)),tool('standards_catalog',{}),
        tool('standards_search',{'standards_query':{'standard_code':'TEST','clause_id':'1.0.1','as_of':'2025-01-01'}}),
        tool('standards_search',{'standards_query':{'standard_code':'TEST 100','clause_id':'1.0.1','as_of':'2025-01-01'}}),DONE])
    task=a.start(pid,Chat(message=question,mode='provider',discover_tools=True),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert any(e['tool']=='standards_search' and e['status']=='failed' and 'full user-requested' in e['error'] for e in task['events'])
    assert task['answer']['checked_standards'][0]['result']['citations']


def test_progress_requires_every_mentioned_code_and_clause_without_claiming_pairing():
    q='Compare TEST 100 1.0.1 with TEST 200 2.0.2'
    r={'question':q,'events':[], 'tool_scope':discovery.freeze(q,discovery.Selection.model_validate(selection(q)['scope_selection']))}
    answer={'checked_standards':[{'result':{'query':{'standard_code':'TEST 100','clause_id':'1.0.1'}}}]}
    row=discovery.progress(r,answer)[0]
    assert row['state']=='pending' and row['missing_codes']==['test200'] and row['missing_clauses']==['2.0.2']
    assert not row['pairing_and_applicability_verified']


def test_source_catalog_bounds_and_declared_unknown_code_retained(client):
    pid,base,b=setup(client);save(client,base,b);a=client.app.state.agent
    found=discovery.catalog(a.domain,pid)
    assert found['complete'] and found['standards'][0]['standard_code']=='TEST 100'
    assert 'text' not in found['standards'][0]
    r={'question':'Read TEST 999 4.0.1','events':[{'tool':'standards_catalog','status':'succeeded','result':found}]}
    assert discovery.query_codes(r)==['TEST 100','TEST 999']
    from backend.standards import Query
    original=Query.model_json_schema();before=copy.deepcopy(original)
    schema=discovery.query_schema(original,r)
    assert set(schema)=={'oneOf'} and original==before
    assert schema['oneOf'][0]['properties']['standard_code']['anyOf'][0]['enum']==['TEST 100','TEST 999']


def test_professional_absence_progress_uses_each_verified_reference_kind():
    q='Check whether thermal and schedule records exist'
    selection=discovery.Selection(scopes=[discovery.Scope(domain=k,request_quote=q,purpose='availability') for k in ['thermal','schedule']])
    r={'question':q,'events':[],'tool_scope':discovery.freeze(q,selection),
       'missing_deliveries':[{'request':{'kind':'thermal'}},{'request':{'kind':'schedule'}}]}
    assert all(x['state']=='selected_scope_observed' for x in discovery.progress(r))
    assert discovery.attach({'task_completion':'incomplete'},{**r,'discover_tools':True})['task_completion']=='incomplete'


def test_text_form_cannot_bypass_explicit_source_scope():
    from backend.standards import Query
    r={'question':'Read TEST 100 clause 1.0.1','events':[{'tool':'standards_catalog','status':'succeeded',
       'result':{'standards':[{'standard_code':'TEST 100'},{'standard_code':'TEST 200'}]}}]}
    with pytest.raises(ValueError,match='outside'):
        discovery.validate_query(r,Query(text='TEST 200 clause 1.0.1',as_of='2025-01-01'))
    discovery.validate_query(r,Query(text='TEST 100 clause 1.0.1',as_of='2025-01-01'))


def test_legacy_single_kind_missing_argument_cannot_bypass_selected_profession(client,monkeypatch):
    pid,_,_=setup(client);a=client.app.state.agent;q='Check whether a thermal record exists'
    scripted(a,monkeypatch,[tool('task_scope_select',selection(q,'thermal','availability')),
        tool('professional_missing',{'missing':{'kind':'lifecycle','finish':True}})])
    task=a.start(pid,Chat(message=q,mode='provider',discover_tools=True),background=False)
    assert task['status']=='failed'
    assert 'exceed inferred task scope' in task['error']
    assert not task['missing_deliveries']
