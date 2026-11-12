from pathlib import Path
p=Path('D:/稀土agent-稀土制暖全流程/outputs/agent-phase-20261113/probe.py')
s=p.read_text(encoding='utf-8').replace("/probe'","/probe-json'")
s=s.replace("'choice':'required'","'choice':'json_schema_action'")
s=s.replace("'P1'","'P4'").replace("'P2'","'P5'").replace("'P3'","'P6'")
s=s.replace("'tool_choice':'required',", "'response_format':{'type':'json_schema','json_schema':{'name':'read_or_defer','strict':True,'schema':{'type':'object','properties':{'action':{'type':'string','enum':['read_temperature','read_power','defer_request']}},'required':['action'],'additionalProperties':False}}},")
s=s.replace("'tools':tools,'response_format'", "'response_format'")
s=s.replace("'protocol_pass':bool(calls) and not (msg.get('content') or '').strip()", "'protocol_pass': isinstance(json.loads(msg.get('content') or '{}'),dict) and set(json.loads(msg.get('content') or '{}'))=={'action'} and json.loads(msg['content'])['action'] in {'read_temperature','read_power','defer_request'}")
p.with_name('probe_json.py').write_text(s,encoding='utf-8')
