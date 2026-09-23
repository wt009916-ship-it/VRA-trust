"""Engineer-confirmed drawing coordinates -> deterministic wall geometry."""
import math
import uuid
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import core
from .schema import Contract


class Wall(Contract):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    x1: float = Field(ge=-1000, le=1000)
    z1: float = Field(ge=-1000, le=1000)
    x2: float = Field(ge=-1000, le=1000)
    z2: float = Field(ge=-1000, le=1000)
    thickness_m: float = Field(gt=0, le=2)
    evidence_id: str
    source_locator: str = Field(min_length=3, max_length=1000)
    status: Literal['CONFIRMED', 'AI_SUGGESTED', 'UNKNOWN']
    insulation: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def nonzero(self):
        if math.hypot(self.x2 - self.x1, self.z2 - self.z1) < .05:
            raise ValueError('Wall must be at least 0.05 m long')
        return self


class Reconstruction(Contract):
    expected_revision: int = Field(ge=0)
    floor_height_m: float = Field(gt=0, le=20)
    floors: int = Field(ge=1, le=30)
    responsible_person: str = Field(min_length=1, max_length=100)
    review_note: str = Field(min_length=5, max_length=2000)
    walls: list[Wall] = Field(min_length=1, max_length=300)

    @model_validator(mode='after')
    def unique(self):
        if len({w.id for w in self.walls}) != len(self.walls):
            raise ValueError('Duplicate wall IDs')
        return self


def geometry(schema):
    walls = []
    for wall in schema['walls']:
        dx, dz = wall['x2'] - wall['x1'], wall['z2'] - wall['z1']
        length = math.hypot(dx, dz)
        for floor in range(schema['floors']):
            walls.append({'component_id': wall['id'] + '-F' + str(floor + 1), 'wall_id': wall['id'], 'floor': floor + 1,
                'center': [(wall['x1'] + wall['x2']) / 2, (floor + .5) * schema['floor_height_m'], (wall['z1'] + wall['z2']) / 2],
                'size': [length, schema['floor_height_m'], wall['thickness_m']], 'rotation_y': -math.atan2(dz, dx),
                'evidence_id': wall['evidence_id'], 'source_locator': wall['source_locator'], 'status': wall['status'],
                'insulation': wall['insulation'], 'affected_claims': [], 'simulation_mapping': 'NOT_LINKED_TO_IDF'})
    return walls


class Spatial:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def get(self, project_id):
        records = self.store.list('geometry', project_id)
        if not records:
            return None
        record = records[0]
        stale = []
        if record.get('geometry_code_hash') != core.sha(Path(__file__)):
            stale.append('geometry_code_version')
        for ev in record['evidence_snapshot']:
            current = self.store.get('evidence', ev['evidence_id'])
            if current['revision'] != ev['revision'] or current['hash'] != ev['hash'] or current['review_state'] != 'confirmed':
                stale.append(ev['evidence_id'])
            if current['source_file']:
                self.domain.file_record(project_id, current['source_file'])
        sources = {e['evidence_id']: e for e in record['evidence_snapshot']}
        components = [{**c, 'source_status': sources[c['evidence_id']]['status']} for c in geometry(record['schema'])]
        return {**record, 'status': 'STALE' if stale else 'ASSUMED' if any(e['status'] == 'ASSUMED' for e in sources.values()) else 'CONFIRMED' if all(w['status'] == 'CONFIRMED' for w in record['schema']['walls']) else 'PARTIAL',
                'stale_evidence': stale, 'components': components}

    def save(self, project_id, body):
        self.store.get('project', project_id)
        evidence = []
        for eid in {w.evidence_id for w in body.walls}:
            ev = self.store.get('evidence', eid)
            if ev['project_id'] != project_id or ev['type'] not in {'drawing', 'manual_input'}:
                raise core.ValidationError('构件必须引用本项目图纸或人工测量证据')
            if any(w.evidence_id == eid and w.status == 'CONFIRMED' for w in body.walls) and (ev['review_state'] != 'confirmed' or ev['status'] in {'AI_INFERRED', 'MISSING'}):
                raise core.ValidationError('确认构件前，必须人工确认其来源证据；AI 推断不能直接成为事实')
            if ev['source_file']:
                self.domain.file_record(project_id, ev['source_file'])
            evidence.append(ev)
        old = self.store.list('geometry', project_id)
        schema = body.model_dump(exclude={'expected_revision'})
        obj = {'geometry_id': old[0]['geometry_id'] if old else 'geometry_' + uuid.uuid4().hex,
            'project_id': project_id, 'schema_version': 'vra.building-geometry.v1', 'units': 'm',
            'schema': schema, 'schema_hash': core.hash_json(schema), 'evidence_snapshot': evidence,
            'geometry_code_hash': core.sha(Path(__file__)),
            'timestamp': core.now(), 'limitations': ['人工确认的简单墙体几何；不是 BIM，不做自动残图识别。', '未链接 IDF 构件；不自动声称这些墙影响特定能耗结论。', '未知/AI 建议不得作为已确认模型输入。']}
        self.store.put('geometry', obj, body.expected_revision)
        return self.get(project_id)
