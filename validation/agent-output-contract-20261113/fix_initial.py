exec(open('D:/稀土agent-稀土制暖全流程/outputs/agent-contract-20261113/implement.py',encoding='utf-8').read().split("edit('backend/agent_outputs.py'")[0])
edit('backend/agent_semantics.py',"'explanation_instruction': statement_instruction()\n", "'explanation_instruction': statement_instruction() +\n")
edit('tests/test_agent_explicit_outputs.py', "Agent.tools({'requested_output_plan'})", "Agent.tools(None, {'requested_output_plan'})")
