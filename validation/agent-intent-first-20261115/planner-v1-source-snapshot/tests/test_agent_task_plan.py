"""Task planning contracts do not read projects or authorize calculations."""
import copy

import pytest

from backend import agent_task_plan as plans


A = 'thermal_' + 'a' * 32
B = 'thermal_' + 'b' * 32


def argument(items, constraints=(), unassigned=()):
    return {'items': items, 'constraint_fragment_ids': list(constraints), 'unassigned_fragment_ids': list(unassigned)}


def item(operation, **fields):
    return {'item_key': 'one', 'operation': operation, 'question_fragment_ids': ['q1'], **fields}


def test_mixed_read_and_new_request_keeps_separate_obligations_without_inherited_permission():
    history = [{'question': 'Read ' + A, 'professional_references': [{'record_id': A}],
                'allow_compute': True, 'summary': 'UNTRUSTED output 9999', 'facts': [9999]}]
    context = plans.context('Give previous total R. Create another calculation.', history)
    before = copy.deepcopy(context)
    args = argument([item('read_record', record_id=A, fact_keys=['total_resistance_m2k_w'], explanation_topics=[]),
                     {**item('create_calculation', kind='thermal', plan_key=None), 'item_key': 'new'}])
    frozen = plans.freeze(args, context)
    assert context == before
    assert '9999' not in str(context) and 'summary' not in str(context)
    assert frozen['items'][1]['execution_requirements'] == ['current_computation_authorization', 'current_locked_parameter_plan']
    assert not frozen['intent_verified'] and not frozen['executed']
    assert frozen['origin'] == 'model_inferred'


@pytest.mark.parametrize('change', ['invent_source', 'wrong_metric', 'extra_value', 'no_output', 'duplicate_key'])
def test_invalid_outputs_cannot_be_frozen(change):
    context = plans.context('Read total R from ' + A)
    row = item('read_record', record_id=A, fact_keys=['total_resistance_m2k_w'], explanation_topics=[])
    if change == 'invent_source':row['record_id'] = B
    if change == 'wrong_metric':row['fact_keys'] = ['boundary_total_kgco2e']
    if change == 'extra_value':row['value'] = 9999
    if change == 'no_output':row['fact_keys'] = []
    args = argument([row, copy.deepcopy(row)] if change == 'duplicate_key' else [row])
    with pytest.raises(ValueError):plans.freeze(args, context)


def test_fragments_cannot_disappear_but_coverage_does_not_certify_intent():
    context = plans.context('读取编号。另有未识别任务。')
    row = item('other_request', domain='other')
    with pytest.raises(ValueError, match='fragment'):plans.freeze(argument([row]), context)
    result = plans.freeze(argument([row], unassigned=['q2']), context)
    assert result['unassigned_fragment_ids'] == ['q2'] and not result['intent_verified']


@pytest.mark.parametrize('authorized', [False, True])
def test_current_plan_permissions_are_requirements_not_execution(authorized):
    context = plans.context('Create the wall', allow_compute=True,
                            calculation_plans=[{'plan_key': 'wall', 'kind': 'thermal', 'execution_authorized': authorized, 'input': {'private': 'not in context'}}])
    result = plans.freeze(argument([item('create_calculation', kind='thermal', plan_key='wall')]), context)
    assert result['items'][0]['execution_requirements'] == ([] if authorized else ['current_plan_authorization'])
    assert 'private' not in str(context) and not result['executed']


def test_current_plan_cannot_be_retyped_and_discovery_cannot_invent_name():
    context = plans.context('Create wall', allow_compute=True,
                            calculation_plans=[{'plan_key': 'wall', 'kind': 'thermal', 'execution_authorized': True}])
    with pytest.raises(ValueError, match='kind mismatch'):
        plans.freeze(argument([item('create_calculation', kind='cost', plan_key='wall')]), context)
    with pytest.raises(ValueError, match='original question'):
        plans.freeze(argument([item('locate_record', kind='thermal', selection='named', name_from_question='fabricated')]), context)


def test_all_question_fields_and_comparison_direction_are_preserved():
    context = plans.context('Compare ' + A + ' baseline with ' + B + ' candidate; only relative U change.')
    result = plans.freeze(argument([item('compare_records', baseline_id=A, candidate_id=B,
                                        fact_key='u_w_m2k', outputs=['relative_change_percent'])], constraints=['q2']), context)
    assert result['items'][0]['baseline_id'] == A and result['items'][0]['candidate_id'] == B
    assert result['items'][0]['outputs'] == ['relative_change_percent']
