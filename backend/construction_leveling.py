"""Bounded serial schedule generation on declared renewable resources, in exact micro-days."""
import time
from fractions import Fraction

from .construction import decimal, ordered

SCALE = 1_000_000
MAX_OPERATIONS = 2_000_000
MAX_SECONDS = 3.0


def integer(value):
    return int(decimal(value) * SCALE)


def day(value):
    whole, part = divmod(value, SCALE)
    return str(whole) if not part else f'{whole}.{part:06d}'.rstrip('0')


class Exhausted(Exception):
    pass


class Budget:
    def __init__(self):
        self.operations = 0
        self.started = time.monotonic()

    def step(self, count=1):
        self.operations += count
        if self.operations > MAX_OPERATIONS or time.monotonic() - self.started > MAX_SECONDS:
            raise Exhausted


def calculate(body, priority, demands_complete):
    """Earlier priority wins among eligible tasks; insertion can precede earlier scheduled tasks."""
    tasks, topology, _ = ordered(body.tasks)
    if len(priority) != len(tasks) or set(priority) != set(tasks):
        raise ValueError('Priority must list every source task exactly once')
    base = {'method': 'serial_sgs_insertion_v1', 'time_unit': 'continuous_elapsed_day',
        'precision_days': '0.000001', 'site_safety': 'NOT_ASSESSED',
        'optimality': 'not_proven', 'schedule': None, 'lower_bound': None,
        'limitations': ['固定可再生资源容量、固定占用、非抢占工序、FS非负间隔；按连续经过日计算。',
            '优先序决定符合前置条件的下一工序；允许插入已安排工序之前的空档。不是所有优先序的搜索。',
            '只核对声明资料，不证明现场可施工、资源已落实、专业工序适用或履约保证。',
            '零工期里程碑不占用资源；无占用工序必须由提交者明确确认，未声明资源不纳入约束。']}
    reasons = []
    if not demands_complete: reasons.append('resource_demands_not_confirmed')
    if body.progress is not None: reasons.append('progress_present_requires_separate_plan_snapshot')
    if not body.resources: reasons.append('no_declared_resources')
    reasons += ['duration_missing:' + t.task_id for t in body.tasks if t.duration_days is None]
    reasons += ['capacity_missing:' + r.resource_id for r in body.resources if r.capacity is None]
    if reasons: return {**base, 'status': 'incomplete', 'reasons': reasons}
    capacities = {r.resource_id: integer(r.capacity) for r in body.resources}
    durations = {k: integer(t.duration_days) for k, t in tasks.items()}
    demands = {k: {d.resource_id: integer(d.units) for d in t.demands} for k, t in tasks.items()}
    excess = [{'task_id': k, 'resource_id': r} for k in topology if durations[k] > 0
              for r, units in demands[k].items() if units > capacities[r]]
    if excess:
        return {**base, 'status': 'constraints_unresolved', 'reasons': ['single_task_exceeds_capacity'], 'excess': excess}
    budget = Budget()
    try:
        cpm, workload = {}, {r: 0 for r in capacities}
        for k in topology:
            budget.step()
            start = max((cpm[d.task_id][1] + integer(d.lag_days) for d in tasks[k].predecessors), default=0)
            cpm[k] = (start, start + durations[k])
            for r, units in demands[k].items(): workload[r] += durations[k] * units
        cpm_duration = max(end for _, end in cpm.values())
        bounds = [('precedence', Fraction(cpm_duration))] + [
            (r, Fraction(workload[r], capacities[r])) for r in capacities if capacities[r] > 0]
        lower = max(value for _, value in bounds)
        intervals = {r: [] for r in capacities}
        starts, sequence = {}, []
        remaining = list(priority)
        while remaining:
            budget.step(len(remaining))
            k = next(key for key in remaining if all(d.task_id in starts for d in tasks[key].predecessors))
            remaining.remove(k)
            start = max((starts[d.task_id][1] + integer(d.lag_days) for d in tasks[k].predecessors), default=0)
            duration = durations[k]
            blocked = []
            if duration:
                for r, required in demands[k].items():
                    events = {}
                    for left, right, units in intervals[r]:
                        budget.step()
                        events[left] = events.get(left, 0) + units
                        events[right] = events.get(right, 0) - units
                    points, used = sorted(events), 0
                    for index, point in enumerate(points[:-1]):
                        budget.step()
                        used += events[point]
                        if used + required > capacities[r]: blocked.append((point, points[index + 1]))
                for left, right in sorted(blocked):
                    budget.step()
                    if start < right and start + duration > left: start = right
            finish = start + duration
            starts[k] = (start, finish)
            sequence.append(k)
            if duration:
                for r, units in demands[k].items(): intervals[r].append((start, finish, units))
        # Separate final sweep verifies all declared inequalities before publishing any schedule.
        peaks = []
        for r, values in intervals.items():
            events = {}
            for start, finish, units in values:
                budget.step()
                events[start] = events.get(start, 0) + units
                events[finish] = events.get(finish, 0) - units
            used, peak = 0, 0
            for point in sorted(events):
                budget.step()
                used += events[point]
                peak = max(peak, used)
                if used < 0 or used > capacities[r]: raise ValueError('Final resource verification failed')
            if used: raise ValueError('Unbalanced resource profile')
            peaks.append({'resource_id': r, 'peak_units': day(peak), 'capacity_units': day(capacities[r])})
        for k, (start, finish) in starts.items():
            budget.step()
            if finish - start != durations[k] or any(start < starts[d.task_id][1] + integer(d.lag_days) for d in tasks[k].predecessors):
                raise ValueError('Final precedence verification failed')
        duration = max(end for _, end in starts.values())
        if duration < lower: raise ValueError('Schedule contradicts lower bound')
        lower_days = lower / SCALE
        return {**base, 'status': 'calculated', 'reasons': [], 'operations': budget.operations,
            'schedule': {'duration_days': day(duration), 'cpm_duration_days': day(cpm_duration),
                'delay_vs_cpm_days': day(duration - cpm_duration), 'selection_sequence': sequence,
                'rows': [{'task_id': k, 'name': tasks[k].name, 'start_day': day(starts[k][0]),
                    'finish_day': day(starts[k][1]), 'cpm_start_day': day(cpm[k][0]),
                    'start_delay_days': day(starts[k][0] - cpm[k][0])} for k in topology],
                'resource_peaks': peaks, 'constraints_verified': True},
            'lower_bound': {'days_floor_6dp': day(lower.numerator // lower.denominator),
                'exact_days_numerator': str(lower_days.numerator), 'exact_days_denominator': str(lower_days.denominator),
                'basis': ['CPM ignores resources', 'For each resource: sum(duration * demand) / capacity'],
                'attained': Fraction(duration) == lower},
            'optimality': 'lower_bound_attained_for_declared_model' if Fraction(duration) == lower else 'not_proven'}
    except Exhausted:
        return {**base, 'status': 'constraints_unresolved', 'reasons': ['execution_budget_exhausted'],
                'operations': budget.operations, 'budget': {'operations': MAX_OPERATIONS, 'seconds': MAX_SECONDS}}
