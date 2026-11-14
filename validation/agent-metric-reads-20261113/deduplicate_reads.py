from pathlib import Path
p=Path('backend/agent_actions.py')
s=p.read_text(encoding='utf-8')
s=s.replace("    for action in actions:\n","    prior_read = None\n    for action in actions:\n")
needle="        calls.append({'id':'action_'"
i=s.index(needle)
s=s[:i]+'''        # A repeated adjacent metric read in one response has no intervening
        # observation. Keep the original message for audit and execute it once.
        read_key = None
        if action['tool'] in {'utility_comparison_read', 'end_use_read', 'professional_read_many'}:
            read_key = (action['tool'], json.dumps(action['arguments'], sort_keys=True))
        if read_key is not None and read_key == prior_read:
            continue
        prior_read = read_key
'''+s[i:]
p.write_text(s,encoding='utf-8')
p=Path('tests/test_agent_actions.py')
with p.open('a',encoding='utf-8') as f:f.write('''

def test_adjacent_identical_reads_run_once_with_original_response_retained():
    definitions = simple_tools()
    definitions[0]['function']['name'] = 'professional_read_many'
    def action(fact):
        return {'tool': 'professional_read_many', 'arguments': {'fact': fact}}
    actions = [action('R'), action('R'), action('U'), action('R')]
    raw = {'role': 'assistant', 'content': json.dumps({'actions': actions})}
    decoded = agent_actions.decode(raw, definitions)
    assert [json.loads(c['function']['arguments'])['fact'] for c in decoded['tool_calls']] == ['R', 'U', 'R']
    assert decoded['_raw_action_response'] == raw
''')
