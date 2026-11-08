"""Real isolated selected-page OCR; synthetic text is not an engineering rule."""
import copy
import hashlib
import pytest
from pydantic import ValidationError
from backend.standards import Clause
from backend.standard_ocr import PageOCR
from backend.standards_worker import select_page
from test_api import create_project
from test_standards import body, query, save
from test_drawings import pdf_bytes


def setup_ocr(client):
    pid=create_project(client)['project_id'];base='/api/projects/'+pid;raw=pdf_bytes()
    fid=client.post(base+'/files',files={'file':('test.pdf',raw)}).json()['file_id']
    r=client.post(base+'/standard-ocr',json={'file_id':fid,'page':2})
    assert r.status_code==201,r.text
    return pid,base,fid,r.json(),raw


def test_actual_selected_page_review_query_and_derivative_withdrawal(client):
    pid,base,fid,r,raw=setup_ocr(client);oid=r['normocr_id']
    assert r['source']['hash']==hashlib.sha256(raw).hexdigest()
    assert r['selection']['original_pdf_page']==2 and r['result']['original_pdf_page']==2
    assert r['result']['page']['page']==1 and r['result']['page']['page_count']==1
    candidate=next(c for c in r['result']['candidates'] if c['text']=='PAGE TWO')
    assert candidate['source_kind']=='AI_INFERRED' and candidate['review_required']
    assert r['selection_limits']['enforced'] and r['result']['resource_limits']['enforced']
    b=body(fid);b['clauses']=[dict(clause_id='1.0.1',pdf_page=2,printed_page='2',topic='Synthetic page label',
        text='PAGE TWO',transcription='ocr_assisted',ocr_id=oid,candidate_ids=[candidate['candidate_id']],
        transcription_basis='Independently compared the actual second PDF page label.')]
    for field,value in [('pdf_page',1),('candidate_ids',['text_999']),('ocr_id','normocr_'+'a'*32)]:
        invalid=copy.deepcopy(b);invalid['clauses'][0][field]=value
        assert client.post(base+'/standards',json=invalid).status_code in (404,409)
    first=save(client,base,b,False)
    assert not query(client,base,text='',standard_code='TEST 100',clause_id='1.0.1').json()['result']['citations']
    review=client.post(base+'/standards/'+first['standard_id']+'/review',json={'expected_revision':1,'state':'confirmed','basis':'Checked synthetic label, page mapping and date; no engineering approval.'})
    assert review.status_code==200
    q=query(client,base,text='',standard_code='TEST 100',clause_id='1.0.1').json()
    citation=q['result']['citations'][0]
    assert citation['ocr_id']==oid and citation['text']=='PAGE TWO'
    assert client.get(base+'/standard-ocr/'+oid).json()['result']['candidates']==r['result']['candidates']
    for name in ('preview.png','selected.pdf'):
        downloaded=client.get(base+'/standard-ocr/'+oid+'/'+name);assert downloaded.status_code==200
        assert hashlib.sha256(downloaded.content).hexdigest()==r['artifacts'][name]['hash']
    other='/api/projects/'+create_project(client)['project_id']
    assert client.get(other+'/standard-ocr/'+oid).status_code==409
    assert client.get(other+'/standard-ocr/'+oid+'/selected.pdf').status_code==409
    original=client.app.state.domain.file_record(pid,fid)[1]
    assert hashlib.sha256(original.read_bytes()).hexdigest()==r['source']['hash']
    artifact=client.app.state.domain.store.root/r['artifacts']['selected.pdf']['path']
    artifact.write_bytes(b'corrupted isolated derivative')
    assert client.get(base+'/standard-ocr/'+oid).json()['result'] is None
    assert client.get(base+'/standard-ocr/'+oid+'/preview.png').status_code==409
    assert client.get(base+'/standards/'+first['standard_id']).json()['source_status']=='stale'
    assert client.get(base+'/standard-queries/'+q['normquery_id']).json()['result'] is None
    assert not query(client,base,text='',standard_code='TEST 100',clause_id='1.0.1').json()['result']['citations']
    client.headers.pop('X-CSRF-Token');assert client.post(base+'/standard-ocr',json={'file_id':fid,'page':1}).status_code==403
    client.cookies.clear();assert client.get(base+'/standard-ocr/'+oid+'/selected.pdf').status_code==401


@pytest.mark.parametrize('page',[0,501,True,1.5])
def test_strict_page_request(page):
    with pytest.raises(ValidationError):PageOCR(file_id='file_'+'a'*32,page=page)


def test_explicit_provenance_required():
    c=dict(clause_id='1.0.1',pdf_page=1,printed_page='1',text='Synthetic excerpt',topic='test',transcription='ocr_assisted')
    with pytest.raises(ValidationError):Clause(**c)
    c.update(ocr_id='normocr_'+'a'*32,candidate_ids=['text_1'],transcription_basis='Compared original raster page')
    Clause(**c)
    for change in [dict(transcription='manual_scan'),dict(candidate_ids=['text_1','text_1']),dict(candidate_ids=['missing'])]:
        with pytest.raises(ValidationError):Clause(**(c|change))


def test_selection_bounds_and_corrupt_source(tmp_path):
    path=tmp_path/'test.pdf';path.write_bytes(pdf_bytes())
    for page in [0,3]:
        with pytest.raises(ValueError):select_page(path,page,tmp_path/'selected.pdf')
    path.write_bytes(b'%PDF-broken')
    with pytest.raises(Exception):select_page(path,1,tmp_path/'selected.pdf')


def test_source_change_withdraws_ocr(client):
    pid,base,fid,r,raw=setup_ocr(client)
    client.app.state.domain.file_record(pid,fid)[1].write_bytes(b'changed isolated original')
    assert client.get(base+'/standard-ocr/'+r['normocr_id']).json()['result'] is None
