import copy
from runner import history_append

def test_history_preserves_actual_tool_call_and_guard_output():
 question={'role':'user','content':'Actual input'}
 message={'role':'assistant','content':None,'tool_calls':[{'id':'actual-call','type':'function','function':{'name':'clarify_calculation','arguments':'{"reason":"missing_parameter"}'}}]}
 review={'outcome':'clarify','issue':'missing_parameter','tasks':[],'execution_authorized':False}
 before=copy.deepcopy((question,message,review));history=[]
 history_append(history,question,message,review)
 assert history[:2]==[question,message]
 assert history[2]['role']=='tool' and history[2]['tool_call_id']=='actual-call'
 import json
 assert json.loads(history[2]['content'])==review
 assert (question,message,review)==before

def test_missing_response_does_not_invent_a_model_reply():
 history=[];q={'role':'user','content':'Actual unanswered input'}
 history_append(history,q,None,None)
 assert history==[q]

def test_invalid_proposal_gets_actual_application_error_not_fake_success():
 history=[];q={'role':'user','content':'Actual input'}
 msg={'role':'assistant','tool_calls':[{'id':'bad-call','type':'function','function':{'name':'invented_tool','arguments':'{}'}}]}
 history_append(history,q,msg,None)
 assert history[1]==msg and history[2]['tool_call_id']=='bad-call'
 assert 'no calculation or business write' in history[2]['content']
