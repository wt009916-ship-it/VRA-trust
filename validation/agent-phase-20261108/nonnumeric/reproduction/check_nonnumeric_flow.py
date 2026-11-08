"""Actual authenticated HTTP/controller flow, scripted planner explicitly disclosed."""
from pathlib import Path
import hashlib,json,os,runpy,secrets,sys,time,uuid
from decimal import Decimal
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
H=Path(__file__).parent;O=Path('C:/Users/18483/AppData/Local/Temp/vra-nonnumeric-20261108')
sys.path.insert(0,str(R))
from backend.private_storage import private_mkdir
root=private_mkdir(O/('flow-'+uuid.uuid4().hex))
os.environ['VRA_DATA_DIR']=str(root/'api')
helpers=runpy.run_path(str(H/'run_next_intent_pair.py'))
from fastapi.testclient import TestClient
from backend.api import app

scripted=[]
app.state.agent.gateway.public=lambda:{'enabled':True,'key_configured':True}
def complete(messages,tools):
    args=scripted.pop(0)
    assert any(t['function']['name']=='requested_output_plan' for t in tools)
    return {'role':'assistant','tool_calls':[{'id':'plan_'+uuid.uuid4().hex,'type':'function',
        'function':{'name':'requested_output_plan','arguments':json.dumps({'output_plan':[args]})}}]}
app.state.agent.gateway.complete=complete
evidence={'method':'Authenticated real HTTP/application services with scripted output-plan messages; no live-model capability credit.','cases':{}}
with TestClient(app) as c:
    login=c.post('/api/auth/register',json={'username':'flow_owner','display_name':'Isolated flow','password':secrets.token_urlsafe(32)})
    assert login.status_code==200;c.headers['X-CSRF-Token']=login.json()['csrf_token']
    p=c.post('/api/projects',json={'name':'Nonnumeric flow','building':{'use':'office','location':'Synthetic','region':'US-CO','area_m2':800}})
    assert p.status_code==201;project=p.json();pid=project['project_id']
    r=c.post(f'/api/projects/{pid}/thermal',json=helpers['seeds']()['thermal']);assert r.status_code==201
    source=r.json();rid=source['thermal_id'];scope={'request_key':'wall','kind':'thermal','purpose':'results','record_id':rid}
    def task(question,item,previous=None):
        scripted.append({'request_key':'wall','question_fragment_ids':['q1'],**item})
        body={'message':question,'mode':'provider','read_requests':[scope],'allow_compute':False}
        if previous:body['previous_agent_id']=previous
        response=c.post(f'/api/projects/{pid}/agent/chat',json=body);assert response.status_code==202,response.text
        result=response.json();start=time.monotonic()
        while result['status']=='running':
            assert time.monotonic()-start<30
            time.sleep(.05);result=c.get(f'/api/projects/{pid}/agent/{result["agent_id"]}').json()
        assert result['status']=='succeeded',result.get('error')
        return result
    review=task('只说明当前记录状态，不报数值。',{'fact_keys':[],'explanation_topics':['status']})
    assert review['answer']['checked_reviews'] and not review['answer'].get('checked_statements')
    ask=task('是否给U存在冲突，请先问我。',{'fact_keys':[],'explanation_topics':[],
        'clarification_reason':'conflicting_request','clarification_question':'请确认是否只需要传热系数U？'})
    assert ask['answer']['task_completion']=='incomplete' and ask['answer']['clarification_requests']
    assert not any(e['tool']=='thermal_read' for e in ask['events'])
    reply=task('现在明确只要U及单位，不需要解释。',{'fact_keys':['u_w_m2k'],'explanation_topics':[]},ask['agent_id'])
    claims=[f for row in reply['answer']['checked_statements'] for f in row['facts']]
    assert len(claims)==1 and claims[0]['fact']=='u_w_m2k'
    assert abs(Decimal(claims[0]['value'])-Decimal(1)/Decimal('1.36'))<Decimal('1e-11')
    assert not reply['answer']['clarification_requests']
    assert not any(e['tool']=='calculation_execute' for e in reply['events'])
    saved=app.state.agent.store.get('agent',review['agent_id'])
    before=hashlib.sha256(json.dumps(saved,sort_keys=True).encode()).hexdigest()
    change=c.put(f'/api/projects/{pid}/building',json={'expected_revision':project['revision'],
        'building':{**project['building'],'area_m2':950}});assert change.status_code==200
    stale=c.get(f'/api/projects/{pid}/agent/{review["agent_id"]}').json()
    assert not stale['answer']['checked_reviews'] and stale['answer']['review_failures']
    assert before==hashlib.sha256(json.dumps(app.state.agent.store.get('agent',review['agent_id']),sort_keys=True).encode()).hexdigest()
    evidence['cases']=dict(review=review,ask=ask,reply=reply,withdrawn=stale)
    evidence.update(passed=True,source_changed_withdraws_text=True,history_unchanged=True,browser=False,model=False)
(O/'http-flow.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':True,'flow':['status-only','clarification','explicit-user-reply','source-change-withdrawal'],'live_model':False,'browser':False}))
