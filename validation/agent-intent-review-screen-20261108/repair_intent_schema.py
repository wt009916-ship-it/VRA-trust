from pathlib import Path
import hashlib,json
root=Path('C:/Users/18483/AppData/Local/Temp/vra-agent-intent-review-20261108')
results=Path('C:/Users/18483/AppData/Local/Temp/vra-intent-review-model-20261108/candidate/results.json')
receipt=json.loads(results.read_text(encoding='utf-8'))
assert receipt.get('completed') and receipt.get('server_stopped'), 'Do not mutate sources during the frozen run'
p=root/'backend/agent_outputs.py'
source=p.read_text(encoding='utf-8')
start=source.index('        if enforce_modes:\n')
end=source.index("    parameters.pop('$defs')",start)
replacement='''        if enforce_modes:
            # llama.cpp does not support properties beside oneOf/anyOf.
            # Expand mutually exclusive complete object branches instead.
            delivery = copy.deepcopy(item)
            delivery['properties'].update(clarification_reason={'type': 'null'},
                                          clarification_question={'type': 'null'})
            if entry['purpose'] == 'results':
                numeric = copy.deepcopy(delivery)
                numeric['properties']['fact_keys']['minItems'] = 1
                explanatory = copy.deepcopy(delivery)
                explanatory['properties']['fact_keys']['maxItems'] = 0
                explanatory['properties']['explanation_topics']['minItems'] = 1
                variants.extend([numeric, explanatory])
            else:
                variants.append(delivery)
            clarification = copy.deepcopy(item)
            clarification['required'] += ['clarification_reason', 'clarification_question']
            clarification['properties'].update(
                clarification_reason={'type': 'string', 'enum': [
                    'metric_not_available', 'ambiguous_request', 'conflicting_request']},
                clarification_question={'type': 'string', 'minLength': 1, 'maxLength': 400},
                fact_keys={'type': 'array', 'maxItems': 0},
                explanation_topics={'type': 'array', 'maxItems': 0})
            variants.append(clarification)
        else:
            variants.append(item)
'''
p.write_text(source[:start]+replacement+source[end:],encoding='utf-8',newline='\n')
t=root/'tests/test_agent_intent_review.py'
with t.open('a',encoding='utf-8',newline='\n') as out:
    out.write('''

def test_review_schema_has_no_unsupported_mixed_object_branches(client):
    requests = [{'request_key': 'wall', 'kind': 'thermal', 'purpose': 'results',
                 'record_id': 'thermal_' + 'a' * 32}]
    schema = agent_outputs.constrain_tool(
        client.app.state.agent.tools({'requested_output_plan'})[0], requests,
        'Return U.', enforce_modes=True)['function']['parameters']

    def visit(node):
        if isinstance(node, dict):
            assert not ('properties' in node and ('oneOf' in node or 'anyOf' in node))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    variants = schema['properties']['output_plan']['items']['oneOf']
    assert len(variants) == 3
    assert all(set(['request_key', 'question_fragment_ids', 'fact_keys',
                    'explanation_topics']).issubset(v['required']) for v in variants)
''')
print(json.dumps({'fixed_file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                  'first_arm_preserved':True,'change':'schema branch expansion only; no prompt, test or oracle edits'}))
