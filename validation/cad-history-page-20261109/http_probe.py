"""Bounded loopback HTTP acceptance; generated CAD and synthetic history only."""
import hashlib,io,json,os,secrets,socket,sys,tempfile,threading,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
DATA=Path(tempfile.mkdtemp(prefix='vra-cad-page-http-'))
os.environ['VRA_DATA_DIR']=str(DATA/'data')
import httpx,uvicorn,ezdxf
from backend.api import create_app
from backend import core
OUT=Path(__file__).resolve().parent/'http-first';OUT.mkdir(exist_ok=False)
checks=[];responses=[]
def check(name,ok):
 checks.append({'name':name,'passed':bool(ok)})
 (OUT/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
 assert ok,name
app=create_app(DATA/'data',start_worker=False)
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
url=f'http://127.0.0.1:{sock.getsockname()[1]}'
start=time.monotonic()
while not server.started:
 if not thread.is_alive() or time.monotonic()-start>30:raise RuntimeError('Readiness failed')
 time.sleep(.1)
receipt={'loopback':True,'synthetic_history':True,'browser_used':False,'formal_data_touched':False}
def capture(client,method,path,**kwargs):
 start=time.monotonic();r=client.request(method,path,**kwargs)
 row={'method':method,'path':path,'status':r.status_code,'bytes':len(r.content),'seconds':round(time.monotonic()-start,4)}
 if '/auth/' not in path:row['response']=r.json()
 responses.append(row)
 (OUT/'responses.json').write_text(json.dumps(responses,ensure_ascii=False,indent=2),encoding='utf8')
 return r
try:
 with httpx.Client(base_url=url,timeout=120,trust_env=False) as c:
  r=capture(c,'POST','/api/auth/register',json={'username':'cad_page_acceptance','display_name':'隔离验收','password':secrets.token_urlsafe(24)})
  check('register',r.status_code==200);c.headers['X-CSRF-Token']=r.json()['csrf_token']
  r=capture(c,'POST','/api/projects',json={'name':'分页参考项目','building':{'use':'office','location':'Golden','region':'US-CO','area_m2':123.0}})
  check('project',r.status_code==201);pid=r.json()['project_id'];base='/api/projects/'+pid
  doc=ezdxf.new('R2010');doc.units=4;doc.modelspace().add_line((0,0),(3000,4000));buffer=io.StringIO();doc.write(buffer);raw=buffer.getvalue().encode()
  r=capture(c,'POST',base+'/files',files={'file':('reference.dxf',raw)});check('upload',r.status_code==201);fid=r.json()['file_id']
  r=capture(c,'POST',base+'/cad-inspections',json={'file_id':fid});check('real_parser',r.status_code==201 and r.json()['result']['objects'][0]['length_m']==5)
  store=app.state.domain.store;original=store.get('cad',r.json()['cad_id']);ids=[original['cad_id']]
  def duplicate():
   obj={k:v for k,v in original.items() if k not in {'hash','revision'}};obj['cad_id']='cad_'+uuid.uuid4().hex;obj['hash']=core.hash_json(obj);store.put('cad',obj);return obj['cad_id']
  ids.extend(duplicate() for _ in range(200))
  old=capture(c,'GET',base+'/cad-inspections');check('legacy_contract',old.status_code==200 and len(old.json())==201)
  r=capture(c,'GET',base+'/cad-inspection-page');first=r.json();check('page_size',r.status_code==200 and len(first['records'])==20)
  check('payload_bounded',len(r.content)<len(old.content)/5)
  receipt['legacy']={'records':201,'bytes':len(old.content),'seconds':responses[-2]['seconds']}
  receipt['first_page']={'records':20,'bytes':len(r.content),'seconds':responses[-1]['seconds']}
  seen=[x['cad_id'] for x in first['records']];new=duplicate();current=first
  while current['next_before'] is not None:
   r=capture(c,'GET',base+'/cad-inspection-page',params={'snapshot':current['snapshot'],'before':current['next_before']})
   check('continuation_status',r.status_code==200);current=r.json();check('continuation_bound',len(current['records'])<=20)
   seen.extend(x['cad_id'] for x in current['records'])
  check('complete_unique_membership',seen==list(reversed(ids)) and len(set(seen))==201 and new not in seen)
  r=capture(c,'GET',base+'/cad-inspection-page');check('reset_sees_new',r.json()['records'][0]['cad_id']==new)
  _,path=app.state.domain.file_record(pid,fid)
  before_hash=hashlib.sha256(path.read_bytes()).hexdigest()
  with store.connect() as con:before_records=[tuple(x) for x in con.execute('SELECT * FROM records ORDER BY rowid')]
  try:
   path.write_bytes(b'isolated source corruption')
   r=capture(c,'GET',base+'/cad-inspection-page',params={'snapshot':first['snapshot']})
   check('snapshot_does_not_preserve_stale_quantity',r.status_code==200 and all(x['result'] is None and x['status']=='stale' for x in r.json()['records']))
  finally:path.write_bytes(raw)
  r=capture(c,'GET',base+'/cad-inspection-page',params={'snapshot':first['snapshot']})
  check('source_restore',all(x['result']['objects'][0]['length_m']==5 for x in r.json()['records']))
  check('original_bytes_preserved',hashlib.sha256(path.read_bytes()).hexdigest()==before_hash)
  with store.connect() as con:after_records=[tuple(x) for x in con.execute('SELECT * FROM records ORDER BY rowid')]
  check('read_did_not_mutate_business_records',before_records==after_records)
  with httpx.Client(base_url=url,timeout=30,trust_env=False) as other:
   check('anonymous_denied',capture(other,'GET',base+'/cad-inspection-page').status_code==401)
   capture(other,'POST','/api/auth/register',json={'username':'cad_page_other','display_name':'其他隔离用户','password':secrets.token_urlsafe(24)})
   check('cross_account_denied',capture(other,'GET',base+'/cad-inspection-page').status_code==404)
  check('invalid_limit',capture(c,'GET',base+'/cad-inspection-page?limit=1000').status_code==422)
 receipt['completed']=True
finally:
 server.should_exit=True;thread.join(20);sock.close();receipt['server_stopped']=not thread.is_alive();receipt['checks']=len(checks);receipt['passed']=sum(x['passed'] for x in checks);receipt['responses']=len(responses)
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(receipt,ensure_ascii=False))
