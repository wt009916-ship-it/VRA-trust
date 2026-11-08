"""Real services and explicit scripted plans; not a live-model score."""
import copy

import pytest

from backend.agent import Chat
from backend.agent_outputs import OutputItem
from backend import agent_reviews, agent_outputs
from test_api import create_project
from test_agent_professional import create_record
from test_agent_read_execution import scope
from test_agent_contract import scripted
from test_agent_capabilities import tool


def item(key, facts=(), topics=('status',), **extra):
    return dict(request_key=key, question_fragment_ids=['q1'], fact_keys=list(facts),
                explanation_topics=list(topics), **extra)


def run(client, monkeypatch, pid, requests, items, **options):
    a=client.app.state.agent
    scripted(a, monkeypatch, [tool('requested_output_plan', {'output_plan':items})])
    task=a.start(pid, Chat(message='Inspect only the requested fields or status.', mode='provider',
        read_requests=requests, **options), background=False)
    assert task['status']=='succeeded', task.get('error')
    return task


@pytest.mark.parametrize('kind',['thermal','lifecycle'])
@pytest.mark.parametrize('topic',['status','scope','area','period','meaning','history'])
def test_nonnumeric_review_delivers_requested_topic_and_no_numeric_artifact(client, monkeypatch, kind, topic):
    pid=create_project(client)['project_id']; r=create_record(client,pid,kind)
    t=run(client,monkeypatch,pid,[scope(kind,r)],[item(kind,topics=[topic])])
    a=t['answer']; review=a['checked_reviews'][0]
    assert not a.get('checked_statements') and not a.get('artifacts')
    assert a['output_contract_coverage']=='fulfilled' and a['task_completion']=='partial'
    assert a['read_request_progress'][0]['state']=='source_review_verified'
    assert review['record_hash']==r['hash'] and review['numeric_values_delivered'] is False
    assert [e['topic'] for e in a['requested_outputs'][0]['explanations']]==[topic]
    assert review['view_hash']==t['professional_reviews'][0]['view_hash']
    assert not a['can_recommend'] and not a['output_plan']['intent_verified']
    tools=[e['tool'] for e in t['events']]
    assert tools.count(kind+'_read')==2 and tools.count('professional_review')==1
    assert 'professional_deliver' not in tools and 'professional_limit' not in tools


def test_mixed_numeric_review_and_clarification_preserve_each_scope(client, monkeypatch):
    pid=create_project(client)['project_id']; wall=create_record(client,pid,'thermal')
    carbon=create_record(client,pid,'lifecycle'); other=create_record(client,pid,'thermal')
    requests=[scope('thermal',wall,'number'),scope('lifecycle',carbon,'explain'),scope('thermal',other,'ask')]
    t=run(client,monkeypatch,pid,requests,[item('number',['u_w_m2k'],[]),item('explain',topics=['scope']),
        item('ask',topics=[],clarification_reason='conflicting_request',clarification_question='Which of the conflicting requests should apply?')])
    a=t['answer']
    assert [r['record_id'] for r in a['checked_statements']]==[wall['thermal_id']]
    assert [r['record_id'] for r in a['checked_reviews']]==[carbon['lifecycle_id']]
    assert [r['state'] for r in a['read_request_progress']]==['result_verified','source_review_verified','needs_clarification']
    assert a['output_contract_coverage']=='needs_clarification' and a['read_request_coverage']=='incomplete'
    assert a['task_completion']=='partial' and len(a['clarification_requests'])==1
    assert not any(e['tool']=='thermal_read' and e['arguments'].get('thermal_id')==other['thermal_id'] for e in t['events'])
    assert len(t['events'])<=15


def test_only_clarification_is_incomplete_without_any_source_numbers_or_reads(client, monkeypatch):
    pid=create_project(client)['project_id']; r=create_record(client,pid,'lifecycle')
    t=run(client,monkeypatch,pid,[scope('lifecycle',r)],[item('lifecycle',topics=[],
        clarification_reason='metric_not_available',clarification_question='Do you need a new annual calculation?')])
    assert t['answer']['task_completion']=='incomplete'
    assert not t['answer'].get('checked_statements') and not t['answer']['checked_reviews']
    assert not any(e['tool'] in {'lifecycle_read','professional_deliver','calculation_execute'} for e in t['events'])
    assert t['answer']['clarification_requests'][0]['origin']=='model_inferred_unresolved_request'


@pytest.mark.parametrize('stale_before',[True,False])
def test_status_snapshot_is_rechecked_without_overwriting_history(client, monkeypatch, stale_before):
    project=create_project(client);pid=project['project_id'];r=create_record(client,pid,'thermal')
    def change():
        p=client.get(f'/api/projects/{pid}').json()
        assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':p['revision'],
            'building':{**p['building'],'area_m2':p['building']['area_m2']+100}}).status_code==200
    if stale_before:change()
    t=run(client,monkeypatch,pid,[scope('thermal',r)],[item('thermal')]);a=client.app.state.agent
    assert t['answer']['checked_reviews'][0]['status']==('stale' if stale_before else 'calculated')
    saved=copy.deepcopy(a.store.get('agent',t['agent_id']))
    change(); current=a.view(pid,t['agent_id'])
    assert not current['answer']['checked_reviews'] and current['answer']['review_failures']
    assert current['answer']['output_contract_coverage']=='incomplete'
    assert a.store.get('agent',t['agent_id'])==saved


def test_changed_review_contract_withdraws_old_explanations(client,monkeypatch):
    pid=create_project(client)['project_id'];r=create_record(client,pid,'thermal')
    t=run(client,monkeypatch,pid,[scope('thermal',r)],[item('thermal')])
    monkeypatch.setattr(agent_outputs,'version',lambda:'changed')
    answer=client.app.state.agent.view(pid,t['agent_id'])['answer']
    assert not answer['checked_reviews'] and answer['requested_outputs']==[]
    assert answer['output_contract_coverage']=='contract_changed'


@pytest.mark.parametrize('bad',[
    dict(clarification_reason='ambiguous_request'),dict(clarification_question='Question'),
    dict(clarification_reason='ambiguous_request',clarification_question='  '),
    dict(clarification_reason='ambiguous_request',clarification_question='Question',fact_keys=['u_w_m2k'])])
def test_clarification_cannot_silently_carry_numeric_delivery(bad):
    payload=item('thermal',topics=[]);payload.update(bad)
    with pytest.raises(ValueError):OutputItem.model_validate(payload)


def test_foreign_review_is_rejected_and_model_mode_can_submit_only_current_review(client,monkeypatch):
    pid=create_project(client)['project_id'];foreign=create_project(client)['project_id']
    r=create_record(client,foreign,'thermal');a=client.app.state.agent
    with pytest.raises(ValueError,match='Cross-project'):
        a.call(pid,'professional_review',{'review':agent_reviews.reference(r,'thermal')},False)
    r=create_record(client,pid,'thermal');ref=agent_reviews.reference(r,'thermal')
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[item('thermal')]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),
        tool('professional_review',{'review':{**ref,'finish':True}})])
    t=a.start(pid,Chat(message='Only status.',mode='provider',read_requests=[scope('thermal',r)],read_execution='model'),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['checked_reviews'] and not t['answer'].get('checked_statements')
