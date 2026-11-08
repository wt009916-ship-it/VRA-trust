"""Real CSV analyzer outputs for post-work comparison; synthetic equipment only."""
import pytest
from backend import core
from backend.operations import AnalysisInput, analyze
from backend.maintenance_recheck import assess, select_event


def record(tmp_path, name, *, hour=0, values=None, gates=None):
    values=values or [25,33,34,35,25];gates=gates or [1]*len(values)
    path=tmp_path/(name+'.csv')
    path.write_text('time,temp,enabled\n'+''.join(f'2026-01-01T{hour:02}:0{i}:00Z,{v},{g}\n' for i,(v,g) in enumerate(zip(values,gates))),encoding='utf-8')
    body=AnalysisInput(name=name,equipment='declared-fan-01',data_nature='synthetic',source='Independent synthetic observations',file_id='file_'+'a'*32,time_column='time',time_format='iso8601',clock_basis='offset_aware',clock_source='UTC synthetic clock',expected_interval_seconds=60,maximum_gap_seconds=60,
        channels=[{'channel_id':'temperature','column':'temp','name':'Temperature','unit':'degC','source':'Same declared test sensor'},
                  {'channel_id':'enabled','column':'enabled','name':'Enabled','unit':'state','source':'Same declared test run signal'}],
        rules=[{'rule_id':'hot','name':'Declared temperature rule','kind':'range','channel_id':'temperature','unit':'degC','upper':30,'minimum_duration_seconds':120,'gate_channel_id':'enabled','gate_minimum':1,'gate_unit':'state','source':'Synthetic threshold, no field diagnosis'}])
    result=analyze(path,body)
    return {'operation_id':name,'project_id':'project-test','status':result['status'],'input':body.model_dump(),
            'file_snapshot':{'hash':core.sha(path)},'result':result}


def pair(tmp_path):
    return record(tmp_path,'before'),record(tmp_path,'after',hour=1,values=[28,27,26,27])


def compare(a,b):return assess(a,b,'hot',0,'2026-01-01T00:30:00Z',120)


def test_actual_analyzer_event_and_rule_recheck(tmp_path):
    a,b=pair(tmp_path);rule,event=select_event(a,'hot',0)
    assert rule['violating_samples']==3 and event['observed_span_seconds']==120
    result=compare(a,b)
    assert result['outcome']=='no_violation_in_observed_window' and result['eligible_for_human_closure']
    assert result['observed_seconds']==180 and result['evaluated_samples']==4
    assert not result['cause_confirmed'] and result['equipment_health']=='NOT_ASSESSED'


@pytest.mark.parametrize('fault',['stale_before','stale_after','project','duplicate_id','duplicate_file','rule','unit','cadence','local_clock','overlap','short_work_time','missing_rule','bad_budget','equipment','nature'])
def test_comparison_refuses_false_recovery(tmp_path,fault):
    a,b=pair(tmp_path)
    if fault=='stale_before':a.update(status='stale',result=None)
    elif fault=='stale_after':b.update(status='stale',result=None)
    elif fault=='project':b['project_id']='other'
    elif fault=='duplicate_id':b['operation_id']=a['operation_id']
    elif fault=='duplicate_file':b['file_snapshot']=a['file_snapshot']
    elif fault=='rule':b['input']['rules'][0]['upper']=40
    elif fault=='equipment':b['input']['equipment']='other equipment'
    elif fault=='nature':b['input']['data_nature']='measured'
    elif fault=='unit':b['input']['channels'][0]['unit']='K'
    elif fault=='cadence':b['input']['expected_interval_seconds']=30
    elif fault=='local_clock':b['input']['clock_basis']='declared_local_clock'
    elif fault=='overlap':b['result']['quality']['first_time']='2026-01-01T00:02:00Z'
    elif fault=='missing_rule':b['input']['rules']=[]
    with pytest.raises(core.ValidationError):
        if fault=='short_work_time':assess(a,b,'hot',0,'2026-01-01T00:01:00Z',120)
        elif fault=='bad_budget':assess(a,b,'hot',0,'2026-01-01T00:30:00Z',float('nan'))
        else:compare(a,b)


@pytest.mark.parametrize('values,gates,outcome',[
    ([25,33,34,35,25],None,'rule_violation_remains'),
    ([28,'',26,27],None,'inconclusive'),
    ([28,27,26,27],[0,0,0,0],'inconclusive'),
    ([28,27],None,'inconclusive'),
    ([28,31,27,26],None,'rule_violation_remains')])
def test_no_qualifying_event_is_not_sufficient(tmp_path,values,gates,outcome):
    a=record(tmp_path,'before');b=record(tmp_path,'after',hour=1,values=values,gates=gates)
    r=compare(a,b);assert r['outcome']==outcome and not r['eligible_for_human_closure']


def test_initial_frozen_input_has_no_120_second_event(tmp_path):
    original=record(tmp_path,'v1',values=[25,33,34,25])
    assert original['result']['rules'][0]['event_count']==0
    with pytest.raises(core.ValidationError):select_event(original,'hot',0)


def test_unknown_event_index_and_boolean_rejected(tmp_path):
    a,b=pair(tmp_path)
    for index in [-1,True,200]:
        with pytest.raises(core.ValidationError):assess(a,b,'hot',index,'2026-01-01T00:30:00Z',120)


@pytest.mark.parametrize('values,expected', [([20,20,20,20],'no_violation_in_observed_window'),([20,'',20,20],'inconclusive')])
def test_rate_rule_allows_only_mathematically_unavailable_first_sample(tmp_path,values,expected):
    a=record(tmp_path,'before',values=[20,30,40,50,50]);b=record(tmp_path,'after',hour=1,values=values)
    for r in (a,b):
        rule=r['input']['rules'][0];rule.pop('upper');rule.update(kind='rate',unit='degC/min',threshold=5)
        r['result']=analyze(tmp_path/(r['operation_id']+'.csv'),AnalysisInput(**r['input']))
        r['status']=r['result']['status']
    result=compare(a,b)
    assert result['outcome']==expected
    assert result['eligible_for_human_closure']==(expected=='no_violation_in_observed_window')
