"""Declared rectangular two-dimensional steady conduction, with current provenance."""
import html
import json
import threading
import uuid
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import Field, StrictFloat, model_validator

from . import core, thermal_bridge_solver as solver
from .calculation_provenance import persist, validity, version as provenance_version
from .schema import Contract
from .task_capacity import CapacityError


class Region(Contract):
    name: str = Field(min_length=1, max_length=100)
    x0: StrictFloat = Field(ge=0)
    x1: StrictFloat = Field(gt=0)
    y0: StrictFloat = Field(ge=0)
    y1: StrictFloat = Field(gt=0)
    conductivity: StrictFloat | None = Field(default=None, gt=0, le=1000000)
    conductivity_unit: Literal['W/(m K)', 'mW/(m K)']
    source: str = Field(min_length=3, max_length=1000)


class Boundary(Contract):
    mode: Literal['adiabatic', 'fixed_temperature', 'film']
    temperature_c: StrictFloat | None = Field(default=None, ge=-100, le=200)
    resistance_m2k_w: StrictFloat | None = Field(default=None, gt=0, le=10)
    basis: str = Field(min_length=3, max_length=1000)

    @model_validator(mode='after')
    def matching_fields(self):
        if self.mode == 'adiabatic' and (self.temperature_c is not None or self.resistance_m2k_w is not None):
            raise ValueError('Adiabatic boundary cannot also prescribe temperature or film resistance')
        if self.mode == 'fixed_temperature' and self.resistance_m2k_w is not None:
            raise ValueError('Fixed surface temperature is distinct from an air/film boundary')
        return self


class Boundaries(Contract):
    left: Boundary
    right: Boundary
    bottom: Boundary
    top: Boundary


class Probe(Contract):
    name: str = Field(min_length=1, max_length=60)
    x: StrictFloat = Field(ge=0)
    y: StrictFloat = Field(ge=0)


class Section(Contract):
    name: str = Field(min_length=1, max_length=160)
    width: StrictFloat = Field(gt=0)
    height: StrictFloat = Field(gt=0)
    length_unit: Literal['m', 'cm', 'mm']
    geometry_source: str = Field(min_length=3, max_length=2000)
    application: str = Field(min_length=3, max_length=2000)
    regions: list[Region] = Field(min_length=1, max_length=32)
    boundaries: Boundaries
    cell_size: StrictFloat = Field(gt=0)
    probes: list[Probe] = Field(default_factory=list, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode='after')
    def geometry(self):
        scale = {'m': 1, 'cm': .01, 'mm': .001}[self.length_unit]
        if not all(1e-6 <= v * scale <= 100 for v in (self.width, self.height, self.cell_size)):
            raise ValueError('Dimensions and cell size must be within 0.000001..100 m')
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError('Select distinct evidence identifiers')
        names = set()
        for region in self.regions:
            if not (0 <= region.x0 < region.x1 <= self.width and 0 <= region.y0 < region.y1 <= self.height):
                raise ValueError('Rectangles must have positive dimensions and lie inside the section')
            if region.name.casefold() in names:
                raise ValueError('Use distinct region names')
            names.add(region.name.casefold())
            k = None if region.conductivity is None else region.conductivity * (1 if region.conductivity_unit == 'W/(m K)' else .001)
            if k is not None and not 1e-5 <= k <= 1000:
                raise ValueError('Conductivity must be within 0.00001..1000 W/(m K)')
        if all(b.mode == 'adiabatic' for b in (self.boundaries.left, self.boundaries.right, self.boundaries.bottom, self.boundaries.top)):
            raise ValueError('At least one temperature or film boundary is required')
        for point in self.probes:
            if point.x > self.width or point.y > self.height:
                raise ValueError('Probe lies outside the section')
            sides = []
            for on_side, boundary in [(point.x == 0, self.boundaries.left), (point.x == self.width, self.boundaries.right),
                                      (point.y == 0, self.boundaries.bottom), (point.y == self.height, self.boundaries.top)]:
                if on_side and boundary.mode == 'fixed_temperature' and boundary.temperature_c is not None:
                    sides.append(boundary.temperature_c)
            if len(set(sides)) > 1:
                raise ValueError('A corner with conflicting fixed temperatures has no unique probe value')
        # Check coverage and the finer-grid budget even when a conductivity is missing.
        normal = normalize(self)
        for region in normal['regions']:
            if region['conductivity'] is None:
                region['conductivity'] = 1.  # Geometry-only validation, never used for calculation.
        solver.mesh(normal, normal['cell_size'] / 2)
        return self


def normalize(body):
    scale = {'m': 1, 'cm': .01, 'mm': .001}[body.length_unit]
    regions = []
    for r in body.regions:
        k = None if r.conductivity is None else r.conductivity * (1 if r.conductivity_unit == 'W/(m K)' else .001)
        regions.append({'name': r.name, **{key: getattr(r, key) * scale for key in ('x0', 'x1', 'y0', 'y1')}, 'conductivity': k})
    return {'width': body.width * scale, 'height': body.height * scale, 'cell_size': body.cell_size * scale,
            'regions': regions, 'boundaries': body.boundaries.model_dump(),
            'probes': [{'name': p.name, 'x': p.x * scale, 'y': p.y * scale} for p in body.probes]}


def calculate(body):
    missing = [f'regions[{i}].conductivity' for i, r in enumerate(body.regions) if r.conductivity is None]
    data = normalize(body)
    for name, b in data['boundaries'].items():
        if b['mode'] != 'adiabatic' and b['temperature_c'] is None:
            missing.append('boundaries.' + name + '.temperature_c')
        if b['mode'] == 'film' and b['resistance_m2k_w'] is None:
            missing.append('boundaries.' + name + '.resistance_m2k_w')
    if missing:
        return {'status': 'incomplete', 'missing': missing, 'temperature_c': None,
                'boundary_heat_into_domain_w_per_m': None, 'mesh_check': None, 'compliance_status': 'NOT_ASSESSED'}
    return {**solver.calculate(data), 'missing': [], 'normalized_input': data}


def version():
    return core.hash_json({'contract': provenance_version(Path(__file__)), 'solver': core.sha(Path(solver.__file__)), 'numpy': np.__version__})


class ThermalBridge:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store
        self.capacity = threading.BoundedSemaphore(1)

    def save(self, pid, body):
        if not self.capacity.acquire(blocking=False):
            raise CapacityError('二维导热计算正在运行，请等待当前计算结束后重试')
        try:
            project = self.store.get('project', pid)
            snapshots = []
            for eid in body.evidence_ids:
                evidence = self.store.get('evidence', eid)
                if evidence['project_id'] != pid or evidence['review_state'] == 'rejected':
                    raise core.ValidationError('Foreign or rejected thermal-bridge evidence')
                if evidence['source_file']:
                    self.domain.file_record(pid, evidence['source_file'])
                snapshots.append(evidence)
            before = version()
            try:
                result = calculate(body)
            except ValueError as exc:
                raise core.ValidationError(str(exc)) from exc
            record = {'thermalbridge_id': 'thermalbridge_' + uuid.uuid4().hex, 'project_id': pid,
                      'project_revision': project['revision'], 'input': body.model_dump(), 'result': result,
                      'calculator_version': before, 'evidence_snapshot': snapshots, 'created_at': core.now()}
            record['hash'] = core.hash_json(record)
            def same_solver():
                if version() != before:
                    raise core.ValidationError('Conduction solver changed during calculation')
            persist(self.domain, 'thermalbridge', record, pre_insert_check=same_solver)
            return self.view(pid, record['thermalbridge_id'])
        finally:
            self.capacity.release()

    def view(self, pid, ident):
        record = self.store.get('thermalbridge', ident)
        if record['project_id'] != pid:
            raise core.ValidationError('Cross-project thermal-bridge record refused')
        if core.hash_json({k: v for k, v in record.items() if k not in {'hash', 'revision'}}) != record['hash']:
            raise core.ValidationError('Thermal-bridge record integrity failed')
        provenance = validity(self.domain, record, version())
        stale = bool(provenance['stale_reasons'])
        return {**record, **provenance, 'status': 'stale' if stale else record['result']['status'],
                'result': None if stale else record['result'], 'source_status': 'USER_DECLARED',
                'source_notice': '来源绑定及人工复核不自动证明截面、材料或边界工况真实；没有标准认证。'}


def report(record):
    result = record['result']
    def text(value):
        return '—' if value is None else html.escape(str(value))
    summary = '<p>来源或计算器版本发生变化，当前结果不可用。</p>'
    if result and result['status'] == 'incomplete':
        summary = '<p>缺失输入：' + text(', '.join(result['missing'])) + '；未进入求解器。</p>'
    elif result:
        summary = ('<h2>边界热流（W/m 延伸长度，正值进入截面）</h2><table><tr><th>边界</th><th>热流</th></tr>' +
                   ''.join('<tr><td>' + text(s) + '</td><td>' + text(round(q, 6)) + '</td></tr>' for s, q in result['boundary_heat_into_domain_w_per_m'].items()) +
                   '</table><p>热平衡残差：' + text(result['energy_balance_w_per_m']) + ' W/m</p><h2>指定位置温度（°C）</h2>' +
                   '<table><tr><th>位置</th><th>x / m</th><th>y / m</th><th>温度 / °C</th></tr>' +
                   ''.join('<tr>' + ''.join('<td>' + text(p[k]) + '</td>' for k in ('name', 'x', 'y', 'temperature_c')) + '</tr>' for p in result['probes']) + '</table>' +
                   '<h2>网格与线性求解检查</h2><pre>' + text(json.dumps({k: result[k] for k in ('mesh_check', 'linear_solver')}, ensure_ascii=False, indent=2)) + '</pre>')
    # Large temperature arrays have a separate CSV/JSON download, not a multi-MB printout.
    audit = {k: v for k, v in record.items() if k != 'result'}
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>二维导热记录</title>'
            '<style>body{font:16px/1.7 system-ui;max-width:1100px;margin:32px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:8px}</style>'
            '<h1>' + html.escape(record['input']['name']) + '</h1><p>状态：' + html.escape(record['status']) +
            '。二维恒定物性数值计算；不是完整热桥标准验证或节能合规结论。needs_refinement 表示网格未通过，数值仅作诊断。</p>' +
            summary + '<h2>输入、来源及版本</h2><pre>' + html.escape(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False)) + '</pre></html>')
