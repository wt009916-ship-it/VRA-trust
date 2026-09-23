"""Node dependencies and immutable carbon derivations over verified physics runs."""
import inspect
import uuid

from pydantic import Field

from . import core
from .schema import Contract


class Factor(Contract):
    value: float = Field(ge=0, le=100)
    unit: str = "kgCO2/kWh"
    source: str = Field(min_length=5, max_length=2000)
    factor_id: str = Field(min_length=1, max_length=200)


class FactorUpdate(Contract):
    expected_revision: int = Field(ge=0)
    region: str = Field(min_length=1, max_length=40)
    scenario: bool
    factors: dict[str, Factor] = Field(max_length=20)


def calculator_version():
    return core.hash_json(inspect.getsource(core.calculate_carbon))


def descendants(nodes, changed):
    """Validate a DAG, then return transitive descendants in topological order."""
    index = {n['id']: n for n in nodes}
    if len(index) != len(nodes):
        raise core.ValidationError('Duplicate claim ID')
    ordered, visiting, visited = [], set(), set()
    def visit(key):
        if key not in index:
            raise core.ValidationError('Unknown claim dependency')
        if key in visiting:
            raise core.ValidationError('Claim graph contains a cycle')
        if key in visited:
            return
        visiting.add(key)
        for dep in index[key]['depends_on']:
            visit(dep)
        visiting.remove(key)
        visited.add(key)
        ordered.append(key)
    for key in index:
        visit(key)
    affected = set(changed)
    if not affected <= index.keys():
        raise core.ValidationError('Unknown changed claim')
    for key in ordered:
        if affected.intersection(index[key]['depends_on']):
            affected.add(key)
    return [key for key in ordered if key in affected]


class Trust:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def factor(self, project_id):
        records = self.store.list('factor', project_id)
        return records[0] if records else None

    def update_factor(self, project_id, body):
        project = self.store.get('project', project_id)
        profile = {'profile_id': 'project-factor', **body.model_dump(exclude={'expected_revision'})}
        if profile['region'] not in {'*', project['building']['region']}:
            raise core.ValidationError('碳因子地区与项目不匹配')
        # Validate every declared unit/provenance, including not-yet-used carriers.
        core.calculate_carbon({k: 1 for k in profile['factors']}, profile, project['building']['region'])
        old = self.factor(project_id)
        return self.store.put('factor', {'factor_id': old['factor_id'] if old else 'factor_' + project_id.split('_', 1)[1],
            'project_id': project_id, 'profile': profile, 'hash': core.hash_json(profile), 'timestamp': core.now()}, body.expected_revision)

    def current_profile(self, job):
        custom = self.factor(job['project_id'])
        if custom:
            return custom['profile']
        try:
            return core.get_profile(job['factor_profile_id'])
        except core.ValidationError:
            return {'profile_id': 'missing', 'region': '*', 'factors': {}, 'scenario': False}

    def carbon_view(self, job, raw):
        profile = self.current_profile(job)
        profile_hash = core.hash_json(profile)
        derived = [d for d in self.store.list('carbon', job['project_id']) if d['run_id'] == job['run_id']]
        if derived:
            latest = derived[0]
            if latest['factor_hash'] == profile_hash and latest['calculator_version'] == calculator_version():
                result_file = self.store.root / 'runs' / job['run_id'] / 'result.json'
                payload = {k: v for k, v in latest.items() if k not in {'revision', 'hash'}}
                if latest['source_result_hash'] != core.sha(result_file) or latest['hash'] != core.hash_json(payload):
                    raise core.ValidationError('Carbon derivation integrity failed')
                return {**latest['result'], 'node_state': 'VALID', 'derivation_id': latest['carbon_id'], 'provenance': payload, 'factor_snapshot': profile}
        elif profile_hash == core.hash_json(job['factor_snapshot']):
            return {**raw, 'node_state': 'VALID', 'derivation_id': None, 'factor_snapshot': profile}
        return {'node_state': 'STALE', 'status': 'stale', 'operating_carbon_kg': None,
                'profile_hash': profile_hash, 'factor_snapshot': profile, 'scenario': profile.get('scenario', False), 'reason': '碳因子或碳计算版本已更新；能耗保持有效，请仅重算碳排。'}

    def recalculate(self, run_id):
        view = self.domain.view(run_id)
        if view['status'] != 'succeeded' or not view['metrics']:
            raise core.ValidationError('Only a currently valid physics result can be reused')
        job = self.store.job(run_id)
        profile = self.current_profile(job)
        obj = {'carbon_id': 'carbon_' + uuid.uuid4().hex, 'project_id': job['project_id'], 'run_id': run_id,
               'factor_snapshot': profile, 'factor_hash': core.hash_json(profile), 'timestamp': core.now(),
               'calculator_version': calculator_version(), 'source_result_hash': core.sha(self.store.root / 'runs' / run_id / 'result.json'),
               'result': core.calculate_carbon(view['metrics']['energy_by_carrier_kwh'], profile, job['project_snapshot']['building']['region']),
               'energyplus_calls': 0}
        obj['hash'] = core.hash_json(obj)
        self.store.put('carbon', obj)
        return self.domain.view(run_id)

    def graph(self, run_id, view, evidence_nodes):
        state = 'VALID' if view['status'] == 'succeeded' else 'STALE' if view['status'] == 'stale' else 'UNKNOWN'
        carbon = view.get('carbon') or {}
        cs = carbon.get('node_state', state)
        if cs == 'VALID' and carbon.get('operating_carbon_kg') is None:
            cs = 'MISSING'
        # Use the exact factor snapshot already validated with this result.
        # A concurrent edit must not attach a different factor to this graph.
        profile = carbon.get('factor_snapshot')
        if profile is None:
            profile = self.current_profile(self.store.job(run_id))
        def node(suffix, kind, label, status, deps, value=None):
            return {'id': run_id + suffix, 'kind': kind, 'label': label, 'state': status, 'depends_on': deps, 'value': value}
        metrics = view.get('metrics') or {}
        nodes = evidence_nodes + [
            node('', 'Simulation', 'EnergyPlus', state, [n['id'] for n in evidence_nodes]),
            node(':energy', 'Metric', '全年场地能耗', state, [run_id], metrics.get('annual_energy_kwh')),
            node(':area', 'Parameter', 'SQL 建筑面积', state, [run_id], metrics.get('area_m2')),
            node(':eui', 'Metric', 'EUI', state, [run_id + ':energy', run_id + ':area'], metrics.get('eui_kwh_m2a')),
            {**node(':factor', 'Evidence', '运行碳因子', 'ASSUMPTION' if profile.get('scenario') else 'VALID', []), 'hash': core.hash_json(profile)},
            node(':carbon', 'Metric', '运行碳排', cs, [run_id + ':energy', run_id + ':factor'], carbon.get('operating_carbon_kg')),
            node(':decision', 'Decision', '确定推荐：尚缺成本、舒适性与稳定性证据', 'UNKNOWN', [run_id + ':eui', run_id + ':carbon']),
            node(':certificate', 'Certificate', '决策证书草稿', 'PARTIALLY_STALE' if cs == 'STALE' and state == 'VALID' else 'STALE' if state == 'STALE' else 'UNKNOWN', [run_id + ':decision'])]
        affected = descendants(nodes, [run_id + ':factor'])
        return {'run_id': run_id, 'nodes': nodes, 'scope': 'node-level provenance',
                'factor_change_affected': affected, 'recomputation_plan': ['carbon.calculate', 'certificate.generate'] if cs == 'STALE' and state == 'VALID' else [],
                'energyplus_required': state != 'VALID'}
