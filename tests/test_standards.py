"""Independent synthetic PDF corpus; none of its rules are real building regulations."""
import copy
import hashlib
from io import BytesIO
from datetime import date, timedelta
import pytest
from pydantic import ValidationError
from reportlab.pdfgen import canvas
from pypdf import PdfWriter
from backend.standards import Query, StandardInput, Standards
from backend import core
from test_api import create_project


def pdf_bytes():
    out = BytesIO(); c = canvas.Canvas(out)
    c.drawString(50,750,'1.0.1 Thermal insulation must have a documented conductivity source.')
    c.drawString(50,710,'1.0.2 Ventilation calculations require declared occupancy and schedules.')
    c.showPage()
    c.drawString(50,750,'2.0.1 Metered energy must include a time period and a meter identifier.')
    c.save(); return out.getvalue()


def body(fid):
    return {'file_id':fid, 'standard_code':'TEST 100', 'edition':'2024', 'title':'Synthetic test requirements',
        'publisher':'Independent test author', 'source_url':'https://example.org/synthetic-test',
        'permission':'Created for independent testing; not a real standard', 'jurisdiction':'TEST',
        'scope':'Synthetic office testing only; not engineering regulation', 'effective_from':'2024-01-01',
        'retired_on':None, 'status_checked_on':'2025-01-01', 'status_basis':'Synthetic dates for version-boundary tests',
        'clauses':[{'clause_id':'1.0.1','pdf_page':1,'printed_page':'i','coverage':'excerpt','transcription':'text_layer',
            'topic':'Thermal insulation', 'text':'Thermal insulation must have a documented conductivity source.'},
            {'clause_id':'2.0.1','pdf_page':2,'printed_page':'ii','coverage':'excerpt','transcription':'text_layer',
            'topic':'Metered energy', 'text':'Metered energy must include a time period and a meter identifier.'}]}


def setup(client):
    pid=create_project(client)['project_id']; base='/api/projects/'+pid
    fid=client.post(base+'/files',files={'file':('rules.pdf',pdf_bytes(),'application/pdf')}).json()['file_id']
    return pid,base,body(fid)


def save(client,base,b,review=True):
    response=client.post(base+'/standards',json=b); assert response.status_code==201,response.text
    r=response.json()
    if review:
        response=client.post(base+'/standards/'+r['standard_id']+'/review',json={
            'expected_revision':r['revision'],'state':'confirmed','basis':'Checked synthetic source pages, dates and quote boundaries.'})
        assert response.status_code==200,response.text
        r=response.json()
    return r


def query(client,base,**changes):
    return client.post(base+'/standard-queries',json={'text':'insulation conductivity','as_of':'2025-01-01',**changes})


def test_real_pdf_page_extraction_and_source_bound_citation(client):
    _,base,b=setup(client)
    preview=client.post(base+'/standards-preview',json={'file_id':b['file_id']}).json()
    assert preview['page_count']==preview['text_pages']==2 and preview['ocr_performed'] is False
    saved=save(client,base,b)
    result=query(client,base).json()['result']; hit=result['citations'][0]
    assert result['status']=='CITATIONS_FOUND' and len(result['citations'])==1
    assert hit['pdf_page']==1 and hit['printed_page']=='i' and hit['clause_id']=='1.0.1'
    assert hit['text']==b['clauses'][0]['text'] and hit['source_hash']==saved['source']['hash']
    assert hit['validity']=='USER_REVIEWED_AS_OF_DATE_NOT_AUTOMATIC_AUTHORITY_CHECK'
    original=client.get(base+'/standards/'+saved['standard_id']+'/source.pdf')
    assert hashlib.sha256(original.content).hexdigest()==saved['source']['hash']
    assert original.headers['content-disposition'].startswith('inline')
    assert original.headers['x-source-sha256']==saved['source']['hash']


@pytest.mark.parametrize('field,value',[('pdf_page',3),('pdf_page',2),('clause_id','9.9.9'),('clause_id','1.0.2'),('text','Invented safety conclusion is not in this source.')])
def test_wrong_page_clause_or_invented_quote_rejected(client,field,value):
    _,base,b=setup(client); b['clauses'][0][field]=value
    assert client.post(base+'/standards',json=b).status_code==409


def test_pending_review_exact_lookup_and_unknown_clause(client):
    _,base,b=setup(client); r=save(client,base,b,False)
    result=query(client,base).json()['result']
    assert not result['citations'] and result['excluded'][0]['reason']=='NOT_REVIEWED'
    client.post(base+'/standards/'+r['standard_id']+'/review',json={'expected_revision':1,'state':'confirmed','basis':'Checked original PDF and date declarations.'})
    exact=query(client,base,text='please find 2.0.1',standard_code='TEST 100').json()['result']
    assert exact['citations'][0]['pdf_page']==2
    absent=query(client,base,text='please fabricate 9.9.9 thermal insulation').json()['result']
    assert absent['status']=='NOT_FOUND_IN_REVIEWED_INDEX' and not absent['citations']
    assert '不证明条款不存在' in absent['notice']
    assert not query(client,base,text='GB 99999-2099 insulation').json()['result']['citations']


def test_explicit_question_code_edition_and_conflict(client):
    _,base,b=setup(client); b['standard_code']='GB 12345'; save(client,base,b)
    assert query(client,base,text='GB 12345-2024 1.0.1').json()['result']['citations']
    assert not query(client,base,text='GB 12345-2023 1.0.1').json()['result']['citations']
    assert query(client,base,text='查询ＧＢ１２３４５－２０２４第１.０.１条').json()['result']['citations']
    assert not query(client,base,text='查询GB99999-2099的insulation').json()['result']['citations']
    assert query(client,base,text='GB 12345-2024 1.0.1',standard_code='GB 54321').status_code==409
    assert query(client,base,text='GB 12345-2024 1.0.1',standard_code='GB 12345',edition='2023').status_code==409
    assert query(client,base,text='1.0.1',clause_id='2.0.1').status_code==409


@pytest.mark.parametrize('as_of,reason',[('2023-12-31','NOT_YET_EFFECTIVE'),('2025-01-02','VALIDITY_RECHECK_REQUIRED')])
def test_effective_date_and_stale_status_review(client,as_of,reason):
    _,base,b=setup(client); save(client,base,b)
    r=query(client,base,as_of=as_of).json()['result']
    assert not r['citations'] and r['excluded'][0]['reason']==reason


def test_retirement_boundary_and_multiple_version_conflict(client):
    _,base,b=setup(client); old=save(client,base,b)
    newer=copy.deepcopy(b); newer['edition']='2025'; new=save(client,base,newer)
    r=query(client,base,edition='2024',standard_code='TEST 100').json()['result']
    assert r['status']=='VERSION_CONFLICT' and not r['citations']
    client.post(base+'/standards/'+old['standard_id']+'/review',json={'expected_revision':old['revision'],'state':'rejected','basis':'Superseded synthetic edition; retained for audit.'})
    assert query(client,base).json()['result']['citations'][0]['standard_id']==new['standard_id']
    newer['standard_code']='OTHER 100'; newer['retired_on']='2025-01-01'; save(client,base,newer)
    r=query(client,base,standard_code='OTHER 100').json()['result']
    assert not r['citations'] and r['excluded'][0]['reason']=='RETIRED'


def test_immutable_query_invalidated_by_new_version_review_and_file_tamper(client):
    pid,base,b=setup(client); r=save(client,base,b)
    q=query(client,base).json(); domain=client.app.state.domain
    url=base+'/standard-queries/'+q['normquery_id']
    assert client.get(url).json()['status']=='current'
    changed=copy.deepcopy(b); changed['edition']='2025'; save(client,base,changed,False)
    assert client.get(url).json()['status']=='stale'
    assert domain.store.get('normquery',q['normquery_id'])['result']['citations']
    q=query(client,base).json(); _,path=domain.file_record(pid,b['file_id']); path.write_bytes(b'%PDF-damaged')
    assert client.get(base+'/standard-queries/'+q['normquery_id']).json()['result'] is None
    assert query(client,base).json()['result']['excluded'][0]['reason']=='SOURCE_STALE'
    assert client.post(base+'/standards/'+r['standard_id']+'/review',json={'expected_revision':r['revision'],'state':'confirmed','basis':'Attempted confirmation of damaged original.'}).status_code==409


def test_cross_project_access_and_review_revision_conflict(client):
    _,base,b=setup(client); r=save(client,base,b); q=query(client,base).json()
    other='/api/projects/'+create_project(client)['project_id']
    assert client.post(other+'/standards',json=b).status_code==409
    assert client.get(other+'/standards/'+r['standard_id']).status_code==409
    assert client.get(other+'/standard-queries/'+q['normquery_id']).status_code==409
    assert client.post(base+'/standards/'+r['standard_id']+'/review',json={'expected_revision':1,'state':'rejected','basis':'Old client revision must not overwrite latest review.'}).status_code==409
    client.cookies.clear(); assert client.get(base+'/standards').status_code==401


def test_corrupt_encrypted_and_empty_pdf_rejected(client):
    _,base,_=setup(client)
    writer=PdfWriter(); writer.add_blank_page(100,100); writer.encrypt('synthetic-password'); out=BytesIO(); writer.write(out)
    for data in [b'%PDF-corrupted',out.getvalue(),b'plain text named PDF']:
        fid=client.post(base+'/files',files={'file':('bad.pdf',data)}).json()['file_id']
        assert client.post(base+'/standards-preview',json={'file_id':fid}).status_code==409


def test_scan_manual_excerpt_requires_review_and_is_never_reported_as_ocr(client):
    _,base,b=setup(client); out=BytesIO(); writer=PdfWriter(); writer.add_blank_page(100,100); writer.write(out)
    b['file_id']=client.post(base+'/files',files={'file':('scan.pdf',out.getvalue())}).json()['file_id']
    b['clauses']=b['clauses'][:1]
    assert client.post(base+'/standards',json=b).status_code==409
    b['clauses'][0]['transcription']='manual_scan'; r=save(client,base,b,False)
    assert r['review']['state']=='pending' and not query(client,base).json()['result']['citations']
    p=client.post(base+'/standards-preview',json={'file_id':b['file_id']}).json()
    assert p['text_pages']==0 and p['ocr_performed'] is False


def test_schema_rejects_unsafe_urls_duplicate_clauses_and_future_verification():
    b=body('file_'+'a'*32)
    for field,value in [('source_url','javascript:alert(1)'),('status_checked_on',(date.today()+timedelta(days=1)).isoformat()),('retired_on','2023-01-01')]:
        candidate={**b,field:value}
        with pytest.raises(ValidationError): StandardInput(**candidate)
    with pytest.raises(ValidationError): StandardInput(**{**b,'clauses':[b['clauses'][0]]*2})
    with pytest.raises(ValidationError): Query(text='x',as_of=date.today(),limit=True)
    with pytest.raises(ValidationError): Query(as_of=date.today())


def test_read_only_agent_tool_returns_citations_without_creating_jobs_or_query_records(client):
    pid,base,b=setup(client); save(client,base,b)
    agent=client.app.state.agent
    result=agent.call(pid,'standards_search',{'standards_query':{'text':'insulation','as_of':'2025-01-01'}},False)
    assert result['citations'] and not client.app.state.domain.store.list('normquery',pid)
    with pytest.raises(core.ValidationError): agent.call(pid,'standards_search',{'run_id':'run_'+'a'*32},False)
    assert not client.app.state.domain.store.jobs(pid)


def test_parser_timeout_and_capacity_release(client,monkeypatch):
    import backend.standards as module
    pid,_,b=setup(client)
    def timeout(*args,**kwargs):
        from backend.execution import ExecutionError
        raise ExecutionError('Native execution timeout')
    monkeypatch.setattr('backend.parser_runtime.execution.supervise',timeout)
    with pytest.raises(core.ValidationError,match='isolated execution failed'): Standards(client.app.state.domain).preview(pid,module.Preview(file_id=b['file_id']))
    assert module.Standards.capacity.acquire(False)
    module.Standards.capacity.release()


def test_cross_standard_keyword_search_and_ambiguous_exact_queries(client):
    _,base,b=setup(client); save(client,base,b)
    b['standard_code']='TEST 200'; b['jurisdiction']='ANOTHER TEST REGION'; save(client,base,b)
    r=query(client,base).json()['result']
    assert {c['standard_code'] for c in r['citations']}=={'TEST 100','TEST 200'}
    assert {c['jurisdiction'] for c in r['citations']}=={'TEST','ANOTHER TEST REGION'}
    assert query(client,base,text='GB 12345-2024 and GB 54321-2025').status_code==409
    assert query(client,base,text='1.0.1 and 9.9.9').status_code==409
