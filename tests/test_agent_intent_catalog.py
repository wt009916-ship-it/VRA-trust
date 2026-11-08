"""Source anchors and explicit domain meanings; no claim of model intent verification."""
import copy
import json
import pytest

from backend import agent_outputs as outputs, agent_intent_catalog as catalog
from backend.agent import Chat
from test_api import create_project
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_professional import create_record


def context(question='读取运行碳排放；不要求单位面积碳排放。'):
    return {'question':question,'read_requests':[{'request_key':'carbon','kind':'lifecycle','purpose':'results',
              'record_id':'lifecycle_'+'a'*32}]}


def item(**kwargs):
    return outputs.OutputItem.model_validate({'request_key':'carbon','question_fragment_ids':['q1'],
        'fact_keys':['stage.operation'],'explanation_topics':[],**kwargs})


@pytest.mark.parametrize('question', ['读取R=2.5和U；检查计划。','line one\nline two;third','😀α𠮷墙体。'+('长'*3999),
    '墙；'*2000,' '*15+'read','X'*4000])
def test_every_fragment_is_exact_bounded_and_stable(question):
    question=question[:4000]
    fragments=catalog.fragments(question)
    assert fragments==catalog.fragments(question) and 1<=len(fragments)<=24
    assert len({f['fragment_id'] for f in fragments})==len(fragments)
    for f in fragments:
        assert f['text']==question[f['start']:f['end']] and len(f['text'])<=400
    covered=set(i for f in fragments for i in range(f['start'],f['end']))
    assert all(i in covered for i,c in enumerate(question) if not c.isspace())


def test_frozen_anchor_preserves_user_text_and_does_not_certify_selection():
    r=context();before=copy.deepcopy(r)
    plan=outputs.freeze(r,[item(question_fragment_ids=['q2','q1'])])
    assert r==before and not plan['intent_verified']
    saved=plan['items'][0]
    assert saved['question_excerpt']=='读取运行碳排放；\n不要求单位面积碳排放。'
    assert [f['fragment_id'] for f in saved['question_spans']]==['q1','q2']
    assert saved['fact_keys']==['stage.operation']
    # Even a wrong metric choice does not become proven intent.
    wrong=outputs.freeze(r,[item(fact_keys=['kgco2e_m2_over_study_period'])])
    assert wrong['intent_verified'] is False


@pytest.mark.parametrize('change',[
    {'question_fragment_ids':['q999']}, {'question_fragment_ids':['q1','q1']},
    {'question_fragment_ids':[]}, {'question_excerpt':'forged source instruction'},
    {'question_fragment_ids':None,'question_excerpt':None},
    {'question_fragment_ids':None,'question_excerpt':'source data is not the user question'},
])
def test_bad_or_ambiguous_anchors_rejected(change):
    with pytest.raises(ValueError):outputs.freeze(context(),[item(**change)])


def test_all_domains_have_complete_distinct_metric_meanings():
    assert set(catalog.MEANINGS)==set(outputs.FACTS)
    for kind,keys in outputs.FACTS.items():
        assert set(keys)==set(catalog.MEANINGS[kind])
        assert len(set(catalog.MEANINGS[kind].values()))==len(keys)


def test_real_service_reads_after_fragment_plan_and_no_free_text_copy(client,monkeypatch):
    p=create_project(client);pid=p['project_id'];r=create_record(client,pid,'thermal');a=client.app.state.agent
    question='给出材料层热阻和传热系数；另外查询施工记录是否存在。'
    plan=[{'request_key':'wall','question_fragment_ids':['q1'],
        'fact_keys':['layer_resistance_m2k_w','u_w_m2k'],'explanation_topics':[]},
        {'request_key':'site','question_fragment_ids':['q2'],'fact_keys':[],'explanation_topics':[]}]
    calls=scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':plan})])
    definitions=[];original=a.gateway.complete
    def capture(messages,tools):
        definitions.extend(copy.deepcopy(tools));return original(messages,tools)
    monkeypatch.setattr(a.gateway,'complete',capture)
    task=a.start(pid,Chat(message=question,mode='provider',read_requests=[
        {'request_key':'wall','kind':'thermal','purpose':'results','record_id':r['thermal_id']},
        {'request_key':'site','kind':'schedule','purpose':'availability','record_id':None}]),background=False)
    assert task['status']=='succeeded',task['error']
    assert len(calls)==1 and task['answer']['output_contract_coverage']=='fulfilled'
    assert not task['answer']['output_plan']['intent_verified']
    for variant in definitions[0]['function']['parameters']['properties']['output_plan']['items']['oneOf']:
        assert 'question_excerpt' not in variant['properties']
        assert variant['properties']['question_fragment_ids']['items']['enum']==['q1','q2']
        assert 'question_fragment_ids' in variant['required']


def test_six_scope_schema_remains_bounded_with_dense_punctuation(client):
    a=client.app.state.agent
    requests=[{'request_key':k,'kind':k,'purpose':'results','record_id':k+'_'+'b'*32}
              for k in outputs.FACTS]  # Schema size bound, not a legal six-result Chat.
    tool_schema=outputs.constrain_tool(a.tools({'requested_output_plan'})[0],requests,'墙；'*2000)
    assert len(json.dumps(tool_schema,ensure_ascii=False))<20000
