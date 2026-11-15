from pathlib import Path
s=Path('D:/稀土agent-稀土制暖全流程/outputs/agent-phase-20261113/implement.py').read_text(encoding='utf-8')
header=s[:s.index("(ROOT/'backend/agent_actions.py')")]
tail=s[s.index("edit('backend/agent.py',\"            offered = {'project_get'}\""):]
tail=tail.replace("            offered = {'project_get'}","            offered={'project_get'}").replace("            offered = {'project_get','requested_defer'}","            offered={'project_get','requested_defer'}")
exec(header+tail)
edit('backend/agent.py',"offered -= {'requested_availability', 'requested_output_plan', 'professional_review'}", "offered -= {'requested_availability', 'requested_output_plan', 'professional_review', 'requested_defer'}")
edit('backend/agent.py',"                            read_records.append((ds, observed))", "                            read_records=[(old_spec,old) for old_spec,old in read_records if old[old_spec.record_key]!=observed[ds.record_key]]\n                            read_records.append((ds, observed))")
edit('backend/agent_actions.py',"        calls.append({'id':'action_'", "        try:encoded=json.dumps(action['arguments'],ensure_ascii=False,allow_nan=False)\n        except (ValueError,RecursionError):reject('invalid numeric or nested arguments')\n        calls.append({'id':'action_'")
edit('backend/agent_actions.py',"'name':action['tool'],'arguments':json.dumps(action['arguments'],ensure_ascii=False,allow_nan=False)}})","'name':action['tool'],'arguments':encoded}})")
print('Remaining integration complete')
