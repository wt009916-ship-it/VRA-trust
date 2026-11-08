"""Source/permission protocol tests; scripted ranking is not real-model evidence."""
import copy
import pytest
from pydantic import ValidationError
from backend import core, semantic_runtime, agent_standards
from backend.standards import Query
from backend.semantic_worker import validate
from test_standards import setup, save, query


@pytest.fixture
def ranking(monkeypatch):
    calls = []
    monkeypatch.setattr(semantic_runtime, 'identity', lambda: 'test-runtime-v1')
    def rank(text, documents):
        calls.append((text, copy.deepcopy(documents)))
        return {'rankings': [{'key': d['key'], 'score': 0.8 - i * 0.1, 'span': [0, len(d['text'])]} for i, d in enumerate(documents)],
                'documents': len(documents), 'chunks': len(documents), 'truncated': False,
                'model': 'scripted-protocol-only', 'revision': 'test', 'runtime_hash': 'test-runtime-v1', 'resource_limits': {}}
    monkeypatch.setattr(semantic_runtime, 'rank', rank)
    return calls


def test_semantic_candidate_has_exact_source_but_no_confidence_or_answer_claim(client, ranking):
    _, base, body = setup(client); source = save(client, base, body)
    response = query(client, base, text='Different words for a source question', retrieval='semantic')
    assert response.status_code == 201, response.text
    result = response.json()['result']
    assert result['status'] == 'RELEVANCE_REVIEW_REQUIRED'
    assert result['retrieval']['confidence'] is None and not result['retrieval']['relevance_verified']
    assert result['citations'][0]['text'] == body['clauses'][0]['text']
    assert result['citations'][0]['source_hash'] == source['source']['hash']
    assert not result['citations'][0]['relevance_verified'] and ranking


@pytest.mark.parametrize('text,code,count', [('9.9.9 nonexistent insulation', None, 0), ('GB 99999-2024 insulation', None, 0), ('1.0.1', 'TEST 100', 1)])
def test_explicit_reference_never_gets_semantic_substitute(client, ranking, text, code, count):
    _, base, body = setup(client); save(client, base, body)
    response = query(client, base, text=text, standard_code=code, retrieval='semantic')
    assert response.status_code == 201
    assert len(response.json()['result']['citations']) == count and not ranking


def test_unreviewed_and_past_validity_never_reach_embedding(client, ranking):
    _, base, body = setup(client); save(client, base, body, False)
    assert not query(client, base, retrieval='semantic').json()['result']['citations'] and not ranking
    # Rejected sources have no inference dependency even when model is absent.
    assert query(client, base, retrieval='semantic').status_code == 201


def test_model_runtime_withdrawal_revokes_saved_and_agent_results_only(client, monkeypatch, ranking):
    pid, base, body = setup(client); save(client, base, body)
    sem = query(client, base, retrieval='semantic').json()
    lex = query(client, base).json()
    event = {'tool': 'standards_search', 'status': 'succeeded', 'result': sem['result'], 'result_hash': core.hash_json(sem['result'])}
    record = {'events': [event]}
    assert agent_standards.attach({}, client.app.state.domain, pid, record)['checked_standards']
    monkeypatch.setattr(semantic_runtime, 'identity', lambda: 'test-runtime-v2')
    now = client.get(base + '/standard-queries/' + sem['normquery_id']).json()
    assert now['status'] == 'stale' and now['result'] is None
    assert client.get(base + '/standard-queries/' + lex['normquery_id']).json()['status'] == 'current'
    assert not agent_standards.attach({}, client.app.state.domain, pid, record)['checked_standards']


def test_source_withdrawn_during_ranking_cannot_be_saved(client, monkeypatch, ranking):
    pid, base, body = setup(client); saved = save(client, base, body)
    original = semantic_runtime.rank
    def racing(text, documents):
        result = original(text, documents)
        response = client.post(base + '/standards/' + saved['standard_id'] + '/review', json={
            'expected_revision': saved['revision'], 'state': 'rejected', 'basis': 'Withdraw during isolated scripted inference.'})
        assert response.status_code == 200
        return result
    monkeypatch.setattr(semantic_runtime, 'rank', racing)
    response = query(client, base, retrieval='semantic')
    assert response.status_code == 409
    assert not client.app.state.domain.store.list('normquery', pid)


def test_missing_runtime_is_error_not_lexical_fallback(client, monkeypatch):
    _, base, body = setup(client); save(client, base, body)
    monkeypatch.delenv('VRA_SEMANTIC_MODEL_DIR', raising=False)
    assert query(client, base, retrieval='semantic').status_code == 409
    assert query(client, base).status_code == 201


def test_semantic_batch_is_rejected_and_source_filter_precedes_ranking(client, ranking):
    assert Query.model_json_schema()['oneOf'][1]['properties']['retrieval'] == {'const': 'lexical'}
    with pytest.raises(ValidationError):
        Query(retrieval='semantic', targets=[{'key': 'a', 'standard_code': 'TEST', 'clause_id': '1.0.1'}], as_of='2025-01-01')
    _, base, body = setup(client); save(client, base, body)
    assert not query(client, base, retrieval='semantic', as_of='2025-01-02').json()['result']['citations']
    assert not ranking


def test_no_corpus_truncation_or_duplicate_keys():
    with pytest.raises(ValueError):
        validate({'query': 'q', 'documents': [{'key': str(i), 'text': 'text'} for i in range(2001)]})
    with pytest.raises(ValueError):
        validate({'query': 'q', 'documents': [{'key': 'same', 'text': 'text'}] * 2})
    with pytest.raises(core.ValidationError):
        semantic_runtime.rank('q', [{'key': 'same', 'text': 'text'}] * 2)


@pytest.mark.parametrize('changed', [
    {'documents': True}, {'chunks': True}, {'truncated': True},
    {'rankings': [{'key': 'foreign', 'score': 0.8, 'span': [0, 4]}]},
    {'rankings': [{'key': 'a', 'score': float('nan'), 'span': [0, 4]}]},
    {'rankings': [{'key': 'a', 'score': 0.8, 'span': [0, 5]}]},
    {'rankings': []},
])
def test_native_ranking_cannot_drop_sources_or_inject_invalid_values(changed):
    result = {'documents': 1, 'chunks': 1, 'truncated': False,
              'rankings': [{'key': 'a', 'score': 0.8, 'span': [0, 4]}]}
    result.update(changed)
    with pytest.raises(core.ValidationError):
        semantic_runtime.validate_result(result, [{'key': 'a', 'text': 'text'}])
