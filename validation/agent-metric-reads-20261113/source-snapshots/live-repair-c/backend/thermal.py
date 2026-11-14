"""Auditable, one-dimensional steady-state opaque assembly calculations."""
import html
import json
import math
import uuid
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictFloat, model_validator

from .calculation_provenance import validity, persist, version as provenance_version
from . import core
from .schema import Contract


class Layer(Contract):
    name: str = Field(min_length=1, max_length=100)
    thickness: StrictFloat | None = Field(default=None, gt=0, le=10000)
    thickness_unit: Literal['m', 'cm', 'mm']
    conductivity: StrictFloat | None = Field(default=None, gt=0, le=100000)
    conductivity_unit: Literal['W/(m K)', 'mW/(m K)']
    correction_factor: StrictFloat = Field(default=1, ge=1, le=10)
    correction_basis: str = Field(min_length=3, max_length=1000)
    source: str = Field(min_length=3, max_length=1000)
    evidence_id: str | None = None


class Assembly(Contract):
    name: str = Field(min_length=1, max_length=160)
    layers: list[Layer] = Field(min_length=1, max_length=40)
    rsi_m2k_w: StrictFloat | None = Field(default=None, ge=0, le=2)
    rse_m2k_w: StrictFloat | None = Field(default=None, ge=0, le=2)
    surface_basis: str = Field(min_length=3, max_length=1000)
    application: str = Field(min_length=3, max_length=2000)

    @model_validator(mode='after')
    def coherent_materials(self):
        seen = {}
        for layer in self.layers:
            thickness, conductivity = normalize(layer)
            if thickness is not None and not .000001 <= thickness <= 10:
                raise ValueError('Layer thickness outside supported 0.000001..10 m range')
            if conductivity is not None and not .000001 <= conductivity <= 100:
                raise ValueError('Conductivity outside supported 0.000001..100 W/(m K) range')
            key = layer.name.casefold()
            if key in seen and conductivity is not None and seen[key] is not None and not math.isclose(seen[key], conductivity, rel_tol=1e-12):
                raise ValueError('Conflicting conductivity for the same material: ' + layer.name)
            if conductivity is not None:
                seen[key] = conductivity
        return self


def normalize(layer):
    d = None if layer.thickness is None else layer.thickness * {'m': 1, 'cm': .01, 'mm': .001}[layer.thickness_unit]
    k = None if layer.conductivity is None else layer.conductivity * (1 if layer.conductivity_unit == 'W/(m K)' else .001)
    return d, k


def calculate(body):
    rows, missing = [], []
    for i, layer in enumerate(body.layers):
        d, k = normalize(layer)
        effective = None if k is None else k * layer.correction_factor
        resistance = None if d is None or effective is None else core.number(d / effective, 'layer resistance', positive=True)
        if resistance is None:
            missing.append(f'layers[{i}].thickness/conductivity')
        rows.append({**layer.model_dump(), 'thickness_m': d, 'conductivity_w_mk': k,
                     'effective_conductivity_w_mk': effective, 'resistance_m2k_w': resistance,
                     'formula': 'R = thickness_m / (conductivity_w_mk * correction_factor)'})
    layer_r = None if missing else core.number(math.fsum(r['resistance_m2k_w'] for r in rows), 'layer resistance sum', positive=True)
    for name in ('rsi_m2k_w', 'rse_m2k_w'):
        if getattr(body, name) is None:
            missing.append(name)
    total = None if missing else core.number(layer_r + body.rsi_m2k_w + body.rse_m2k_w, 'total resistance', positive=True)
    return {'status': 'incomplete' if missing else 'calculated', 'layers': rows, 'missing': missing,
            'layer_resistance_m2k_w': layer_r, 'total_resistance_m2k_w': total,
            'u_w_m2k': None if total is None else core.number(1 / total, 'U', positive=True),
            'formula': 'R_total = Rsi + sum(d / lambda_effective) + Rse; U = 1 / R_total',
            'compliance_status': 'NOT_ASSESSED', 'energy_saving_rate': None,
            'limitations': ['一维稳态、均匀连续不透明材料层；不包含热桥、窗框、空气层辐射/对流或结露校核。',
                           '导热系数与修正系数由用户提供；含湿、温度、老化影响未自动推断。',
                           '表面热阻必须按实际工况提供；本工具不默认套用规范限值，也不证明节能合规。',
                           'U值下降不等于建筑全年节能率；未自动修改IDF或联动年度仿真。']}


def version():
    return provenance_version(Path(__file__))


class Thermal:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def save(self, project_id, body, *, expected_bindings=None):
        project = self.store.get('project', project_id)
        snapshots = []
        for eid in sorted({layer.evidence_id for layer in body.layers if layer.evidence_id}):
            ev = self.store.get('evidence', eid)
            if ev['project_id'] != project_id:
                raise core.ValidationError('Cross-project thermal evidence rejected')
            if ev['review_state'] == 'rejected':
                raise core.ValidationError('Rejected thermal evidence cannot support a new calculation')
            if ev['source_file']:
                self.domain.file_record(project_id, ev['source_file'])
            snapshots.append(ev)
        obj = {'thermal_id': 'thermal_' + uuid.uuid4().hex, 'project_id': project_id,
               'project_revision': project['revision'], 'input': body.model_dump(), 'result': calculate(body),
               'calculator_version': version(), 'evidence_snapshot': snapshots, 'created_at': core.now()}
        obj['hash'] = core.hash_json(obj)
        record = persist(self.domain, 'thermal', obj, expected_bindings)
        return self.view(project_id, record['thermal_id'])

    def view(self, project_id, thermal_id):
        obj = self.store.get('thermal', thermal_id)
        if obj['project_id'] != project_id:
            raise core.ValidationError('Cross-project thermal record rejected')
        payload = {k: v for k, v in obj.items() if k not in {'hash', 'revision'}}
        if core.hash_json(payload) != obj['hash']:
            raise core.ValidationError('Thermal record integrity failed')
        provenance = validity(self.domain, obj, version())
        stale = provenance['stale_reasons']
        verified = bool(obj['evidence_snapshot']) and all(
            layer['evidence_id'] and any(ev['evidence_id'] == layer['evidence_id'] and ev['review_state'] == 'confirmed'
                and ev['status'] not in {'ASSUMED', 'AI_INFERRED', 'MISSING'} for ev in obj['evidence_snapshot']) for layer in obj['input']['layers'])
        return {**obj, 'status': 'stale' if stale else obj['result']['status'],
                'result': None if stale else obj['result'], **provenance,
                'source_status': 'HUMAN_REVIEWED_SOURCES' if verified and not stale else 'USER_DECLARED',
                'source_notice': '来源人工复核不代表材料性能实测或法定认证。'}


class ThermalCompare(Contract):
    thermal_ids: list[str] = Field(min_length=2, max_length=5)


def compare(service, project_id, body):
    if len(set(body.thermal_ids)) != len(body.thermal_ids):
        raise core.ValidationError('Select distinct thermal calculations')
    rows = [service.view(project_id, tid) for tid in body.thermal_ids]
    if any(r['status'] != 'calculated' for r in rows):
        raise core.ValidationError('Only current complete thermal calculations can be compared')
    contexts = {(r['input']['rsi_m2k_w'], r['input']['rse_m2k_w'], r['input']['surface_basis'], r['input']['application']) for r in rows}
    if len(contexts) != 1:
        raise core.ValidationError('Thermal comparison requires identical surface and application conditions')
    base = rows[0]['result']['u_w_m2k']
    return {'baseline_id': body.thermal_ids[0], 'results': [
        {'thermal_id': r['thermal_id'], 'name': r['input']['name'], 'u_w_m2k': r['result']['u_w_m2k'],
         'u_reduction_pct': (1 - r['result']['u_w_m2k'] / base) * 100} for r in rows],
        'note': '仅比较相同边界条件下的U值，U下降比例不是全年能耗节能率。', 'recommendation': None}


def render_html(record):
    def text(value):
        return '—' if value is None else html.escape(str(value))
    result = record['result']
    summary = '<p>当前结果不可用，来源或计算器变更后须重新计算。</p>'
    if result:
        summary = '<table><thead><tr><th>材料</th><th>厚度 m</th><th>有效导热系数 W/(m K)</th><th>热阻 m²K/W</th></tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join('<td>' + text(layer[k]) + '</td>' for k in
                ('name', 'thickness_m', 'effective_conductivity_w_mk', 'resistance_m2k_w')) + '</tr>'
            for layer in result['layers']) + '</tbody></table><p>总热阻：' + text(result['total_resistance_m2k_w']) + \
            ' m²K/W；U：' + text(result['u_w_m2k']) + ' W/(m²K)</p>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>围护结构热工计算记录</title>' + \
        '<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:32px auto;padding:20px}td,th{padding:10px;border:1px solid #bbb}table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>' + \
        '<h1>围护结构热工计算记录</h1><h2>' + text(record['input']['name']) + '</h2>' + \
        '<p>未签署；一维稳态计算，不是节能合规结论。U下降不等于建筑节能率。</p>' + summary + \
        '<h2>完整输入、来源与计算过程</h2><pre>' + html.escape(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)) + '</pre></html>'
