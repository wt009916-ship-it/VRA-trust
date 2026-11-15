"""Read-bound mathematical comparisons; no model numbers or engineering equivalence."""
import copy
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import Field, model_validator
from .schema import Contract
from . import core, agent_selections
from .agent_semantics import inspection, check, Delivery, accumulate

KINDS = {'thermal', 'cost', 'lifecycle'}
NOTICE = '仅比较当前记录中同一指标；相对变化=(对照−基准)/基准×100%。声明口径一致不证明功能等效、全年节能、合规、安全或可交易碳资产。'


class Comparison(Contract):
    baseline_id: str = Field(pattern=r'^(thermal|cost|lifecycle)_[a-f0-9]{32}$')
    baseline_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    candidate_id: str = Field(pattern=r'^(thermal|cost|lifecycle)_[a-f0-9]{32}$')
    candidate_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    fact_key: str = Field(min_length=1, max_length=100)
    outputs: list[Literal['difference', 'relative_change_percent']] = Field(min_length=1, max_length=2)
    finish: bool = False

    @model_validator(mode='after')
    def coherent(self):
        if self.baseline_id == self.candidate_id or self.baseline_id.split('_')[0] != self.candidate_id.split('_')[0]:
            raise ValueError('Choose two distinct records of the same supported kind')
        if len(set(self.outputs)) != len(self.outputs):
            raise ValueError('Choose distinct requested comparison outputs')
        return self


def context(source, kind):
    body = source['input']
    fields = {'thermal': ('rsi_m2k_w', 'rse_m2k_w', 'surface_basis', 'application'),
              'cost': ('currency', 'tax_basis', 'region', 'as_of', 'functional_scope'),
              'lifecycle': ('area_m2', 'study_years', 'region', 'method', 'functional_unit', 'replacement_scope')}
    result = {key: body[key] for key in fields[kind]}
    if kind == 'cost':
        result['exclusions'] = sorted(body['exclusions'])
    if kind == 'lifecycle':
        result['boundaries'] = sorted((b['stage'], b['included'], b['reason']) for b in body['boundaries'])
        activities = body['activities'] + [p['activity'] for c in body['replacements'] for p in c['processes'] if p.get('activity')]
        # A changed factor basis must be reviewed explicitly, never hidden in a percentage.
        result['factor_bases'] = sorted({tuple(a['factor'][k] for k in ('publisher', 'version', 'year', 'region', 'method')) for a in activities})
    return result


def arithmetic(baseline, candidate, outputs):
    with localcontext() as ctx:
        ctx.prec = 50
        base, other = Decimal(baseline), Decimal(candidate)
        if not base.is_finite() or not other.is_finite():
            raise core.ValidationError('Comparison requires finite source numbers')
        difference = other - base
        values = {}
        if 'difference' in outputs:
            values['difference'] = str(difference)
        if 'relative_change_percent' in outputs:
            values['relative_change_percent'] = str(difference / base * 100) if base else None
        return values


def evaluate(domain, pid, task, request):
    """Validate actual selected receipts, then recheck both original source services."""
    kind = request.baseline_id.split('_')[0]
    spec = inspection(kind)
    sources, facts, deliveries = [], [], []
    for role in ('baseline', 'candidate'):
        ident, digest = getattr(request, role + '_id'), getattr(request, role + '_hash')
        numeric, _ = agent_selections.materialize(task, {'kind': kind, 'record_id': ident,
            'record_hash': digest, 'fact_keys': [request.fact_key], 'finish': False})
        source = spec.service(domain).view(pid, ident)
        accepted = check(source, Delivery.model_validate(numeric))
        if not spec.artifact(source)['verified'] or accepted['statements'][0]['source_value'] is None:
            raise core.ValidationError('Comparison requires current complete numeric source results')
        sources.append(source); facts.append(accepted['statements'][0]); deliveries.append(numeric)
    contexts = [context(s, kind) for s in sources]
    mismatch = sorted(k for k in contexts[0] if contexts[0][k] != contexts[1][k])
    for key in ('fact', 'unit', 'period', 'study_years', 'area_m2', 'area_basis', 'energy_context'):
        if facts[0].get(key) != facts[1].get(key):
            mismatch.append('metric.' + key)
    # Same factor ID with altered contents is an unresolved version conflict.
    if kind == 'lifecycle':
        factor_maps = []
        for source in sources:
            body = source['input']
            acts = body['activities'] + [p['activity'] for c in body['replacements'] for p in c['processes'] if p.get('activity')]
            factor_maps.append({a['factor']['factor_id']: a['factor'] for a in acts})
        if any(factor_maps[0][k] != factor_maps[1][k] for k in factor_maps[0].keys() & factor_maps[1].keys()):
            mismatch.append('factor_identity_conflict')
    reference = request.model_dump(mode='json')
    row = {'status': 'unavailable' if mismatch else 'verified', 'reference': reference,
           'kind': kind, 'fact_key': request.fact_key, 'label': facts[0]['label'], 'unit': facts[0]['unit'],
           'context': contexts[0] if not mismatch else None, 'mismatches': mismatch,
           'baseline': None, 'candidate': None, 'values': None, 'unavailable_reason': None,
           'notice': NOTICE, 'source_value_policy': 'original source_value, not rounded display'}
    if not mismatch:
        row.update(baseline=facts[0]['source_value'], candidate=facts[1]['source_value'],
                   values=arithmetic(facts[0]['source_value'], facts[1]['source_value'], request.outputs))
        if 'relative_change_percent' in request.outputs and Decimal(row['baseline']) == 0:
            row['unavailable_reason'] = 'zero_baseline_relative_change_undefined'
    else:
        row['unavailable_reason'] = 'comparison_context_mismatch'
    previous = task.get('professional_deliveries', [])
    if len({x['record_id'] for x in previous + deliveries}) > 3:
        raise core.ValidationError('At most three professional source records per task')
    for delivery in deliveries:
        previous = accumulate(previous, delivery)
    saved = task.get('professional_comparisons', [])
    key = lambda x: (x['reference']['baseline_id'], x['reference']['candidate_id'], x['reference']['fact_key'])
    if len(saved) >= 3 and not any(key(x) == key(row) for x in saved):
        raise core.ValidationError('At most three comparisons per task')
    task['professional_deliveries'] = previous
    task['professional_comparisons'] = [x for x in saved if key(x) != key(row)] + [row]
    return row


def attach(answer, task):
    """Source deliveries were revalidated by current_answer; never reuse withdrawn values."""
    if not task.get('professional_comparisons'):
        return answer
    result = copy.deepcopy(answer)
    present = {(s['record_id'], f['fact']): f for s in answer.get('checked_statements', []) for f in s['facts']}
    hashes = {d['record_id']: d['record_hash'] for d in task.get('professional_deliveries', [])}
    rows = []
    for saved in task['professional_comparisons']:
        row = copy.deepcopy(saved); ref = row['reference']
        current = [present.get((ref[role + '_id'], ref['fact_key'])) for role in ('baseline', 'candidate')]
        if (any(f is None or f['source_value'] is None for f in current)
                or any(hashes.get(ref[role + '_id']) != ref[role + '_hash'] for role in ('baseline', 'candidate'))):
            row.update(status='stale', baseline=None, candidate=None, values=None, context=None,
                       unavailable_reason='source_no_longer_current')
        elif row['status'] == 'verified':
            row.update(baseline=current[0]['source_value'], candidate=current[1]['source_value'],
                       values=arithmetic(current[0]['source_value'], current[1]['source_value'], ref['outputs']))
        rows.append(row)
    result['checked_comparisons'] = rows
    result['verification'] = result.get('verification', []) + [
        {'check': 'current_record_comparison', 'passed': row['status'] == 'verified',
         'baseline_id': row['reference']['baseline_id'], 'candidate_id': row['reference']['candidate_id'],
         'fact_key': row['fact_key'], 'meaning': '仅核验声明口径和数学差值，不证明功能等效或原问题完整覆盖'} for row in rows]
    if any(r['status'] == 'stale' for r in rows):
        result['gaps'] = result.get('gaps', []) + [{'message': '比较来源已失效，当前差值已撤下', 'action': '重新核验来源，不复用历史差值'}]
    return result


def candidates(task):
    rows = {}
    for event in task['events']:
        if event['status'] != 'succeeded':
            continue
        for kind in KINDS:
            spec = inspection(kind)
            if event['tool'] == spec.read_tool:
                source = event['result']; ident = source[spec.record_key]
                from .agent_semantics import model_projection
                facts = model_projection(source, kind)['explanation_facts']
                rows[ident] = (kind, source['hash'], [f['fact'] for f in facts if f['source_value'] is not None])
    return [(a, b, x, y, sorted(set(x[2]) & set(y[2]))) for a, x in rows.items() for b, y in rows.items()
            if a != b and x[0] == y[0] and set(x[2]) & set(y[2])]


def tool_schema(tool, task):
    result = copy.deepcopy(tool); variants = []
    for a, b, x, y, keys in candidates(task):
        schema = Comparison.model_json_schema(); props = schema['properties']
        for key, value in [('baseline_id', a), ('candidate_id', b), ('baseline_hash', x[1]), ('candidate_hash', y[1])]:
            props[key] = {'type': 'string', 'const': value}
        props['fact_key'] = {'type': 'string', 'enum': keys}
        schema['required'] = list(props)
        variants.append(schema)
    result['function']['parameters'] = {'type': 'object', 'properties': {'comparison': {'oneOf': variants}},
        'required': ['comparison'], 'additionalProperties': False}
    return result
