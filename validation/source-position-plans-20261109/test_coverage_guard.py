import copy,json
import pytest
import freeze_positions as fixtures
import tool_protocol as tools
from coverage_guard import guard

def proposal(case):
 msg={'tool_calls':[{'type':'function','function':{'name':'propose_calculations','arguments':json.dumps({'tasks':case['gold_draft']['tasks']})}}]}
 return tools.decode(case['message'],msg)

def test_omitted_material_layer_is_blocked():
 case=fixtures.CASES[0];r=proposal(case)
 del r['tasks'][0]['sources']['layers.1.thickness'];del r['tasks'][0]['sources']['layers.1.conductivity']
 checked=guard(case['message'],r)
 assert checked['outcome']=='clarify' and not checked['tasks']
 assert {x['quote'] for x in checked['coverage']['unaccounted']}=={'8.2 cm','41 mW/(m K)'}
 assert r['outcome']=='draft' # Do not mutate original proposal.

def test_complete_multi_task_sources_are_accounted():
 case=fixtures.CASES[4];r=guard(case['message'],proposal(case))
 assert r['outcome']=='draft' and r['coverage']['all_source_atoms_accounted']
 assert not r['coverage']['semantics_verified'] and not r['execution_authorized']

def test_old_and_injected_numbers_are_not_silently_excluded():
 for i in [6,7]:
  case=fixtures.CASES[i];r=guard(case['message'],proposal(case))
  assert r['outcome']=='clarify' and r['issue']=='unaccounted_source' and r['coverage']['unaccounted']

@pytest.mark.parametrize('field,value',[('quote','伪造'),('value','999'),('start',999),('ref','s999')])
def test_tampered_source_binding_rejected(field,value):
 case=fixtures.CASES[0];r=proposal(case);r['tasks'][0]['sources']['rsi'][field]=value
 with pytest.raises(ValueError):guard(case['message'],r)

def test_source_revision_change_rejected():
 case=fixtures.CASES[0]
 with pytest.raises(ValueError):guard(case['message']+'更正资料',proposal(case))
