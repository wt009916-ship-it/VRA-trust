"""Source-bound cross-sheet annotation candidates, not inferred element identity."""
import copy
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictInt, model_validator
from fastapi import Request
from fastapi.responses import HTMLResponse
from . import core
from .schema import Contract
from .domain import identifier

Role = Literal['width','height','length','thickness']
CANDIDATE = r'^text_[1-9][0-9]{0,2}$'


class QuantityLink(Contract):
    mark_candidate_id: str = Field(pattern=CANDIDATE)
    value_candidate_id: str = Field(pattern=CANDIDATE)
    role: Role
    basis: str = Field(min_length=10,max_length=1000)


class Sheet(Contract):
    drawing_id: str = Field(pattern=r'^drawing_[a-f0-9]{32}$')
    drawing_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    scope_label: str = Field(default='',max_length=120)
    scope_basis: str = Field(default='',max_length=1000)
    candidate_ids: list[str] | None = Field(default=None,min_length=1,max_length=500)
    quantity_links: list[QuantityLink] = Field(default_factory=list,max_length=50)

    @model_validator(mode='after')
    def scope(self):
        if self.scope_label.strip() and len(self.scope_basis.strip())<10:
            raise ValueError('A declared comparison scope requires its explicit basis')
        if self.candidate_ids is not None and (len(set(self.candidate_ids))!=len(self.candidate_ids) or
                any(not re.fullmatch(CANDIDATE,v) for v in self.candidate_ids)):
            raise ValueError('Select distinct existing text candidate IDs')
        keys=[(r.mark_candidate_id,r.role) for r in self.quantity_links]
        if len(set(keys))!=len(keys):raise ValueError('At most one explicit quantity association per mark and role')
        return self


class AssociationInput(Contract):
    name: str = Field(min_length=1,max_length=120)
    sheets: list[Sheet] = Field(min_length=2,max_length=8)

    @model_validator(mode='after')
    def distinct(self):
        if len({s.drawing_id for s in self.sheets})!=len(self.sheets):
            raise ValueError('Choose distinct drawing records')
        return self


class AssociationReview(Contract):
    expected_revision: StrictInt = Field(ge=1)
    relation_id: str = Field(pattern=r'^link_[a-f0-9]{24}$')
    decision: Literal['association_confirmed','rejected','unresolved']
    basis: str = Field(min_length=10,max_length=2000)


# Deliberately bounded label recognition. A mark denotes neither instance count
# nor type/instance semantics; unrecognized text is retained as a coverage gap.
MARK = re.compile(r'(?<![A-Za-z0-9])(?:DOOR|WINDOW|ROOM|WALL|WL|D|M|W|R|C|Z|L)[ _-]?[0-9]{1,4}(?![A-Za-z0-9])')
NUMBER = r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?'
UNIT = r'(?:mm|cm|m|毫米|厘米|米)'
SCALAR = re.compile(r'(?P<number>'+NUMBER+r')\s*(?P<unit>'+UNIT+r')?',re.I)
ATTRIBUTE = re.compile(r'(?<![A-Za-z])(WIDTH|HEIGHT|LENGTH|THICKNESS|宽|高|长|厚)\s*[:=：]?\s*('+NUMBER+r')\s*('+UNIT+r')?(?![A-Za-z0-9.²³^/])',re.I)
ROLES={'width':'width','height':'height','length':'length','thickness':'thickness','宽':'width','高':'height','长':'length','厚':'thickness'}
FACTORS={'mm':Decimal('.001'),'cm':Decimal('.01'),'m':Decimal(1),'毫米':Decimal('.001'),'厘米':Decimal('.01'),'米':Decimal(1)}


def normalize(text):
    return unicodedata.normalize('NFKC',text).strip()


def scalar(number,unit):
    if not unit:return {'status':'missing_unit','value_m':None}
    try:
        value=Decimal(number)*FACTORS[unit.lower()]
        if not value.is_finite() or not Decimal(0)<value<=Decimal('1000000'):
            raise ValueError('Invalid annotated length')
    except (InvalidOperation,ValueError,KeyError):return {'status':'invalid_value','value_m':None}
    return {'status':'parsed_annotation','value_m':format(value.normalize(),'f')}


def attributes(text):
    values=defaultdict(list)
    for match in ATTRIBUTE.finditer(normalize(text)):
        role=ROLES[match[1].lower()]
        values[role].append({**scalar(match[2],match[3]),'raw_text':match[0]})
    return {role:rows[0] if len(rows)==1 else {'status':'multiple_values','value_m':None,'raw_text':[r['raw_text'] for r in rows]}
            for role,rows in values.items()}


def text_source(drawing,candidate):
    review=drawing['reviews'].get(candidate['candidate_id'])
    if review and review['decision'] in {'rejected','unreadable'}:return None
    return {'candidate_id':candidate['candidate_id'],'original_text':candidate['text'],
        'text':review['effective_text'] if review else candidate['text'],
        'source_kind':'HUMAN_TRANSCRIPTION' if review else 'AI_INFERRED',
        'transcription_reviewed':bool(review),'recognition_score':candidate['recognition_score'],
        'score_is_correctness_probability':False,'source_position_verified':candidate.get('source_polygon_inside_raster',False),
        'polygon_source_px':candidate['polygon_source_px'],
        'polygon_preview_px':candidate['polygon_px']}


def observations(drawing,sheet):
    selected=set(sheet.candidate_ids) if sheet.candidate_ids is not None else None
    available={c['candidate_id']:c for c in drawing['result']['candidates']}
    required=set(selected or ())|{v for link in sheet.quantity_links for v in (link.mark_candidate_id,link.value_candidate_id)}
    if not required<=set(available):raise core.ValidationError('Selected annotation candidate does not exist')
    if selected is not None and any(link.mark_candidate_id not in selected for link in sheet.quantity_links):
        raise core.ValidationError('Explicit quantity association must address a selected mark candidate')
    sources={key:text_source(drawing,c) for key,c in available.items()}
    rows=[];unmatched=[]
    for key,source in sources.items():
        if source is None or (selected is not None and key not in selected):continue
        tags=list(dict.fromkeys(re.sub(r'[ _-]','',m[0]) for m in MARK.finditer(normalize(source['text']))))
        if not tags:
            unmatched.append(key);continue
        dimensions=attributes(source['text']) if len(tags)==1 else {}
        for tag in tags:
            rows.append({'mark':tag,'drawing_id':drawing['drawing_id'],'source_file_id':drawing['source']['file_id'],
                'page':drawing['input']['page'],'scope_label':normalize(sheet.scope_label),
                'scope_basis':sheet.scope_basis,'scope_source_kind':'USER_DECLARED' if sheet.scope_label.strip() else 'MISSING',
                'annotation':copy.deepcopy(source),'mark_assignment_ambiguous':len(tags)>1,
                'dimensions':{k:{**v,'source':copy.deepcopy(source),'association_kind':'SAME_TEXT_ANNOTATION'} for k,v in dimensions.items()}})
    for link in sheet.quantity_links:
        matches=[r for r in rows if r['annotation']['candidate_id']==link.mark_candidate_id]
        value=sources[link.value_candidate_id]
        if len(matches)!=1 or value is None:
            raise core.ValidationError('Quantity association requires one recognized mark and readable source text')
        if link.role in matches[0]['dimensions']:
            raise core.ValidationError('Do not replace an inline annotated quantity with another source')
        match=SCALAR.fullmatch(normalize(value['text']))
        parsed=scalar(match['number'],match['unit']) if match else {'status':'unparsed_value','value_m':None}
        matches[0]['dimensions'][link.role]={**parsed,'raw_text':value['text'],'source':copy.deepcopy(value),
            'association_kind':'USER_DECLARED_CANDIDATE_LINK','association_basis':link.basis}
    return rows,unmatched


def analyze(drawings,sheets):
    groups=defaultdict(list);coverage=[]
    for drawing,sheet in zip(drawings,sheets):
        rows,unmatched=observations(drawing,sheet)
        for row in rows:groups[row['mark']].append(row)
        if sum(len(v) for v in groups.values())>1000:raise core.ValidationError('Annotation budget exceeded; explicitly select candidates')
        coverage.append({'drawing_id':drawing['drawing_id'],'selected_text_count':len(sheet.candidate_ids or drawing['result']['candidates']),
            'mark_occurrence_count':len(rows),'unrecognized_candidate_ids':unmatched,
            'notice':'Unrecognized or unselected text is not proof of missing components.'})
    relations=[];single=[]
    for mark,rows in sorted(groups.items()):
        counts=Counter(r['drawing_id'] for r in rows)
        if len(counts)<2:
            single.append({'mark':mark,'drawing_ids':list(counts),'occurrences':sum(counts.values())});continue
        scopes={r['scope_label'] for r in rows};issues=[];comparisons=[]
        if '' in scopes:issues.append('scope_missing')
        if len(scopes-{''})>1:issues.append('scope_conflict')
        if max(counts.values())>1 or any(r['mark_assignment_ambiguous'] for r in rows):issues.append('ambiguous_occurrences')
        roles=sorted({role for row in rows for role in row['dimensions']})
        if not roles:issues.append('dimensions_missing')
        for role in roles:
            values=[r['dimensions'].get(role) for r in rows]
            known=all(v and v['status']=='parsed_annotation' for v in values)
            state='consistent' if known and len({v['value_m'] for v in values})==1 else 'conflict' if known else 'unknown'
            comparisons.append({'role':role,'state':state,'values_m':[v.get('value_m') if v else None for v in values],
                'basis':'Exact normalized annotated quantities; no geometric measurement, uncertainty model or inferred axis.'})
            if state=='conflict':issues.append('dimension_conflict')
            if state=='unknown':issues.append('dimension_unknown')
        if not all(r['annotation']['transcription_reviewed'] and all(v['source']['transcription_reviewed'] for v in r['dimensions'].values()) for r in rows):
            issues.append('transcription_unreviewed')
        if not all(r['annotation']['source_position_verified'] and all(v['source']['source_position_verified'] for v in r['dimensions'].values()) for r in rows):
            issues.append('source_position_uncertain')
        issues=list(dict.fromkeys(issues))
        relations.append({'relation_id':'link_'+core.hash_json([mark,sorted(counts)])[:24],'mark':mark,
            'state':'consistent_annotations' if not issues else 'review_required','issues':issues,
            'observations':rows,'comparisons':comparisons,'match_basis':'Exact recognized annotation mark in selected drawings',
            'element_identity_verified':False,'geometry_alignment_performed':False,'may_deduplicate_quantities':False})
    if len(relations)>200:raise core.ValidationError('Relation budget exceeded; explicitly select a smaller drawing scope')
    return {'relations':relations,'single_sheet_marks':single,'coverage':coverage,
        'assessment':'ANNOTATION_ASSOCIATIONS_NOT_ELEMENT_IDENTITY','confidence_probability':None,
        'limitations':['同编号可能是类型编号、重复实例或不同楼层，不能据此合并构件或去重算量。',
            '只识别有限字母数字标记及明确属性/单位；不识别墙门窗几何、不推断遗漏尺寸或坐标对齐。',
            '比对范围和分离文字的属性关联由用户声明；原文复核不是工程审批，识别分数不是正确概率。',
            '数值一致仅说明所选标注一致；未测量实体，不评估公差、结构安全或规范合规。']}


def version():return core.sha(Path(__file__))


class DrawingAssociations:
    def __init__(self,drawings):self.drawings,self.store=drawings,drawings.store

    def save(self,pid,body):
        if len(self.store.list('drawingassociation',pid))>=50:raise core.ValidationError('At most 50 drawing association analyses per project')
        sources=[];seen=set()
        for sheet in body.sheets:
            source=self.drawings.view(pid,sheet.drawing_id)
            if source['status']=='stale' or source['hash']!=sheet.drawing_hash:raise core.ValidationError('Drawing changed or stale; refresh and review')
            page=(source['source']['hash'],source['input']['page'])
            if page in seen:raise core.ValidationError('The same original file page is not independent cross-sheet evidence')
            seen.add(page);sources.append(source)
        before=version();result=analyze(sources,body.sheets)
        for source in sources:
            current=self.drawings.view(pid,source['drawing_id'])
            if current['status']=='stale' or current['hash']!=source['hash']:raise core.ValidationError('Drawing changed during association analysis')
        snapshots=[{'drawing_id':d['drawing_id'],'drawing_hash':d['hash'],'drawing_revision':d['revision'],
            'file_id':d['source']['file_id'],'file_sha256':d['source']['hash'],'page':d['input']['page'],
            'source_name':d['source']['name'],'geometry_basis_hash':d.get('geometry_basis_hash')} for d in sources]
        obj={'drawingassociation_id':identifier('drawingassociation'),'project_id':pid,'input':body.model_dump(mode='json'),
            'sources':snapshots,'method_hash':before,'result':result,'reviews':{},'last_review':None,'created_at':core.now()}
        obj['hash']=core.hash_json(obj);self.store.put('drawingassociation',obj)
        return self.view(pid,obj['drawingassociation_id'])

    def _record(self,pid,ident):
        obj=self.store.get('drawingassociation',ident)
        if obj['project_id']!=pid:raise core.ValidationError('Cross-project drawing association rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}})!=obj['hash']:
            raise core.ValidationError('Drawing association integrity failed')
        return obj

    def view(self,pid,ident):
        obj=self._record(pid,ident);reasons=[]
        if obj['method_hash']!=version():reasons.append('method_changed')
        for source in obj['sources']:
            try:
                current=self.drawings.view(pid,source['drawing_id'])
                if current['status']=='stale' or current['hash']!=source['drawing_hash']:reasons.append('drawing_changed:'+source['drawing_id'])
            except (ValueError,KeyError,OSError):reasons.append('drawing_unavailable:'+source['drawing_id'])
        return {**obj,'status':'stale' if reasons else 'review_required' if obj['result']['relations'] else 'no_cross_sheet_candidates',
            'stale_reasons':reasons,'result':None if reasons else copy.deepcopy(obj['result']),
            'reviews':None if reasons else copy.deepcopy(obj['reviews']),
            'notice':'关联和尺寸对照只针对原文标注；未确认实体同一性、工程量、结构安全或缺失信息。'}

    def review(self,pid,ident,body,reviewer):
        current=self.view(pid,ident)
        if current['status']=='stale':raise core.ValidationError('Cannot review a stale association analysis')
        relation=next((r for r in current['result']['relations'] if r['relation_id']==body.relation_id),None)
        if not relation:raise core.ValidationError('Unknown relation; cannot create a missing association through review')
        if body.decision=='association_confirmed' and relation['state']!='consistent_annotations':
            raise core.ValidationError('Resolve scope, ambiguity, transcription and dimension issues in sources before confirming')
        obj=self._record(pid,ident)
        action={**body.model_dump(exclude={'expected_revision'}),'reviewer_id':reviewer,'reviewed_at':core.now(),
            'source_kind':'HUMAN_ASSOCIATION_REVIEW','element_identity_verified':False}
        obj['reviews']={**obj['reviews'],body.relation_id:action};obj['last_review']=action
        obj.pop('revision',None);obj.pop('hash',None);obj['hash']=core.hash_json(obj)
        self.store.put('drawingassociation',obj,expected=body.expected_revision)
        return self.view(pid,ident)

    def history(self,pid,ident):
        self._record(pid,ident)
        return [{'revision':r['revision'],'hash':r['hash'],'last_review':r['last_review']} for r in self.store.history('drawingassociation',ident)]


def report(record):
    esc=lambda v:html.escape(str(v))
    sources=''.join('<li>'+esc(s['source_name'])+' · page '+esc(s['page'])+' · SHA256 '+esc(s['file_sha256'])+'</li>' for s in record['sources'])
    content='<p>来源或方法已变化，历史关联及数值已撤下。</p>'
    if record['result']:
        content=''.join('<section><h2>'+esc(r['mark'])+'</h2><p>'+esc(', '.join(r['issues']) or '标注一致，仍不证明实体同一性')+'</p><ul>'+''.join(
            '<li>'+esc(o['source_file_id'])+' / '+esc(o['annotation']['candidate_id'])+'：'+esc(o['annotation']['text'])+'</li>' for o in r['observations'])+'</ul><pre>'+esc(json.dumps(r['comparisons'],ensure_ascii=False,indent=2))+'</pre></section>' for r in record['result']['relations'])
    embedded=json.dumps(record,ensure_ascii=False).replace('<',r'\u003c').replace('>',r'\u003e').replace('&',r'\u0026')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>跨图标注关联</title><h1>'+esc(record['input']['name'])+'</h1><p>'+esc(record['notice'])+'</p><ul>'+sources+'</ul>'+content+'<script type="application/json" id="record">'+embedded+'</script></html>'


def register(app,drawings):
    service=DrawingAssociations(drawings)
    @app.post('/api/projects/{project_id}/drawing-associations',status_code=201)
    def create(project_id:str,body:AssociationInput):return service.save(project_id,body)
    @app.get('/api/projects/{project_id}/drawing-associations')
    def listing(project_id:str):
        return [{k:r[k] for k in ('drawingassociation_id','revision','created_at')}|{'name':r['input']['name']}
                for r in service.store.list('drawingassociation',project_id)]
    @app.get('/api/projects/{project_id}/drawing-associations/{association_id}')
    def get(project_id:str,association_id:str):return service.view(project_id,association_id)
    @app.get('/api/projects/{project_id}/drawing-associations/{association_id}/report.html',response_class=HTMLResponse)
    def html_report(project_id:str,association_id:str):return report(service.view(project_id,association_id))
    @app.post('/api/projects/{project_id}/drawing-associations/{association_id}/review')
    def review(project_id:str,association_id:str,body:AssociationReview,request:Request):
        return service.review(project_id,association_id,body,request.state.user['id'])
    @app.get('/api/projects/{project_id}/drawing-associations/{association_id}/history')
    def history(project_id:str,association_id:str):return service.history(project_id,association_id)
    return service
