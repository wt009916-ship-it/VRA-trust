from pathlib import Path
p=Path('tests/test_agent_energy.py')
with p.open('a',encoding='utf-8') as f:
 f.write('''

def test_relationship_uses_current_context_and_withdraws_with_source(client, native, monkeypatch):
    from backend.agent_semantics import current_answer
    pid, record, snapshot = create_utility(client, native, monkeypatch)
    delivery = claim(record, 'utility', ['bill_total_kwh', 'native_total_kwh'])
    answer = current_answer(client.app.state.domain, pid, [delivery])
    relationship = answer['checked_statements'][0]['energy_relationship']
    assert relationship['origin'] == 'application_from_current_verified_sources'
    assert [source['fact'] for source in relationship['sources']] == ['bill_total_kwh', 'native_total_kwh']
    assert 'kWh表示能量' in relationship['text']
    assert all(source['data_nature'] == 'synthetic' for source in relationship['sources'])
    snapshot['sql_sha256'] = 'withdrawn'
    assert not current_answer(client.app.state.domain, pid, [delivery])['checked_statements']


def test_carrier_relationship_and_insufficient_read():
    context = {'carrier':'Electricity', 'boundary':'Facility', 'native_start':'2020-01-01',
               'native_end':'2021-01-01', 'bill_start':None, 'bill_end':None,
               'basis':'native_table_rounded', 'data_nature':'model_scenario', 'run_id':'run_reference'}
    first = {'fact':'carrier_total.Electricity', 'unit':'kWh', 'energy_context':context}
    second = {'fact':'carrier_total.NaturalGas', 'unit':'kWh',
              'energy_context':{**context,'carrier':'Natural Gas'}}
    assert agent_energy.relationship([first]) is None
    result = agent_energy.relationship([first, second])
    assert '天然气量不能作为耗电量' in result['text']
    assert result['sources'][1]['carrier'] == 'Natural Gas'
    assert '来源期间一致' in result['text']
    second['energy_context']['native_end'] = '2020-07-01'
    assert '来源期间有差异' in agent_energy.relationship([first, second])['text']


def test_relationship_plan_requires_two_selected_facts():
    from backend import agent_outputs
    record = {'question':'Explain the carrier relationship', 'read_requests':[
        {'request_key':'energy', 'record_id':'enduse_'+'a'*32,
         'kind':'enduse','purpose':'results'}]}
    item = agent_outputs.OutputItem(request_key='energy',
        question_excerpt=record['question'], fact_keys=['carrier_total.Electricity'],
        explanation_topics=['energy_relationship'])
    with pytest.raises(core.ValidationError, match='at least two'):
        agent_outputs.freeze(record,[item])
    item.fact_keys.append('carrier_total.NaturalGas')
    assert agent_outputs.freeze(record,[item])['items'][0]['explanation_topics'] == ['energy_relationship']
''')
