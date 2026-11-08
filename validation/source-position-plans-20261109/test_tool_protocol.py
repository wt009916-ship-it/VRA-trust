import json,copy
import pytest
import freeze_positions as fixture
import tool_protocol as p

def message(name,args):return {'role':'assistant','tool_calls':[{'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}

def test_complete_two_task_proposal_keeps_roles_and_has_no_authority():
 case=fixture.CASES[4];r=p.decode(case['message'],message('propose_calculations',{'tasks':case['gold_draft']['tasks']}))
 assert len(r['tasks'])==2 and r['outcome']=='draft' and r['issue'] is None
 assert not r['execution_authorized']
 assert [{k:v['ref'] for k,v in t['sources'].items()} for t in r['tasks']]==[g['refs'] for g in case['expected']['tasks']]

@pytest.mark.parametrize('name,reason,outcome',[('clarify_calculation','conflicting_parameter','clarify'),('clarify_calculation','missing_parameter','clarify'),('reject_calculation','invalid_parameter','reject'),('reject_calculation','unsafe_claim','reject')])
def test_abstention_cannot_carry_calculation(name,reason,outcome):
 r=p.decode('未知条件',message(name,{'reason':reason}));assert r['outcome']==outcome and not r['tasks'] and not r['execution_authorized']
 with pytest.raises(Exception):p.decode('未知条件',message(name,{'reason':reason,'tasks':[]}))

@pytest.mark.parametrize('mode',['contradictory','two_calls','unauthorized','no_calls','numeric_override'])
def test_ambiguous_or_unauthorized_messages_rejected(mode):
 case=fixture.CASES[0];args={'tasks':copy.deepcopy(case['gold_draft']['tasks'])};m=message('propose_calculations',args)
 if mode=='contradictory':args['issue']='missing_parameter';m=message('propose_calculations',args)
 if mode=='two_calls':m['tool_calls']*=2
 if mode=='unauthorized':m=message('calculation_execute',args)
 if mode=='no_calls':m={'role':'assistant','content':'已计算完成'}
 if mode=='numeric_override':args['tasks'][0]['layers'][0]['value']=42;m=message('propose_calculations',args)
 with pytest.raises(Exception):p.decode(case['message'],m)
