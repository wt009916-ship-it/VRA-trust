exec(open('D:/稀土agent-稀土制暖全流程/outputs/agent-contract-20261113/implement.py',encoding='utf-8').read().split("edit('backend/agent_outputs.py'")[0])
edit('tests/test_agent_explicit_outputs.py', "    assert t['answer']['output_contract_coverage']!='fulfilled'\n    assert t['answer']['task_completion']!='verified'", "    assert t['status']=='failed' and t['answer'] is None\n    assert not t.get('model_finished_delivery')")
edit('frontend/src/agent-requests.js','以下要求由模型从原问题解析，请核对是否准确。计划完成不等于已证明完整理解问题；解释由应用依据当前核验来源生成。','每项注明要求来自用户勾选或模型解析。交付所选指标不等于完整回答自由问题；解释由应用依据当前核验来源生成。')
with (ROOT/'tests/test_agent_energy.py').open('a',encoding='utf-8') as f:
 f.write('''

def test_energy_delivery_schema_requires_context_after_actual_read(client,native,monkeypatch):
    pid,r,_=create_utility(client,native,monkeypatch);agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['interval_count']}),tool('professional_deliver',{'delivery':{**claim(r,'utility',['interval_count']),'finish':True}})])
    original=agent.gateway.complete;seen=[]
    def captured(messages,tools):
        seen.append(copy.deepcopy(tools));return original(messages,tools)
    monkeypatch.setattr(agent.gateway,'complete',captured)
    task=agent.start(pid,Chat(message='Read interval count',mode='provider',infer_outputs=False,read_requests=[{'request_key':'r','kind':'utility','purpose':'results','record_id':r['utility_id']}]),background=False)
    assert task['status']=='succeeded',task.get('error')
    schema=next(t['function']['parameters'] for t in seen[-1] if t['function']['name']=='professional_deliver')
    statement=schema['$defs']['Statement']
    assert 'energy_context' in statement['required']
    assert statement['properties']['energy_context']=={'$ref':'#/$defs/EnergyContext'}


def test_energy_period_explanation_is_readable_and_keeps_both_calendars(client,native,monkeypatch):
    _,r,_=create_utility(client,native,monkeypatch)
    artifact=agent_energy.artifact(r,'utility')
    text=agent_energy.explanation('period',artifact)
    assert '原始账期' in text and '映射模拟期间' in text and '2019' in text
    assert '{' not in text and '参考数据不是实楼校准' in text
''')
print('test expectations aligned with observed terminal scope refusal; added energy schema and period checks')
