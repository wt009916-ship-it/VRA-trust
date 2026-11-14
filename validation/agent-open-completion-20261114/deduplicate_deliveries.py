from pathlib import Path
p=Path('backend/agent_actions.py');s=p.read_text(encoding='utf-8')
needle="        calls.append({'id':'action_'"
i=s.index(needle)
s=s[:i]+'''        if calls and action['tool'] in {'professional_deliver', 'professional_limit'}:
            previous = calls[-1]['function']
            if previous['name'] == action['tool']:
                field = 'delivery' if action['tool'] == 'professional_deliver' else 'limitation'
                previous_args = json.loads(previous['arguments'])
                previous_body = previous_args.get(field, {})
                current_body = action['arguments'].get(field, {})
                previous_identity = {k: v for k, v in previous_body.items() if k != 'finish'}
                current_identity = {k: v for k, v in current_body.items() if k != 'finish'}
                if previous_identity == current_identity:
                    previous_body['finish'] = bool(previous_body.get('finish') or current_body.get('finish'))
                    previous['arguments'] = json.dumps(previous_args, ensure_ascii=False, allow_nan=False)
                    continue
'''+s[i:]
p.write_text(s,encoding='utf-8')
p=Path('tests/test_agent_actions.py')
with p.open('a',encoding='utf-8') as f:f.write('''

def test_same_response_delivery_duplicates_preserve_finish_and_distinct_facts():
    definition = {'type':'function','function':{'name':'professional_deliver','parameters':{
        'type':'object','properties':{'delivery':{'type':'object'}}}}}
    def selected(key, finish):
        return {'tool':'professional_deliver','arguments':{'delivery':{
            'kind':'thermal','record_id':'thermal_a','record_hash':'same',
            'fact_keys':[key],'finish':finish}}}
    raw={'role':'assistant','content':json.dumps({'actions':[
        selected('R',False),selected('R',True),selected('R',False),selected('U',False)]})}
    decoded=agent_actions.decode(raw,[definition])
    args=[json.loads(call['function']['arguments'])['delivery'] for call in decoded['tool_calls']]
    assert [(a['fact_keys'],a['finish']) for a in args]==[(['R'],True),(['U'],False)]
    assert decoded['_raw_action_response']==raw
''')
