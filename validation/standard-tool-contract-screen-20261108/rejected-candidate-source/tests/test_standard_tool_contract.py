"""Decoder-facing branches preserve actual server bounds and refusal rules."""
import copy
import pytest
from pydantic import ValidationError
from backend.agent import Agent, ToolArgs
from backend.standards import Query


def schema():
    return Agent.__new__(Agent).tools({'standards_search'})[0]['function']['parameters']


def test_decoder_uses_complete_disjoint_objects_without_mutating_api_schema():
    before = copy.deepcopy(Query.model_json_schema())
    actual = schema()
    definition = actual['$defs']['Query']
    assert set(definition) == {'oneOf'}
    single, batch = definition['oneOf']
    assert single['type'] == batch['type'] == 'object'
    assert single['additionalProperties'] is batch['additionalProperties'] is False
    assert set(single['properties']) == {'text','standard_code','edition','clause_id','retrieval','as_of','limit'}
    assert single['required'] == ['as_of']
    assert set(batch['properties']) == {'targets','as_of','limit'}
    assert set(batch['required']) == {'as_of','targets'}
    assert batch['properties']['targets']['minItems'] == 1
    assert batch['properties']['targets']['maxItems'] == 8
    assert batch['properties']['targets']['items'] == {'$ref':'#/$defs/ExactTarget'}
    assert single['properties']['text']['maxLength'] == 1000
    assert single['properties']['retrieval']['enum'] == ['lexical','semantic']
    for branch in (single,batch):
        assert branch['properties']['limit']['minimum'] == 1
        assert branch['properties']['limit']['maximum'] == 20
        assert branch['properties']['as_of']['format'] == 'date'
    assert actual['$defs']['ExactTarget']['additionalProperties'] is False
    assert Query.model_json_schema() == before


def test_batch_omitted_fields_resolve_to_canonical_server_defaults():
    body={'as_of':'2025-06-15','targets':[{'key':'left','standard_code':'QA 810','clause_id':'3.4.1'}]}
    query=ToolArgs(standards_query=body).standards_query
    assert query.retrieval == 'lexical' and query.text == ''
    assert query.standard_code is query.edition is query.clause_id is None
    assert query.limit == 10 and len(query.targets) == 1
    assert Query(text='thermal',as_of='2025-06-15',retrieval='semantic').retrieval == 'semantic'


@pytest.mark.parametrize('extra',[
    {'text':'thermal'}, {'retrieval':'semantic'}, {'standard_code':'QA 810'},
    {'edition':'2025'}, {'clause_id':'3.4.1'}, {'limit':True}, {'limit':21},
    {'as_of':'2099-01-01'}, {'unexpected':'ignored'},
])
def test_server_still_rejects_mixed_or_invalid_inputs(extra):
    body={'as_of':'2025-06-15','targets':[{'key':'left','standard_code':'QA 810','clause_id':'3.4.1'}],**extra}
    with pytest.raises(ValidationError):
        ToolArgs(standards_query=body)
