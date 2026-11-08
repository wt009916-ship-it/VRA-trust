from pathlib import Path
import json,os,secrets,socket,subprocess,sys,tempfile,time,uuid,hashlib
R=Path(r'C:/Users/18483/AppData/Local/Temp/vra-agent-read-execution-20261108');sys.path.insert(0,str(R))
from backend.private_storage import private_mkdir
import httpx
root=private_mkdir(Path(tempfile.gettempdir())/('vra-standard-ui-'+uuid.uuid4().hex));port=18774
with socket.socket() as sock:sock.bind(('127.0.0.1',port))
bootstrap=root/'serve.py'
bootstrap.write_text('''import os,sys,threading,time
from pathlib import Path
sys.path.insert(0,os.environ['VRA_TEST_REPO'])
from backend.api import create_app
import uvicorn
server=uvicorn.Server(uvicorn.Config(create_app(start_worker=False),host='127.0.0.1',port=18774,log_level='warning'))
def monitor():
    stop=Path(os.environ['VRA_TEST_STOP'])
    while not stop.exists():time.sleep(.2)
    server.should_exit=True
threading.Thread(target=monitor,daemon=True).start()
server.run()
''',encoding='utf-8')
env={**os.environ,'VRA_DATA_DIR':str(root/'data'),'VRA_TEST_REPO':str(R),'VRA_TEST_STOP':str(root/'stop')}
log=(root/'server.log').open('wb')
process=subprocess.Popen([sys.executable,'-B','-X','utf8',str(bootstrap)],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
receipt={'root':str(root),'pid':process.pid,'port':port,'repo':str(R),'status':'starting','prototype_18772_touched':False}
pointer=Path('D:/稀土agent-稀土制暖全流程/outputs/vra-soak-20261108/standard-browser.json')
pointer.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
try:
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,trust_env=False) as client:
        for _ in range(60):
            assert process.poll() is None,'Isolated server exited during startup'
            try:
                if client.get('/api/health',timeout=2).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.5)
        else:raise RuntimeError('Local server not ready')
        login=client.post('/api/auth/register',json={'username':'standard_ui_test','display_name':'Isolated standards QA','password':secrets.token_urlsafe(32)})
        assert login.status_code==200,login.status_code;client.headers['X-CSRF-Token']=login.json()['csrf_token']
        c=json.loads((R/'validation/scenario-agent-20261108/frozen-fresh.json').read_text(encoding='utf-8'))['cases'][0]
        project=client.post('/api/projects',json={'name':'合成规范跨条款验收（非真实法规）','building':c['building']})
        assert project.status_code==201,project.text;pid=project.json()['project_id'];base='/api/projects/'+pid
        from io import BytesIO
        from datetime import date
        from reportlab.pdfgen import canvas
        standards=[]
        for code,label,second in [('TEST 101','ALPHA','2.3.4'),('TEST 202','BETA','9.8.7')]:
            stream=BytesIO();pdf=canvas.Canvas(stream)
            quotes=[('1.2.3',f'SYNTHETIC_{label}: This clause is for software testing only.'),(second,f'SYNTHETIC_{label}_SECOND: This text has no regulatory authority.')]
            for clause,text in quotes:
                pdf.drawString(40,750,clause+' '+text);pdf.showPage()
            pdf.save();raw=stream.getvalue()
            (R/'validation/standard-batch-20261108'/f'{label}.pdf').write_bytes(raw)
            uploaded=client.post(base+'/files',files={'file':(label+'.pdf',raw,'application/pdf')});assert uploaded.status_code==201,uploaded.text
            body={'file_id':uploaded.json()['file_id'],'standard_code':code,'edition':'2024','title':f'Synthetic {label} test source','publisher':'Independent test author','source_url':'https://example.org/synthetic-test','permission':'Created for software testing; not a real standard','jurisdiction':label+' TEST REGION','scope':'Synthetic software testing only; no engineering authority','effective_from':'2024-01-01','retired_on':None,'status_checked_on':date.today().isoformat(),'status_basis':'Synthetic version dates checked for this isolated test','clauses':[{'clause_id':clause,'pdf_page':i+1,'printed_page':str(i+1),'coverage':'excerpt','transcription':'text_layer','topic':label+' comparison','text':text} for i,(clause,text) in enumerate(quotes)]}
            registered=client.post(base+'/standards',json=body);assert registered.status_code==201,registered.text;r=registered.json()
            reviewed=client.post(base+'/standards/'+r['standard_id']+'/review',json={'expected_revision':r['revision'],'state':'confirmed','basis':'Compared synthetic document, pages, identifiers and version declarations.'});assert reviewed.status_code==200,reviewed.text
            standards.append(reviewed.json())
        state={'cookies':[{'name':c.name,'value':c.value,'domain':'127.0.0.1','path':'/','expires':-1,'httpOnly':True,'secure':False,'sameSite':'Strict'} for c in client.cookies.jar],'origins':[]}
        (root/'browser-state.json').write_text(json.dumps(state),encoding='utf-8')
        receipt.update(status='ready',project_id=pid,standards=standards)
        pointer.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        (R/'validation/standard-batch-20261108/browser-seed.json').write_text(json.dumps({k:v for k,v in receipt.items() if k not in {'root','pid','repo'}},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:receipt[k] for k in ['status','root','project_id']},ensure_ascii=False),flush=True)
    began=time.monotonic()
    while not (root/'stop').exists():
        assert process.poll() is None,'Local browser server exited unexpectedly'
        if time.monotonic()-began>1800:raise RuntimeError('Isolated browser lifecycle limit')
        time.sleep(.5)
finally:
    (root/'stop').touch()
    try:process.wait(timeout=30)
    except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
    log.close();receipt.update(status='stopped',exit_code=process.returncode)
    (root/'browser-state.json').unlink(missing_ok=True)
    pointer.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'stopped','exit_code':process.returncode}),flush=True)
