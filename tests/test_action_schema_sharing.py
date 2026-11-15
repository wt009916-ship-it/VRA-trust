"""Captured overflow contract, independent malformed actions and exact expansion."""
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from backend import agent_actions, core
from backend.agent_schema_sharing import compact_choices


def frozen():
    return json.loads((core.ROOT / 'fixtures/test/agent_large_read_catalog.json').read_text(encoding='utf-8'))


def test_captured_overflow_contract_shares_all_meanings_without_removing_tools():
    original = frozen()
    before = copy.deepcopy(original)
    result = agent_actions.schema(original['tools'])
    assert original == before
    shared = {k: v for k, v in result.get('$defs', {}).items() if k.startswith('vra_shared_choices_')}
    assert shared

    def expand(node):
        if isinstance(node, dict):
            if set(node) == {'$ref'} and node['$ref'].split('/')[-1] in shared:
                return copy.deepcopy(shared[node['$ref'].split('/')[-1]])
            return {k: expand(v) for k, v in node.items()}
        if isinstance(node, list):
            return [expand(v) for v in node]
        return node

    expanded = expand(result)
    for name in shared:
        expanded['$defs'].pop(name)
    if not expanded['$defs'] and '$defs' not in original['unshared_schema']:
        expanded.pop('$defs')
    assert expanded == original['unshared_schema']
    assert len(json.dumps(result, ensure_ascii=False)) < 25000
    assert len(json.dumps(original['unshared_schema'], ensure_ascii=False)) > 34000


@pytest.mark.parametrize('change,valid', [
    ('valid', True), ('batch', True), ('unknown_fact', False), ('duplicate_fact', False),
    ('too_many', False), ('wrong_record', False), ('null', False), ('extra_field', False),
])
def test_original_and_shared_contracts_accept_the_same_actions(change, valid):
    data = frozen()
    parameters = next(t['function']['parameters'] for t in data['tools'] if t['function']['name'] == 'end_use_read')
    props = parameters['oneOf'][0]['properties']
    ident = props['enduse_id']['const']
    keys = props['fact_keys']['items']['enum']
    action = {'tool': 'end_use_read', 'arguments': {'enduse_id': ident, 'fact_keys': keys[:2]}}
    if change == 'batch':
        action = {'tool': 'professional_read_many', 'arguments': {'selections': [{'record_id': ident, 'fact_keys': keys[:2]}]}}
    if change == 'unknown_fact':
        action['arguments']['fact_keys'] = ['invented.credit_issuance']
    if change == 'duplicate_fact':
        action['arguments']['fact_keys'] = [keys[0], keys[0]]
    if change == 'too_many':
        action['arguments']['fact_keys'] = keys[:13]
    if change == 'wrong_record':
        action['arguments']['enduse_id'] = 'enduse_' + 'f' * 32
    if change == 'null':
        action['arguments']['fact_keys'] = None
    if change == 'extra_field':
        action['arguments']['engine_override'] = 'unapproved'
    for schema in (data['unshared_schema'], agent_actions.schema(data['tools'])):
        assert Draft202012Validator(schema).is_valid({'actions': [action]}) is valid


def test_distinct_constraints_scopes_and_literal_data_are_not_conflated():
    choices = {'type': 'array', 'items': {'type': 'string', 'enum': ['field_' + str(i) for i in range(50)]}, 'maxItems': 2}
    original = {'type': 'object', 'properties': {'a': choices, 'b': copy.deepcopy(choices),
        'c': {**choices, 'maxItems': 3}}, 'examples': [{'a': choices}],
        '$defs': {'vra_shared_choices_0': {'type': 'integer'}}}
    shared = compact_choices(original)
    assert shared['properties']['a']['$ref'] == shared['properties']['b']['$ref']
    assert shared['properties']['c']['maxItems'] == 3
    assert shared['examples'] == original['examples']
    assert shared['$defs']['vra_shared_choices_0'] == {'type': 'integer'}
    scoped = {**original, '$id': 'https://example.invalid/a-schema'}
    assert compact_choices(scoped) == scoped
