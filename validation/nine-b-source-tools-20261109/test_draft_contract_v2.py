import copy,json
from pathlib import Path
import pytest
import draft_contract_v2 as v2
from source_catalog import catalog
BASE=Path(__file__).resolve().parent
F=json.loads((BASE/'frozen.json').read_text(encoding='utf-8'))
def actual(t,step=1):
 row=json.loads((BASE/'first-run'/f'{t}-{step}.json').read_text(encoding='utf-8'))
 case=next(x for x in F['tasks'] if x['id']==t)['steps'][step-1]
 return case,json.loads(row['raw_response'])['choices'][0]['message'],row

def test_observed_opposite_films_cannot_pass_new_schema():
 case,message,_=actual('T05')
 with pytest.raises(Exception):v2.decode(case['message'],message)

def test_observed_null_layers_rejected_without_trimming():
 case,message,_=actual('T13');before=copy.deepcopy(message)
 with pytest.raises(Exception):v2.decode(case['message'],message)
 assert message==before

def test_actual_correct_multi_task_and_shared_films_remain_structurally_valid():
 for name in ['T02','T03']:
  case,message,_=actual(name);r=v2.decode(case['message'],message)
  assert r['outcome']=='draft' and len(r['tasks'])==2
  assert not r['role_guard']['semantics_verified'] and not r['execution_authorized']

def test_independent_role_guard_withdraws_observed_swap():
 case,_,row=actual('T05');r=v2.guard_roles(case['message'],row['review'])
 assert r['outcome']=='clarify' and not r['tasks'] and len(r['role_guard']['issues'])==2

@pytest.mark.parametrize('label,roles',[('内表面热阻：',{'rsi'}),('外侧膜为',{'rse'}),('Rsi=',{'rsi'}),('R_se ',{'rse'}),('内外膜均',{'rsi','rse'}),('膜阻未分类 ',None)])
def test_explicit_labels_and_unknown_text(label,roles):
 text=label+'0.17 m2 K/W';a=catalog(text).atoms[0]
 assert v2.film_roles(text,a)==roles

def test_missing_units_remove_only_unfulfillable_proposal_kind():
 specs=v2.tools('材料导热系数未知，只有厚度57 mm')
 assert {x['function']['name'] for x in specs}=={'clarify_calculation','reject_calculation'}

def test_duplicate_complete_layer_refs_require_multiplicity_review():
 case,_,row=actual('T01');r=copy.deepcopy(row['review']);task=r['tasks'][0]
 for field in ('thickness','conductivity','correction'):task['sources']['layers.1.'+field]=copy.deepcopy(task['sources']['layers.0.'+field])
 checked=v2.guard_roles(case['message'],r)
 assert checked['outcome']=='clarify' and not checked['tasks']
