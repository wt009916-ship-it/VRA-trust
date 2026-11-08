"""Independent synthetic documents; no fabricated rule is an actual regulation."""
import copy
import pytest
from pydantic import ValidationError
from backend.standards import Query, Standards
from backend.agent import Chat
from test_standards import setup, save
from test_api import create_project
from test_agent_contract import scripted
from test_agent_capabilities import tool


def target(key, code='TEST 100', clause='1.0.1', edition='2024'):
    return dict(key=key, standard_code=code, edition=edition, clause_id=clause)


def batch(*targets):
    return {'as_of':'2025-01-01','targets':list(targets)}


def corpus(client):
    pid,base,b=setup(client)
    first=save(client,base,b)
    other=copy.deepcopy(b);other.update(standard_code='TEST 200',jurisdiction='OTHER REGION')
    other['clauses']=[other['clauses'][1]]
    second=save(client,base,other)
    return pid,base,first,second


def test_batch_keeps_exact_pairing_and_missing_row_without_fuzzy_substitution(client,monkeypatch):
    pid,base,a,b=corpus(client)
    service=Standards(client.app.state.agent.domain);original=service.catalog;calls=[]
    def catalog(pid):
        calls.append(pid);return original(pid)
    monkeypatch.setattr(service,'catalog',catalog)
    body=Query(**batch(target('a'),target('b','TEST 200','2.0.1'),target('missing','TEST 200','1.0.1')))
    result=service.search(pid,body)
    assert calls==[pid] and result['status']=='PARTIAL_TARGETS_FOUND'
    assert [r['status'] for r in result['targets']]==['CITATIONS_FOUND','CITATIONS_FOUND','NOT_FOUND_IN_REVIEWED_INDEX']
    assert [(c['target_key'],c['standard_id'],c['clause_id'],c['pdf_page']) for c in result['citations']]==[
        ('a',a['standard_id'],'1.0.1',1),('b',b['standard_id'],'2.0.1',2)]
    assert all(r['catalog_hash']==result['catalog_hash'] for r in result['targets'])
    assert not result['targets'][2]['citations']


def test_conflict_in_one_standard_does_not_erase_other_target_or_accept_requested_edition(client):
    pid,base,a,b=corpus(client)
    duplicate=copy.deepcopy(a['input']);duplicate['edition']='2025';save(client,base,duplicate)
    r=client.post(base+'/standard-queries',json=batch(target('a'),target('b','TEST 200','2.0.1')))
    assert r.status_code==201
    result=r.json()['result'];assert result['status']=='PARTIAL_TARGETS_FOUND'
    assert result['targets'][0]['status']=='VERSION_CONFLICT' and not result['targets'][0]['citations']
    assert result['targets'][1]['citations'][0]['standard_id']==b['standard_id']


def test_expired_and_unknown_editions_do_not_substitute_or_hide_targets(client):
    pid,base,a,b=corpus(client)
    obsolete=copy.deepcopy(a['input']);obsolete.update(standard_code='TEST 300',retired_on='2024-12-31');save(client,base,obsolete)
    result=client.post(base+'/standard-queries',json=batch(target('old','TEST 300'),target('unknown','TEST 200','2.0.1','2099'))).json()['result']
    assert result['status']=='NO_TARGETS_FOUND' and len(result['targets'])==2
    assert result['targets'][0]['excluded'][0]['reason']=='RETIRED'
    assert not result['citations']


@pytest.mark.parametrize('body',[
    batch(target('a'),target('a','TEST 200')),
    batch(target('a'),target('b','test 100')),
    {**batch(target('a')),'text':'GB 12345-2024 9.9.9'},
    {**batch(target('a')),'standard_code':'OTHER'},
    batch(*[target(str(i),'TEST '+str(100+i)) for i in range(9)]),
    batch({**target('a'),'clause_id':' '})
])
def test_batch_ambiguous_or_unbounded_contract_rejected(body):
    with pytest.raises(ValidationError):Query(**body)


def test_eight_exact_targets_all_return_even_with_small_single_query_limit(client):
    pid,base,a,b=corpus(client)
    # Distinct missing clause IDs keep all 8 requests visible; no truncation to limit=1.
    body={**batch(*[target(str(i),clause=f'9.0.{i+1}') for i in range(8)]),'limit':1}
    result=client.post(base+'/standard-queries',json=body).json()['result']
    assert len(result['targets'])==8 and result['status']=='NO_TARGETS_FOUND'


def test_saved_batch_retracts_all_quotes_on_review_change_and_is_project_bound(client):
    pid,base,a,b=corpus(client)
    record=client.post(base+'/standard-queries',json=batch(target('a'),target('b','TEST 200','2.0.1'))).json()
    path=base+'/standard-queries/'+record['normquery_id']
    assert client.get(path).json()['status']=='current'
    other=create_project(client)['project_id']
    assert client.get('/api/projects/'+other+'/standard-queries/'+record['normquery_id']).status_code==409
    assert client.post(base+'/standards/'+a['standard_id']+'/review',json={'expected_revision':a['revision'],'state':'rejected','basis':'Synthetic withdrawal; preserve original source.'}).status_code==200
    assert client.get(path).json()['status']=='stale' and client.get(path).json()['result'] is None
    assert client.app.state.agent.store.get('normquery',record['normquery_id'])['result']['citations']


def test_real_agent_tool_pipeline_exposes_only_source_bound_citations_and_rechecks_history(client,monkeypatch):
    pid,base,a,b=corpus(client);agent=client.app.state.agent
    body=batch(target('a'),target('b','TEST 200','2.0.1'),target('none','TEST 900','9.9.9'))
    scripted(agent,monkeypatch,[tool('standards_search',{'standards_query':body}),{'role':'assistant','content':'Fake claim: all regulations passed.'}])
    task=agent.start(pid,Chat(message='Compare the declared synthetic references',mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert task['llm_commentary_policy']=='audit_only' and task['answer']['task_completion']=='partial'
    checked=task['answer']['checked_standards'];assert len(checked)==1
    assert checked[0]['result']['status']=='PARTIAL_TARGETS_FOUND'
    assert [(c['standard_id'],c['pdf_page']) for c in checked[0]['result']['citations']]==[(a['standard_id'],1),(b['standard_id'],2)]
    assert not agent.store.list('normquery',pid)  # Agent search remains read-only.
    client.post(base+'/standards/'+a['standard_id']+'/review',json={'expected_revision':a['revision'],'state':'rejected','basis':'Synthetic source withdrawal for task history.'})
    current=agent.view(pid,task['agent_id'])
    assert not current['answer']['checked_standards']
    assert current['answer']['standard_query_coverage']=='incomplete'
    assert not current['answer']['standard_query_progress'][0]['outcome']
    assert agent.store.get('agent',task['agent_id'])['answer']['checked_standards']  # audit snapshot unchanged


def test_source_loss_and_tampered_event_do_not_create_current_agent_citations(client,monkeypatch):
    pid,base,a,b=corpus(client);agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('standards_search',{'standards_query':batch(target('a'))}),{'role':'assistant','content':'Done'}])
    task=agent.start(pid,Chat(message='Read exact synthetic clause',mode='provider'),background=False)
    from backend import agent_standards
    fake=copy.deepcopy(task)
    event=agent_standards.searches(fake)[0];event['result']['citations'][0]['text']='FORGED QUOTE'
    assert not agent_standards.attach({},agent.domain,pid,fake)['checked_standards']
    def unavailable(self,pid):raise OSError('synthetic source read failure')
    monkeypatch.setattr(Standards,'catalog',unavailable)
    assert not agent_standards.attach({},agent.domain,pid,task)['checked_standards']


def test_batch_query_api_csrf_and_authentication_remain_enforced(client):
    pid,base,b=setup(client);save(client,base,b)
    client.headers.pop('X-CSRF-Token')
    assert client.post(base+'/standard-queries',json=batch(target('a'))).status_code==403
    client.cookies.clear()
    assert client.post(base+'/standard-queries',json=batch(target('a'))).status_code==401


def test_published_schema_expresses_batch_single_exclusivity_and_retains_bounds():
    schema = Query.model_json_schema()
    single, many = schema['oneOf']
    assert single['properties']['targets']['maxItems'] == 0
    assert many['required'] == ['targets'] and many['properties']['targets']['minItems'] == 1
    assert many['properties']['text'] == {'const': ''}
    assert all(many['properties'][k] == {'type':'null'} for k in ['standard_code','edition','clause_id'])
    assert schema['properties']['targets']['maxItems'] == 8
    assert schema['$defs']['ExactTarget']['additionalProperties'] is False
    assert schema['additionalProperties'] is False
