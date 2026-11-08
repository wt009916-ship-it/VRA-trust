"""Source-bound clause retrieval. Declared validity and human review are not certification."""
import re
import threading
import unicodedata
from collections import Counter
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Literal
from pydantic import Field, HttpUrl, StrictInt, model_validator
from . import core
from .domain import identifier
from .schema import Contract
from . import parser_runtime


def normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).casefold()


def parser_hash():
    return core.hash_json({'worker': core.sha(Path(__file__).with_name('standards_worker.py')),
                          'isolated_runtime':parser_runtime.identity('standards'),
                          'resource_policy':core.sha(Path(__file__).with_name('worker_limits.py')), 'pypdf': version('pypdf')})


class Preview(Contract):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')


class Clause(Contract):
    clause_id: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z0-9.()-]+$')
    pdf_page: StrictInt = Field(ge=1, le=500)
    printed_page: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=8, max_length=8000)
    coverage: Literal['excerpt', 'whole_clause'] = 'excerpt'
    transcription: Literal['text_layer', 'manual_scan']
    topic: str = Field(min_length=1, max_length=200)


class StandardInput(Contract):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')
    standard_code: str = Field(min_length=2, max_length=80)
    edition: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=2, max_length=200)
    publisher: str = Field(min_length=2, max_length=200)
    source_url: HttpUrl
    permission: str = Field(min_length=5, max_length=1000)
    jurisdiction: str = Field(min_length=2, max_length=120)
    scope: str = Field(min_length=5, max_length=2000)
    effective_from: date
    retired_on: date | None = None
    status_checked_on: date
    status_basis: str = Field(min_length=10, max_length=2000)
    clauses: list[Clause] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def consistency(self):
        if self.retired_on and self.retired_on <= self.effective_from:
            raise ValueError('Retirement must follow effective date')
        if self.status_checked_on > date.today():
            raise ValueError('Future status verification cannot be claimed')
        if len({c.clause_id for c in self.clauses}) != len(self.clauses):
            raise ValueError('Duplicate clause identifiers')
        if sum(len(c.text) for c in self.clauses) > 200000:
            raise ValueError('Clause index exceeds 200000 characters')
        return self


class Review(Contract):
    expected_revision: StrictInt = Field(ge=1)
    state: Literal['confirmed', 'rejected']
    basis: str = Field(min_length=10, max_length=2000)


class ExactTarget(Contract):
    key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    standard_code: str = Field(min_length=2, max_length=80)
    edition: str | None = Field(default=None, min_length=1, max_length=40)
    clause_id: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z0-9.()-]+$')


class Query(Contract):
    # Surface the same mutually exclusive input forms to clients and tool decoders.
    model_config = {'json_schema_extra': {'oneOf': [
        {'properties': {'targets': {'maxItems': 0}}},
        {'required': ['targets'], 'properties': {
            'targets': {'minItems': 1}, 'text': {'const': ''},
            'standard_code': {'type': 'null'}, 'edition': {'type': 'null'}, 'clause_id': {'type': 'null'}}}
    ]}}
    text: str = Field(default='', max_length=1000)
    standard_code: str | None = Field(default=None, min_length=2, max_length=80)
    edition: str | None = Field(default=None, min_length=1, max_length=40)
    clause_id: str | None = Field(default=None, min_length=1, max_length=60)
    as_of: date
    limit: StrictInt = Field(default=10, ge=1, le=20)
    targets: list[ExactTarget] = Field(default_factory=list, max_length=8, description='Exact batch; leave text and single-query fields empty. Each target is resolved separately.')

    @model_validator(mode='after')
    def bounded(self):
        if self.targets:
            if self.text or self.standard_code or self.edition or self.clause_id:
                raise ValueError('Batch targets cannot be mixed with text or single-query fields')
            if len({t.key for t in self.targets}) != len(self.targets):
                raise ValueError('Each batch target needs a distinct key')
            identities = {(normalized(t.standard_code), normalized(t.edition or ''), normalized(t.clause_id)) for t in self.targets}
            if len(identities) != len(self.targets):
                raise ValueError('Duplicate exact target')
        elif not self.text and not self.clause_id:
            raise ValueError('Provide a query or exact clause identifier')
        if self.as_of > date.today():
            raise ValueError('Future standard validity is not verified')
        if self.edition and not self.standard_code:
            raise ValueError('Edition requires a standard code')
        return self


def tokens(text):
    value = unicodedata.normalize('NFKC', text).casefold()
    result = set(re.findall(r'[a-z0-9]+', value))
    for phrase in re.findall(r'[\u3400-\u9fff]+', value):
        result.update(phrase[i:i+2] for i in range(len(phrase)-1))
        if len(phrase) == 1:
            result.add(phrase)
    return result


class Standards:
    capacity = threading.BoundedSemaphore(2)

    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def preview(self, pid, body):
        source, path = self.domain.file_record(pid, body.file_id)
        if path.suffix != '.pdf' or source['size'] > 20*1024*1024:
            raise core.ValidationError('Provide PDF up to 20 MiB')
        if not self.capacity.acquire(False):
            raise core.ValidationError('PDF parsers busy; retry later')
        try:
            before=parser_hash()
            with parser_runtime.run('standards',path) as scope:
                output = scope['work']/'result.json'
                if not output.exists() or output.stat().st_size > 4*1024*1024:
                    raise core.ValidationError('PDF extraction rejected; original preserved')
                result = core.read_json(output)
                result['resource_limits']=scope['resource_limits']
            self.domain.file_record(pid, body.file_id)
            if parser_hash()!=before:
                raise core.ValidationError('PDF parser changed during processing; retry')
            return {**result, 'source_hash': source['hash'], 'parser_hash': before,
                'notice': '文字层并不证明OCR或条款正确；扫描页需要人工摘录和原件复核。'}
        finally:
            self.capacity.release()

    def save(self, pid, body):
        if len(self.store.list('standard', pid)) >= 50:
            raise core.ValidationError('Project standard index limit is 50 documents')
        extracted = self.preview(pid, Preview(file_id=body.file_id))
        for clause in body.clauses:
            if clause.pdf_page > extracted['page_count']:
                raise core.ValidationError('Clause page is outside source PDF')
            page = extracted['pages'][clause.pdf_page-1]['text']
            if clause.transcription == 'text_layer' and normalized(clause.text) not in normalized(page):
                raise core.ValidationError('Quoted text not found on stated PDF page')
            if clause.transcription == 'text_layer':
                compact = normalized(page)
                marker = re.search(r'(?<![\d.])'+re.escape(normalized(clause.clause_id))+r'(?![\d.])', compact)
                if not marker:
                    raise core.ValidationError('Clause identifier not present on stated page')
                segment = re.split(r'(?<![\d.])\d+(?:\.\d+){2,}(?![\d.])', compact[marker.end():], maxsplit=1)[0]
                if normalized(clause.text) not in segment:
                    raise core.ValidationError('Quote belongs to a different clause or spans a clause boundary')
            if clause.transcription == 'manual_scan' and page.strip():
                raise core.ValidationError('Page has text layer; use matching text or a separately reviewed transcription workflow')
        source, _ = self.domain.file_record(pid, body.file_id)
        obj = {'standard_id': identifier('standard'), 'project_id': pid, 'input': body.model_dump(mode='json'),
            'source': source, 'parser_hash': extracted['parser_hash'], 'page_count': extracted['page_count'],
            'extraction_resource_limits':extracted['resource_limits'],
            'review': {'state':'pending', 'basis':None, 'reviewer_id':None}, 'created_at':core.now()}
        obj['hash'] = core.hash_json(obj)
        self.store.put('standard', obj)
        return self.view(pid, obj['standard_id'])

    def view(self, pid, sid):
        obj = self.store.get('standard', sid)
        if obj['project_id'] != pid:
            raise core.ValidationError('Cross-project standard rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}}) != obj['hash']:
            raise core.ValidationError('Standard record integrity failed')
        stale = obj['parser_hash'] != parser_hash()
        try:
            self.domain.file_record(pid, obj['input']['file_id'])
        except (ValueError, KeyError, OSError):
            stale = True
        return {**obj, 'source_status': 'stale' if stale else 'intact'}

    def review(self, pid, sid, body, reviewer_id):
        obj = self.view(pid, sid)
        if body.state == 'confirmed' and obj['source_status'] != 'intact':
            raise core.ValidationError('Cannot confirm a changed source')
        obj = {k:v for k,v in obj.items() if k not in {'hash','revision','source_status'}}
        obj['review'] = {'state':body.state, 'basis':body.basis, 'reviewer_id':reviewer_id, 'at':core.now()}
        obj['hash'] = core.hash_json(obj)
        self.store.put('standard', obj, body.expected_revision)
        return self.view(pid, sid)

    def catalog(self, pid):
        return [self.view(pid, r['standard_id']) for r in self.store.list('standard', pid)]

    def search(self, pid, body):
        records = self.catalog(pid)
        if not body.targets:
            return self._search(records, body)
        # One verified catalog snapshot for the whole batch, never a Cartesian
        # product of all standard codes and all clause identifiers.
        results = []
        for target in body.targets:
            single = Query(standard_code=target.standard_code, edition=target.edition,
                           clause_id=target.clause_id, as_of=body.as_of, limit=body.limit)
            results.append({'key': target.key, **self._search(records, single)})
        found = sum(r['status'] == 'CITATIONS_FOUND' for r in results)
        return {'status': 'ALL_TARGETS_FOUND' if found == len(results) else
                'PARTIAL_TARGETS_FOUND' if found else 'NO_TARGETS_FOUND',
                'targets': results, 'query': body.model_dump(mode='json'),
                'citations': [{**c, 'target_key': r['key']} for r in results for c in r['citations']],
                'total_matches': sum(r['total_matches'] for r in results),
                'conflicts': sorted({c for r in results for c in r['conflicts']}),
                'excluded': [{**e, 'target_key': r['key']} for r in results for e in r['excluded']],
                'catalog_hash': core.hash_json(records), 'retriever_hash': core.sha(Path(__file__)),
                'notice': '逐项查询明确指定的规范及条款；未找到、版本冲突和排除原因分别保留。各条款的地区、适用范围和版本独立，不自动合并为合规结论。'}

    def _search(self, records, body):
        code, edition, clause_id = body.standard_code, body.edition, body.clause_id
        # An explicit code/clause in a question must never be replaced with a fuzzy match.
        question = unicodedata.normalize('NFKC', body.text)
        expression = r'(?<![A-Za-z0-9])((?:GB|JGJ)(?:/T)?\s*\d+)(?:\s*[-—]\s*(\d{4}))?'
        explicit_refs = list(re.finditer(expression, question, re.I))
        if len({(normalized(m[1]),m[2]) for m in explicit_refs}) > 1:
            raise core.ValidationError('Multiple explicit references require separate exact queries; keyword search can span standards')
        explicit = explicit_refs[0] if explicit_refs else None
        if explicit:
            if code and normalized(code) != normalized(explicit[1]):
                raise core.ValidationError('Conflicting standard codes in query')
            code = explicit[1]
            if edition and explicit[2] and edition != explicit[2]:
                raise core.ValidationError('Conflicting editions in query')
            edition = edition or explicit[2]
        clause_pattern = r'(?<![\d.])\d+(?:\.\d+){2,}(?![\d.])'
        if len(set(re.findall(clause_pattern, question))) > 1:
            raise core.ValidationError('Query exact clauses separately; multiple identifiers cannot be silently dropped')
        detected = re.search(clause_pattern, question)
        if detected:
            if clause_id and clause_id != detected[0]:
                raise core.ValidationError('Conflicting clauses in query')
            clause_id = detected[0]
        filtered = [r for r in records if not code or normalized(r['input']['standard_code']) == normalized(code)]
        candidates, excluded = [], []
        for r in filtered:
            b = r['input']
            reason = None
            if r['source_status'] != 'intact': reason = 'SOURCE_STALE'
            elif r['review']['state'] != 'confirmed': reason = 'NOT_REVIEWED'
            elif body.as_of.isoformat() < b['effective_from']: reason = 'NOT_YET_EFFECTIVE'
            elif b['retired_on'] and body.as_of.isoformat() >= b['retired_on']: reason = 'RETIRED'
            elif body.as_of.isoformat() > b['status_checked_on']: reason = 'VALIDITY_RECHECK_REQUIRED'
            if reason: excluded.append({'standard_id':r['standard_id'], 'reason':reason})
            else: candidates.append(r)
        counts = Counter(normalized(r['input']['standard_code']) for r in candidates)
        conflicts = sorted(k for k,v in counts.items() if v > 1)
        hits = []
        terms = tokens(body.text)
        for r in candidates:
            b = r['input']
            if normalized(b['standard_code']) in conflicts or (edition and edition != b['edition']): continue
            for c in b['clauses']:
                if clause_id and clause_id != c['clause_id']: continue
                score = 1.0 if clause_id else len(terms & tokens(c['topic']+' '+c['text']))/max(1,len(terms))
                if score == 0: continue
                hits.append({'standard_id':r['standard_id'], 'revision':r['revision'], 'standard_code':b['standard_code'],
                    'edition':b['edition'], 'title':b['title'], 'jurisdiction':b['jurisdiction'], 'scope':b['scope'],
                    **c, 'score':round(score,6), 'source_url':b['source_url'], 'file_id':b['file_id'],
                    'source_hash':r['source']['hash'], 'quote_hash':core.hash_json(c), 'review':r['review'],
                    'validity': 'USER_REVIEWED_AS_OF_DATE_NOT_AUTOMATIC_AUTHORITY_CHECK'})
        hits.sort(key=lambda h:(-h['score'],h['standard_code'],h['edition'],h['clause_id']))
        return {'status':'VERSION_CONFLICT' if conflicts else 'CITATIONS_FOUND' if hits else 'NOT_FOUND_IN_REVIEWED_INDEX',
            'citations':hits[:body.limit], 'total_matches':len(hits), 'conflicts':conflicts, 'excluded':excluded,
            'query':body.model_dump(mode='json'), 'catalog_hash':core.hash_json(records), 'retriever_hash':core.sha(Path(__file__)),
            'notice':'只检索本项目已复核条款索引；未命中不证明条款不存在。摘录不等于完整条文。有效期和适用范围仍需工程师核对，不生成合规结论。'}

    def query(self, pid, body):
        result = self.search(pid, body)
        obj = {'normquery_id':identifier('normquery'), 'project_id':pid, 'result':result, 'created_at':core.now(),
               'retriever_hash':core.sha(Path(__file__))}
        obj['hash'] = core.hash_json(obj)
        self.store.put('normquery', obj)
        return obj

    def query_view(self, pid, qid):
        obj = self.store.get('normquery', qid)
        if obj['project_id'] != pid: raise core.ValidationError('Cross-project query rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}}) != obj['hash']:
            raise core.ValidationError('Query integrity failed')
        stale = obj['retriever_hash'] != core.sha(Path(__file__)) or obj['result']['catalog_hash'] != core.hash_json(self.catalog(pid))
        return {**obj, 'status':'stale' if stale else 'current', 'result':None if stale else obj['result']}
