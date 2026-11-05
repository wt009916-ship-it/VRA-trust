import copy

import pytest
from pydantic import ValidationError
from backend import core
from backend.operations import AnalysisInput, analyze
from test_api import create_project


def contract():
    return dict(name='Independent operational screening',file_id='file_'+'a'*32,equipment='Synthetic FCU',data_nature='synthetic',
        source='Independent synthetic acceptance input',time_column='time',time_format='iso8601',clock_basis='offset_aware',
        clock_source='Explicit UTC synthetic clock',expected_interval_seconds=60,maximum_gap_seconds=90,
        channels=[dict(channel_id=k,column=k,name=k,unit=u,source='Independent declared unit') for k,u in [('temp','degF'),('command','ratio'),('feedback','percent')]],
        rules=[dict(rule_id='valve',name='Command feedback difference',kind='difference',channel_id='command',other_channel_id='feedback',unit='ratio',threshold=.1,
            minimum_duration_seconds=120,gate_channel_id='command',gate_minimum=.2,gate_unit='ratio',source='Explicit synthetic acceptance rule; not diagnostic')])


CSV='time,temp,command,feedback\n'+''.join(f'2026-01-01T00:0{i}:00Z,68,{c},{v}\n' for i,(c,v) in enumerate([(0,0),(1,0),(1,0),(1,0),(1,100),(1,0),(1,0)]))


def run(tmp_path,text=CSV,b=None):
    p=tmp_path/'samples.csv';p.write_text(text,encoding='utf-8');return analyze(p,AnalysisInput(**(b or contract())))


def test_manual_event_span_gate_and_affine_units(tmp_path):
    r=run(tmp_path);v=r['rules'][0]
    assert r['channels'][0]['sample_mean']==pytest.approx(20)
    assert r['channels'][2]['maximum']==1
    assert (v['evaluated_samples'],v['excluded_by_gate_samples'],v['violating_samples'])==(6,1,5)
    assert v['event_count']==1 and v['events'][0]['first_line']==3 and v['events'][0]['last_line']==5
    assert v['events'][0]['observed_span_seconds']==120
    assert r['diagnosis']=='NOT_CONFIRMED' and r['control_action']=='NONE'


def test_missing_nonfinite_and_gap_break_events(tmp_path):
    text=CSV.replace('00:02:00Z,68,1,0','00:02:00Z,NaN,1,').replace('00:06:00Z','00:09:00Z')
    r=run(tmp_path,text);v=r['rules'][0]
    assert r['quality']['cell_issue_count']==2 and r['quality']['gap_count']==1
    assert v['unknown_samples']==1 and v['event_count']==0 and r['status']=='insufficient_evidence'
    assert r['series_preview'][2]['values']['feedback'] is None


def test_range_and_rate_independent_values(tmp_path):
    b=contract();b['rules']=[dict(rule_id='temp',name='Temperature band',kind='range',channel_id='temp',unit='degC',lower=19,upper=21,minimum_duration_seconds=0,source='Synthetic explicit range'),
        dict(rule_id='slope',name='Temperature change',kind='rate',channel_id='temp',unit='degC/min',threshold=1,minimum_duration_seconds=0,source='Synthetic explicit slope')]
    text=CSV.replace('00:02:00Z,68','00:02:00Z,77')
    r=run(tmp_path,text,b)
    assert r['rules'][0]['violating_samples']==1
    assert r['rules'][1]['violating_samples']==2 and r['rules'][1]['unknown_samples']==1
    assert r['rules'][1]['events'][0]['observed_span_seconds']==60
    b['rules'][0]['lower']=20;b['rules'][0]['upper']=25
    assert run(tmp_path,text,b)['rules'][0]['violating_samples']==0


def test_exact_decimal_threshold_is_not_a_false_alarm(tmp_path):
    b=contract();b['rules'][0]['minimum_duration_seconds']=0
    text=CSV.replace(',1,0',',0.4,30').replace(',1,100',',0.4,30')
    assert run(tmp_path,text,b)['rules'][0]['violating_samples']==0
    text=text.replace(',0.4,30',',0.400000000000001,30')
    assert run(tmp_path,text,b)['rules'][0]['violating_samples']==6


def test_extreme_numeric_encoding_is_bounded_and_missing(tmp_path):
    r=run(tmp_path,CSV.replace(',68,',',1e-99999999,'))
    assert r['channels'][0]['valid_samples']==0 and r['quality']['cell_issue_count']==7


@pytest.mark.parametrize('edit',[
    lambda b:b.update(expected_interval_seconds=True),lambda b:b.update(maximum_gap_seconds=30),
    lambda b:b.update(expected_interval_seconds=.0001),lambda b:b['rules'][0].update(threshold=-1),
    lambda b:b['rules'][0].update(unit='percent'),lambda b:b['rules'][0].update(gate_unit='W'),
    lambda b:b['rules'][0].update(channel_id='unknown'),lambda b:b['channels'][2].update(unit='W'),
    lambda b:b['rules'][0].update(threshold=True),lambda b:b['rules'][0].update(minimum_duration_seconds=-1),
    lambda b:b['rules'][0].update(gate_minimum=None),lambda b:b['channels'].append(copy.deepcopy(b['channels'][0]))])
def test_invalid_rules_and_units_rejected(edit):
    b=contract();edit(b)
    with pytest.raises(ValidationError):AnalysisInput(**b)


@pytest.mark.parametrize('text',[
    '', 'time,temp,temp\n', CSV.replace('00:02:00Z','00:01:00Z'),CSV.replace('00:02:00Z','00:00:00Z'),
    CSV.replace('2026-01-01T00:02:00Z','2026-01-01T01:01:00+01:00'),CSV.replace('00:02:00Z','00:02:00'),
    CSV.replace('2026-01-01T00:02:00Z','01/02/2026 00:02'),CSV.replace(',68,1,0',',68,1,0,extra',1),CSV+'\0'])
def test_corrupt_or_ambiguous_inputs_rejected(tmp_path,text):
    with pytest.raises(core.ValidationError):run(tmp_path,text)


def test_no_health_claim_for_excluded_or_invalid_data(tmp_path):
    r=run(tmp_path,CSV.replace(',1,',',0,'))
    assert r['rules'][0]['evaluated_samples']==0 and r['status']=='insufficient_evidence'
    r=run(tmp_path,CSV.replace(',68,',',-500,').replace(',100',',101'))
    assert r['channels'][0]['sample_mean'] is None and r['quality']['cell_issue_count']==8


def test_preview_limit_and_event_truncation(tmp_path):
    from datetime import datetime,timedelta,timezone
    b=contract();b['rules'][0]['minimum_duration_seconds']=0
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    text='time,temp,command,feedback\n'+''.join(f'{(start+timedelta(minutes=i)).isoformat()},68,1,{100 if i%2 else 0}\n' for i in range(501))
    r=run(tmp_path,text,b);rule=r['rules'][0]
    assert len(r['series_preview'])==200 and r['preview_downsampled']
    assert rule['event_count']==251 and len(rule['events'])==200 and rule['events_truncated']
    assert r['series_preview'][-1]['line']==502


def upload(client,base,text=CSV):
    response=client.post(base+'/files',files={'file':('operations.csv',text.encode())})
    assert response.status_code==201,response.text
    b=contract();b['file_id']=response.json()['file_id'];return b


def test_api_preview_export_agent_auth_and_stale(client):
    from backend.agent import ToolRefusal
    pid=create_project(client)['project_id'];base='/api/projects/'+pid;b=upload(client,base)
    assert client.get(base+'/operation-inputs').json()[0]['file_id']==b['file_id']
    assert len(client.get(base+'/operation-inputs/'+b['file_id']).json()['sample_rows'])==5
    b['name']='<script>alert(1)</script>';response=client.post(base+'/operations',json=b)
    assert response.status_code==201,response.text
    r=response.json();oid=r['operation_id'];url=base+'/operations/'+oid
    assert client.get(url).json()['result']['rules'][0]['event_count']==1
    page=client.get(url+'/report.html').text
    assert '<script>' not in page and '&lt;script&gt;' in page
    agent=client.app.state.agent
    assert agent.call(pid,'operations_read',{'operation_id':oid},False)['result']['diagnosis']=='NOT_CONFIRMED'
    assert agent.call(pid,'operations_list',{},False)[0]['operation_id']==oid
    other=create_project(client)['project_id']
    assert client.get('/api/projects/'+other+'/operations/'+oid).status_code==409
    assert client.get('/api/projects/'+other+'/operation-inputs/'+b['file_id']).status_code==409
    with pytest.raises(ToolRefusal):agent.call(other,'operations_read',{'operation_id':oid},False)
    domain=client.app.state.domain;_,path=domain.file_record(pid,b['file_id']);path.write_text('changed')
    assert client.get(url).json()['result'] is None
    assert domain.store.get('operation',oid)['result']['rules'][0]['event_count']==1
    client.headers.pop('X-CSRF-Token');assert client.post(base+'/operations',json=b).status_code==403
    client.cookies.clear();assert client.get(url).status_code==401


def test_project_code_integrity_and_rejected_evidence(client,monkeypatch):
    from backend import operations
    pid=create_project(client)['project_id'];base='/api/projects/'+pid;b=upload(client,base)
    ev=client.post(base+'/evidence',json={'type':'manual_input','name':'Test meter provenance','source_file':b['file_id'],
        'source_locator':'all rows','authority':'Auditor','permission':'synthetic test','acquisition_method':'test','responsible_person':'auditor','status':'IMPORTED'}).json()
    b['evidence_ids']=[ev['evidence_id']];r=client.post(base+'/operations',json=b).json();url=base+'/operations/'+r['operation_id']
    client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected','responsible_person':'auditor','review_note':'Withdraw test source'})
    assert client.get(url).json()['result'] is None and client.post(base+'/operations',json=b).status_code==409
    b['evidence_ids']=[];r=client.post(base+'/operations',json=b).json();url=base+'/operations/'+r['operation_id']
    store=client.app.state.domain.store;p=store.get('project',pid);store.put('project',p,p['revision'])
    assert client.get(url).json()['result'] is None
    r=client.post(base+'/operations',json=b).json();url=base+'/operations/'+r['operation_id']
    with monkeypatch.context() as patch:
        patch.setattr(operations.core,'sha',lambda path:'changed')
        assert client.get(url).json()['result'] is None
    r=store.get('operation',r['operation_id']);r['result']['status']='healthy';store.put('operation',r,r['revision'])
    assert client.get(url).status_code==409


def test_size_and_sample_boundaries(tmp_path):
    p=tmp_path/'large.csv';p.write_bytes(b' '*(8*1024*1024+1))
    with pytest.raises(core.ValidationError,match='8 MiB'):analyze(p,AnalysisInput(**contract()))
    with pytest.raises(core.ValidationError):run(tmp_path,'time,temp,command,feedback\n2026-01-01T00:00:00Z,68,1,0\n')
