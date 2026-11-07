"""Exact annotation math plus real PDF/OCR/service integration, not geometry recognition."""
import copy
import hashlib
import io
import json
import re

import pytest
from reportlab.pdfgen.canvas import Canvas
from backend.drawing_associations import Sheet, AssociationInput, analyze, attributes, report
from test_api import create_project
from test_cad import upload


def drawing(index,texts,reviewed=True):
    candidates=[{'candidate_id':'text_'+str(i+1),'text':text,'recognition_score':.98,
        'polygon_px':[[1,1],[20,1],[20,10],[1,10]],'polygon_source_px':[[1,1],[20,1],[20,10],[1,10]],
        'source_polygon_inside_raster':True} for i,text in enumerate(texts)]
    return {'drawing_id':'drawing_'+str(index)*32,'hash':'a'*64,'input':{'page':1},'source':{'file_id':'file_'+str(index)*32},
        'result':{'candidates':candidates},'reviews':{c['candidate_id']:{'decision':'confirmed','effective_text':c['text']} for c in candidates} if reviewed else {}}


def sheet(d,**kw):
    return Sheet(drawing_id=d['drawing_id'],drawing_hash=d['hash'],scope_label='Door type scope',
        scope_basis='Explicit synthetic comparison scope only',**kw)


def pair(a,b,**kw):
    d=[drawing(1,a,**kw),drawing(2,b,**kw)];return analyze(d,[sheet(v) for v in d])


def test_exact_mixed_units_and_mark_only_no_element_identity():
    result=pair(['D01 WIDTH 900 mm HEIGHT 2100 mm'],['D01 WIDTH 0.9 m HEIGHT 210 cm'])
    r=result['relations'][0]
    assert r['state']=='consistent_annotations' and not r['issues']
    assert {c['role']:c['values_m'] for c in r['comparisons']}=={'width':['0.9','0.9'],'height':['2.1','2.1']}
    assert not r['element_identity_verified'] and not r['may_deduplicate_quantities']
    assert result['confidence_probability'] is None


@pytest.mark.parametrize('text,expected',[
    ('D01 WIDTH 950 mm','dimension_conflict'),('D01 WIDTH 900','dimension_unknown'),
    ('D01 WIDTH -1 mm','dimension_unknown'),('D01 WIDTH 0 mm','dimension_unknown'),
    ('D01 WIDTH 1e100 m','dimension_unknown'),('D01 WIDTH 900 mm WIDTH 950 mm','dimension_unknown'),
    ('D01 WIDTH 900 mm²','dimension_unknown'),('D01','dimension_unknown')])
def test_conflicting_missing_invalid_and_duplicate_dimensions_never_zero(text,expected):
    r=pair(['D01 WIDTH 900 mm'],[text])['relations'][0]
    assert expected in r['issues'] and r['state']=='review_required'
    if expected=='dimension_unknown':assert r['comparisons'][0]['values_m'][1] is None


def test_dimensions_require_role_not_inferred_from_two_number_order():
    r=pair(['D01 900 x 2100 mm'],['D01 900 x 2100 mm'])['relations'][0]
    assert r['comparisons']==[] and 'dimensions_missing' in r['issues']
    assert attributes('WIDTH 900 mm HEIGHT 2.1 m')['height']['value_m']=='2.1'


def test_duplicates_scopes_and_unreviewed_candidates_block_confirmation_basis():
    d=[drawing(1,['D01 WIDTH 900 mm','D01 WIDTH 900 mm']),drawing(2,['D01 WIDTH 900 mm'],False)]
    s=[sheet(x) for x in d];s[1].scope_label='Another floor'
    r=analyze(d,s)['relations'][0]
    assert {'scope_conflict','ambiguous_occurrences','transcription_unreviewed'}<=set(r['issues'])
    s[1].scope_label='';assert 'scope_missing' in analyze(d,s)['relations'][0]['issues']


def test_explicit_separate_text_binding_retains_manual_basis_and_units():
    d=[drawing(1,['D01','900 mm']),drawing(2,['D01 WIDTH 0.9 m'])]
    s=[sheet(d[0],quantity_links=[{'mark_candidate_id':'text_1','value_candidate_id':'text_2','role':'width','basis':'Explicit adjacent dimension association from original page'}]),sheet(d[1])]
    before=copy.deepcopy(d);r=analyze(d,s)['relations'][0]
    assert d==before and r['state']=='consistent_annotations'
    assert r['observations'][0]['dimensions']['width']['association_kind']=='USER_DECLARED_CANDIDATE_LINK'
    assert r['observations'][0]['dimensions']['width']['source']['candidate_id']=='text_2'


@pytest.mark.parametrize('field,value',[('candidate_ids',['text_999']),('quantity_links',[{'mark_candidate_id':'text_1','value_candidate_id':'text_999','role':'width','basis':'Explicit test association'}])])
def test_invented_candidate_rejected(field,value):
    d=[drawing(1,['D01']),drawing(2,['D01'])]
    with pytest.raises(ValueError):analyze(d,[sheet(d[0],**{field:value}),sheet(d[1])])


def test_rejected_or_outside_source_candidates_cannot_be_confirmed():
    d=[drawing(1,['D01 WIDTH 900 mm']),drawing(2,['D01 WIDTH 900 mm'])]
    d[1]['reviews']['text_1']['decision']='rejected'
    assert analyze(d,[sheet(v) for v in d])['relations']==[]
    d[1]['reviews']['text_1']['decision']='confirmed';d[1]['result']['candidates'][0]['source_polygon_inside_raster']=False
    assert 'source_position_uncertain' in analyze(d,[sheet(v) for v in d])['relations'][0]['issues']


def document(second_width="950 mm"):
    stream=io.BytesIO();canvas=Canvas(stream,pagesize=(900,500))
    for title,text in [('PLAN LEVEL 1','D01 WIDTH 900 mm'),('DOOR SCHEDULE','D01 WIDTH '+second_width)]:
        canvas.setFont('Helvetica',25);canvas.drawString(50,430,title)
        canvas.rect(50,120,700,240);canvas.line(400,120,400,360)
        canvas.setFont('Helvetica',28);canvas.drawString(80,280,text)
        canvas.showPage()
    canvas.save();return stream.getvalue()


def real_pages(client):
    pid=create_project(client)['project_id'];raw=document();fid=upload(client,pid,'independent-two-sheet.pdf',raw)
    pages=[]
    for page in [1,2]:
        response=client.post(f'/api/projects/{pid}/drawings',json={'file_id':fid,'page':page})
        assert response.status_code==201,response.text
        pages.append(response.json())
    return pid,pages,raw,fid


def input_body(pages):
    return {'name':'Independent cross-sheet door mark check','sheets':[{'drawing_id':p['drawing_id'],'drawing_hash':p['hash'],
        'scope_label':'Declared D01 type scope','scope_basis':'Synthetic drawing pair explicitly intended to describe same door type, not same instance'} for p in pages]}


def test_real_two_page_ocr_conflict_review_staleness_auth_and_original_preservation(client):
    pid,pages,raw,fid=real_pages(client);base=f'/api/projects/{pid}';body=input_body(pages)
    response=client.post(base+'/drawing-associations',json=body)
    assert response.status_code==201,response.text
    record=response.json();relations=record['result']['relations']
    assert any(r['mark']=='D01' and 'dimension_conflict' in r['issues'] for r in relations),[p['result']['candidates'] for p in pages]
    relation=next(r for r in relations if r['mark']=='D01');path=base+'/drawing-associations/'+record['drawingassociation_id']
    review={'expected_revision':1,'relation_id':relation['relation_id'],'decision':'association_confirmed','basis':'Synthetic reviewer cannot override contradictory dimensions'}
    assert client.post(path+'/review',json=review).status_code==409
    review['decision']='unresolved';saved=client.post(path+'/review',json=review)
    assert saved.status_code==200,saved.text
    assert client.post(path+'/review',json=review).status_code==409
    assert [x['revision'] for x in client.get(path+'/history').json()]==[1,2]
    html=client.get(path+'/report.html');assert html.status_code==200
    embedded=json.loads(re.search(r'<script type="application/json" id="record">(.*?)</script>',html.text,re.S)[1])
    assert embedded['result']==saved.json()['result']
    assert hashlib.sha256(client.get(base+'/files/'+fid).content).digest()==hashlib.sha256(raw).digest()
    current=pages[0];candidate=next(c for c in current['result']['candidates'] if 'D01' in c['text'])
    assert client.post(base+'/drawings/'+current['drawing_id']+'/review',json={'expected_revision':1,
        'candidate_id':candidate['candidate_id'],'decision':'confirmed','basis':'Changed transcription review after association creation'}).status_code==200
    old=copy.deepcopy(client.app.state.domain.store.get('drawingassociation',record['drawingassociation_id']))
    refreshed=client.get(path).json();assert refreshed['status']=='stale' and refreshed['result'] is None and refreshed['reviews'] is None
    assert client.post(path+'/review',json={**review,'expected_revision':2}).status_code==409
    assert '950' not in client.get(path+'/report.html').text
    assert client.app.state.domain.store.get('drawingassociation',record['drawingassociation_id'])==old
    other=create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/drawing-associations/'+record['drawingassociation_id']).status_code==409
    assert client.post(f'/api/projects/{other}/drawing-associations',json=body).status_code==409
    client.headers.pop('X-CSRF-Token');assert client.post(path+'/review',json=review).status_code==403
    client.cookies.clear();assert client.get(path).status_code==401


def test_same_source_page_and_changed_hash_not_independent_evidence(client):
    pid,pages,raw,fid=real_pages(client);base=f'/api/projects/{pid}'
    duplicate=client.post(base+'/drawings',json={'file_id':fid,'page':1}).json()
    assert client.post(base+'/drawing-associations',json=input_body([pages[0],duplicate])).status_code==409
    body=input_body(pages);body['sheets'][0]['drawing_hash']='f'*64
    assert client.post(base+'/drawing-associations',json=body).status_code==409


def test_html_report_escapes_original_annotations_and_embedded_json():
    malicious='</script><img src=x onerror=alert(1)>'
    record={'input':{'name':malicious},'sources':[],'result':None,'notice':malicious}
    rendered=report(record)
    assert '<img' not in rendered and rendered.count('</script>')==1
    embedded=re.search(r'<script type="application/json" id="record">(.*?)</script>',rendered,re.S)[1]
    assert json.loads(embedded)==record


def test_input_capacity_and_duplicate_record_guard():
    d=drawing(1,['D01']);s=sheet(d)
    with pytest.raises(ValueError):AssociationInput(name='duplicate',sheets=[s,s])
    with pytest.raises(ValueError):Sheet(drawing_id=d['drawing_id'],drawing_hash=d['hash'],scope_label='L1')


def test_real_reviewed_consistent_annotations_confirm_without_entity_merge(client):
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}';raw=document('0.9 m')
    fid=upload(client,pid,'consistent-type-mark.pdf',raw);pages=[]
    for page in [1,2]:
        response=client.post(base+'/drawings',json={'file_id':fid,'page':page});assert response.status_code==201,response.text
        drawing=response.json()
        for candidate in drawing['result']['candidates']:
            if 'D01' not in candidate['text']:continue
            response=client.post(base+'/drawings/'+drawing['drawing_id']+'/review',json={
                'expected_revision':drawing['revision'],'candidate_id':candidate['candidate_id'],
                'decision':'confirmed','basis':'Transcription checked against the newly generated source page'})
            assert response.status_code==200,response.text;drawing=response.json()
        pages.append(drawing)
    response=client.post(base+'/drawing-associations',json=input_body(pages));assert response.status_code==201,response.text
    record=response.json();r=next(r for r in record['result']['relations'] if r['mark']=='D01')
    assert r['state']=='consistent_annotations',r['issues']
    assert r['comparisons'][0]['values_m']==['0.9','0.9']
    response=client.post(base+'/drawing-associations/'+record['drawingassociation_id']+'/review',json={
        'expected_revision':1,'relation_id':r['relation_id'],'decision':'association_confirmed',
        'basis':'Confirmed same declared type annotation, not identity of physical door instances'})
    assert response.status_code==200,response.text
    assert response.json()['reviews'][r['relation_id']]['element_identity_verified'] is False
    assert response.json()['result']['relations'][0]['may_deduplicate_quantities'] is False
