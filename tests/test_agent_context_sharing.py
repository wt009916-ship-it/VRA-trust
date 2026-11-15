"""Exact expansion proves unique evidence and semantics survive wire sharing."""
import copy
import json

from backend import core
from backend.agent_context_sharing import share_catalogs


def test_actual_repeated_catalog_round_trips_without_dropping_any_fact_or_context():
    source = json.loads((core.ROOT / 'fixtures/test/agent_repeated_catalogs.json').read_text(encoding='utf-8'))['messages']
    before = copy.deepcopy(source)
    wire = share_catalogs(source)
    assert source == before
    assert len(json.dumps(wire, ensure_ascii=False)) < len(json.dumps(source, ensure_ascii=False)) - 9000
    expanded = {}; references = []
    def expand(node):
        if isinstance(node, dict):
            ref = node.pop('available_fact_catalog_reference', None)
            if ref:
                value = expanded[ref['tool_call_id']]
                for part in ref['json_pointer'].split('/')[1:]:
                    part = part.replace('~1', '/').replace('~0', '~')
                    value = value[int(part)] if isinstance(value, list) else value[part]
                assert core.hash_json(value) == ref['sha256'] and len(value) == ref['entry_count']
                references.append(ref)
                node['available_fact_catalog'] = copy.deepcopy(value)
            return {k: expand(v) for k, v in node.items()}
        if isinstance(node, list):return [expand(v) for v in node]
        return node
    for original, message in zip(source, wire):
        if message['role'] != 'tool':
            assert message == original
            continue
        content = expand(json.loads(message['content']))
        assert content == json.loads(original['content'])
        expanded[message['tool_call_id']] = content
    assert len(references) == 1 and references[0]['entry_count'] == 77


def test_different_labels_units_and_user_text_are_not_merged():
    catalog = [{'fact': 'fact_' + str(i), 'label': 'original meaning', 'unit': 'kWh'} for i in range(80)]
    modified = copy.deepcopy(catalog); modified[0]['unit'] = 'kW'
    messages = [{'role': 'user', 'content': json.dumps({'available_fact_catalog': catalog})},
                {'role': 'tool', 'tool_call_id': 'one', 'content': json.dumps({'available_fact_catalog': catalog})},
                {'role': 'tool', 'tool_call_id': 'two', 'content': json.dumps({'available_fact_catalog': modified})},
                {'role': 'tool', 'tool_call_id': 'bad', 'content': 'not json'}]
    assert share_catalogs(messages) == messages
