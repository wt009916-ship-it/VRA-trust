"""Material cards bind engineer-entered model parameters to reviewed evidence."""
import uuid
from typing import Literal

from pydantic import Field, model_validator

from . import core
from .schema import Contract


PROPERTIES = ('conductivity_w_mk', 'density_kg_m3', 'specific_heat_j_kgk')
EVIDENCE_FIELDS = ('thermal_evidence_id', 'sample_evidence_id', 'control_evidence_id', 'aging_evidence_id')
GAP_LABELS = {'conductivity_w_mk': '导热系数', 'density_kg_m3': '密度', 'specific_heat_j_kgk': '比热',
              'thermal_evidence_id': '热工参数证据', 'sample_evidence_id': '样品批次证据',
              'control_evidence_id': '对照测试证据', 'aging_evidence_id': '老化证据', 'batch': '样品批次',
              'source_locator': '参数定位', 'test_conditions': '测试条件', 'applicability': '适用范围',
              'material_review': '材料参数复核', 'thermal_evidence_review': '热工来源复核'}


def gap_text(key):
    if key.endswith('_not_measured'):
        return GAP_LABELS[key.removesuffix('_not_measured')] + '尚非已复核实测'
    return GAP_LABELS.get(key, key)


class MaterialCard(Contract):
    name: str = Field(min_length=1, max_length=160)
    batch: str | None = Field(default=None, max_length=200)
    contains_rare_earth: bool = False
    conductivity_w_mk: float | None = Field(default=None, gt=0, le=100, strict=True)
    density_kg_m3: float | None = Field(default=None, gt=0, le=30000, strict=True)
    specific_heat_j_kgk: float | None = Field(default=None, ge=100, le=20000, strict=True)
    thermal_evidence_id: str | None = None
    sample_evidence_id: str | None = None
    control_evidence_id: str | None = None
    aging_evidence_id: str | None = None
    test_conditions: str | None = Field(default=None, max_length=2000)
    applicability: str | None = Field(default=None, max_length=2000)
    source_locator: str | None = Field(default=None, max_length=1000)
    review_state: Literal['pending', 'confirmed'] = 'pending'
    responsible_person: str = Field(min_length=1, max_length=100)
    review_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def confirmation(self):
        if self.review_state == 'confirmed' and (
            any(getattr(self, key) is None for key in PROPERTIES)
            or not all((self.thermal_evidence_id, self.test_conditions, self.applicability, self.source_locator,
                        self.review_note and len(self.review_note) >= 5))
        ):
            raise ValueError('确认材料需热工参数、来源定位、测试条件、适用范围和复核依据')
        return self


class MaterialUpdate(MaterialCard):
    expected_revision: int = Field(ge=1)


def evidence_snapshot(domain, project_id, evidence_id, *, confirmed=True):
    evidence = domain.store.get('evidence', evidence_id)
    if evidence['project_id'] != project_id:
        raise core.ValidationError('Cross-project evidence rejected')
    if confirmed and (evidence['review_state'] != 'confirmed' or evidence['status'] in {'MISSING', 'AI_INFERRED'}):
        raise core.ValidationError('请先复核来源证据；缺失和 AI 推断不能成为已核验输入')
    if evidence['source_file']:
        source, _ = domain.file_record(project_id, evidence['source_file'])
        if source['hash'] != evidence['hash']:
            raise core.ValidationError('Evidence/file hash mismatch')
    return evidence


def evidence_changes(domain, project_id, snapshots):
    reasons = []
    for old in snapshots:
        try:
            current = evidence_snapshot(domain, project_id, old['evidence_id'], confirmed=False)
            if current != old:
                reasons.append('证据版本变化：' + old['name'])
        except (KeyError, OSError, core.ValidationError):
            reasons.append('证据缺失或损坏：' + old['name'])
    return reasons


class Materials:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def save(self, project_id, body, material_id=None):
        self.store.get('project', project_id)
        if material_id and self.store.get('material', material_id)['project_id'] != project_id:
            raise core.ValidationError('Cross-project material rejected')
        snapshots = [evidence_snapshot(self.domain, project_id, eid, confirmed=body.review_state == 'confirmed')
                     for eid in dict.fromkeys(getattr(body, field) for field in EVIDENCE_FIELDS) if eid]
        card = body.model_dump(exclude={'expected_revision'})
        card.update(material_id=material_id or 'material_' + uuid.uuid4().hex, project_id=project_id,
                    timestamp=core.now(), evidence_snapshot=snapshots)
        self.store.put('material', card, body.expected_revision if material_id else 0)
        return self.get(project_id, card['material_id'])

    def get(self, project_id, material_id):
        card = self.store.get('material', material_id)
        if card['project_id'] != project_id:
            raise core.ValidationError('Cross-project material rejected')
        stale = evidence_changes(self.domain, project_id, card['evidence_snapshot'])
        gaps = [key for key in PROPERTIES if card[key] is None]
        gaps += [key for key in ('thermal_evidence_id', 'source_locator', 'test_conditions', 'applicability') if not card[key]]
        if card['review_state'] != 'confirmed':
            gaps.append('material_review')
        sources = {e['evidence_id']: e for e in card['evidence_snapshot']}
        thermal = sources.get(card['thermal_evidence_id'])
        if thermal and (thermal['review_state'] != 'confirmed' or thermal['status'] in {'MISSING', 'AI_INFERRED'}):
            gaps.append('thermal_evidence_review')
        validation_gaps = [key for key in ('batch', 'sample_evidence_id', 'control_evidence_id', 'aging_evidence_id') if not card[key]]
        # A filled identifier alone never establishes experimental material performance.
        validation_gaps += [key + '_not_measured' for key in EVIDENCE_FIELDS
                            if card[key] and (sources[card[key]]['status'] != 'MEASURED' or sources[card[key]]['review_state'] != 'confirmed')]
        return {**card, 'can_simulate': not gaps and not stale, 'simulation_gaps': gaps,
                'validation_gaps': validation_gaps, 'stale_reasons': stale,
                'source_nature': thermal['status'] if thermal else 'MISSING',
                'status': 'STALE' if stale else 'PARAMETER_SCENARIO_READY' if not gaps else 'INCOMPLETE',
                'performance_claim_verified': False,
                'limitations': ['材料卡是工程师登记的参数与来源，不自动证明检测报告内容正确或材料实测优势。',
                                '替换现有不透明构造层的热工参数；光学、老化、施工及稀土机理需独立核验。']}

    def list(self, project_id):
        return [self.get(project_id, card['material_id']) for card in self.store.list('material', project_id)]
