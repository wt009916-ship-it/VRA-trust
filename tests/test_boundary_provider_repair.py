"""Numerical seam conservation and real transport failure controls (no model score claim)."""
import json

import httpx
import pytest

from backend import core, model_export, honeybee_bridge, thermal_mesh
from backend.agent import Chat
from backend.gateway import ProviderSettings, ProviderError
from backend.model_schema import ModelDraft
from test_model_workbench import model_body, project


def test_numerical_cut_collapses_only_after_serialization_and_preserves_box():
    model = ModelDraft.model_validate(model_body()).model_dump()
    surfaces = model_export.geometry(model)
    seam = {'name':'numerical_cut','zone':'R1','kind':'Floor','boundary':'Ground','other':'',
            'construction':'Floor','boundary_basis':'Controlled numerical seam',
            'points':[[0.,0.,0.],[5.,0.,0.],[5.,3e-8,0.]]}
    fixed, report = thermal_mesh.engine_vertices([*surfaces,seam])
    assert report['max_displacement_m'] < thermal_mesh.WELD_LIMIT_M
    assert any(f['name']=='numerical_cut' for f in report['collapsed_faces'])
    assert honeybee_bridge.audit(model,fixed)['passed']
    assert {s['name']:s['boundary'] for s in fixed} == {s['name']:s['boundary'] for s in surfaces}
    assert sum(abs(z['volume_after_m3']-z['volume_before_m3']) for z in report['zones']) < .0001


def test_numerical_weld_rejects_large_connected_movement_and_one_sided_pair():
    face={'name':'a','zone':'R1','kind':'Floor','boundary':'Ground','other':'','construction':'Floor','boundary_basis':'test'}
    with pytest.raises(core.ValidationError, match='10微米'):
        thermal_mesh.engine_vertices([{**face,'points':[[i*9e-6,0.,0.] for i in range(6)]+[[1.,1.,0.]]}])
    small={**face,'boundary':'Surface','other':'b','points':[[0.,0.,0.],[5.,0.,0.],[5.,3e-8,0.]]}
    big={**face,'name':'b','zone':'R2','boundary':'Surface','other':'a','points':[[0.,0.,0.],[1.,0.,0.],[1.,1.,0.]]}
    with pytest.raises(core.ValidationError, match='成对'):
        thermal_mesh.engine_vertices([small,big])


def test_no_unused_window_construction_for_explicit_adiabatic_ifc_scenario():
    body=model_body()
    for r in body['rooms']:
        r['ifc_source']='Controlled-no-external-boundary'
    body['thermal']['ifc_unpaired_policy']='adiabatic_scenario'
    text,surfaces=model_export.idf(ModelDraft.model_validate(body).model_dump())
    assert not any(s['boundary']=='Outdoors' for s in surfaces)
    assert 'WindowMaterial:SimpleGlazingSystem' not in text
    assert 'FenestrationSurface:Detailed' not in text


def gateway(client, monkeypatch):
    monkeypatch.setenv('VRA_API_KEY','protocol-fixture-not-live')
    g=client.app.state.gateway
    g.save(ProviderSettings(enabled=True,model='qwen3-benchmark',endpoint='http://127.0.0.1:8790/v1/chat/completions'))
    return g


def completion():
    return {'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'依据工具核对完成。','reasoning_content':'must stay hidden'}}]}


def test_local_qwen_payload_budget_and_bounded_transient_retry(client,monkeypatch):
    g=gateway(client,monkeypatch)
    calls=[]
    def handle(request):
        payload=json.loads(request.content);calls.append(payload)
        assert payload['chat_template_kwargs']=={'enable_thinking':False}
        assert payload['max_tokens']==1000
        assert request.extensions['timeout']['read']>60
        return httpx.Response(503,text='private upstream details') if len(calls)==1 else httpx.Response(200,json=completion())
    response=g.complete([],[],transport=httpx.MockTransport(handle))
    assert len(calls)==2 and len(response['_request']['attempts'])==2
    assert response['_request']['attempts'][0]['code']=='HTTP_503'
    assert 'reasoning_content' not in response
    assert 'private upstream details' not in json.dumps(response)


@pytest.mark.parametrize('kind',['authorization','malformed','partial_transport'])
def test_gateway_does_not_retry_unauthorized_or_partial_results(client,monkeypatch,kind):
    g=gateway(client,monkeypatch);calls=[]
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"choices":'
            raise httpx.ReadTimeout('sensitive body must not echo')
    def handle(request):
        calls.append(request)
        if kind=='authorization':return httpx.Response(401,text='sensitive response')
        if kind=='partial_transport':return httpx.Response(200,stream=Broken())
        return httpx.Response(200,text='broken sensitive body')
    with pytest.raises(ProviderError) as error:
        g.complete([],[],transport=httpx.MockTransport(handle))
    assert len(calls)==1
    assert 'sensitive' not in str(error.value)
    assert error.value.attempts[0]['status']=='failed'


def test_deadline_prevents_request_and_length_limit_stays_partial(client,monkeypatch):
    g=gateway(client,monkeypatch)
    with pytest.raises(ProviderError,match='TIME_BUDGET'):
        g.complete([],[],timeout_s=0,transport=httpx.MockTransport(lambda r:pytest.fail('must not request')))
    pid=project(client);agent=client.app.state.agent
    monkeypatch.setattr(g,'complete',lambda *a,**k:{'role':'assistant','content':'截断说明',
        '_request':{'finish_reason':'length','attempts':[{'attempt':1,'status':'succeeded'}]}})
    result=agent.start(pid,Chat(message='核对天气',mode='provider',task='weather'),background=False)
    assert result['status']=='partial' and result['explanation_status']=='invalid'
    assert result['llm_commentary'] is None
    provider=next(e for e in result['events'] if e['tool']=='llm.request')
    assert provider['request_info']['finish_reason']=='length'


def test_tool_json_as_text_is_not_executed_and_explanation_retry_has_no_tools(client,monkeypatch):
    g=gateway(client,monkeypatch);pid=project(client);seen=[]
    replies=iter([{'role':'assistant','content':'```json\n{"name":"simulation_create","arguments":{}}\n```'},
                  {'role':'assistant','content':'当前没有天气或建筑证据，尚不能仿真；请先补齐来源。'}])
    def complete(messages,tools,**kwargs):
        seen.append(tools)
        return next(replies)
    monkeypatch.setattr(g,'complete',complete)
    task=client.app.state.agent.start(pid,Chat(message='核对天气',mode='provider',task='weather'),background=False)
    assert task['status']=='succeeded' and task['explanation_status']=='available'
    assert seen[0] and seen[1]==[] and len(seen)==2
    assert task['explanation_repairs']==1
    assert 'simulation_create' in task['explanation_attempts'][0]['content']
    assert not client.app.state.domain.store.jobs(pid)
