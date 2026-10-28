"""Version-bound engineering review, semantic model changes and issue-only BCF handoff.

Readiness here is an input checklist, never a replacement for the physical gate,
calibration, compliance or a professional signature. A disposition cannot fix data.
"""
from collections import Counter
import hashlib
import html
import io
import json
import threading
import uuid
import zipfile
from xml.etree import ElementTree as ET

from pydantic import Field, field_validator
from typing import Literal

from . import core
from .schema import Contract


LIMITS = [
    '本页是资料与假设复核，不替代模型几何校验、计算准入、现场校准或工程签署。',
    '记录处置不会补齐数据、解除阻断或把假设升级为实测。来源或模型版本改变后须重新复核。',
    '变更分类仅解释影响；当前计算仍按整版模型/输入绑定核验，没有按房间选择性重算。',
    'BCF 2.1仅交换问题文字与来源标识，不含相机、截图、模型原件或双向问题同步。',
]
LABELS = {'BLOCKER': '待补齐输入', 'ASSUMPTION': '显式假设', 'EVIDENCE_GAP': '外推依据待补'}


class Disposition(Contract):
    snapshot_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    finding_id: str = Field(pattern=r'^finding_[0-9a-f]{24}$')
    expected_revision: int = Field(default=0, ge=0, strict=True)
    decision: Literal['needs_information', 'accepted_scenario', 'rejected']
    note: str = Field(min_length=10, max_length=2000)

    @field_validator('note')
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 10:
            raise ValueError('复核依据须至少10个非首尾空白字符')
        return value.strip()


def model_changes(before, after):
    """Stable IDs only: never pair different rooms by a similar display name."""
    if not before or not after:
        return {'from_revision': before and before['revision'], 'to_revision': after and after['revision'],
                'changes': [], 'basis': '尚无两个模型版本可比较'}
    changes = []
    def add(scope, field, old, new, room_id=None):
        if old == new:
            return
        def short(value):
            if isinstance(value, list) and len(value) <= 12 and all(isinstance(v, (int, float, str, bool)) for v in value):
                return value
            return value if value is None or isinstance(value, (bool, int, float)) else value[:200] if isinstance(value, str) else {'sha256': core.hash_json(value), 'items': len(value)}
        changes.append({'category': scope, 'field': field, 'room_id': room_id,
                        'before': short(old), 'after': short(new)})
    old = {r['id']: r for r in before['rooms']}
    new = {r['id']: r for r in after['rooms']}
    geometry = {'polygon', 'holes', 'segments', 'shell', 'height_m', 'elevation_m'}
    usage = {'conditioned', 'include_floor_area'}
    for rid in sorted(old.keys() | new.keys()):
        if rid not in old or rid not in new:
            add('space_added' if rid not in old else 'space_removed', 'room', old.get(rid), new.get(rid), rid)
            continue
        for key in sorted(old[rid].keys() | new[rid].keys()):
            category = 'geometry' if key in geometry else 'use' if key in usage else 'display' if key == 'name' else 'source_and_boundary'
            add(category, key, old[rid].get(key), new[rid].get(key), rid)
    def parameters(category, field, a, b, room_id=None):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(a.keys() | b.keys()):
                parameters(category, field+'.'+key, a.get(key), b.get(key), room_id)
        elif field.startswith('thermal.constructions.') and isinstance(a, list) and isinstance(b, list):
            for i in range(max(len(a), len(b))):
                parameters(category, field+f'[{i}]', a[i] if i < len(a) else {}, b[i] if i < len(b) else {}, room_id)
        else:
            add(category, field, a, b, room_id)
    parameters('thermal', 'thermal', before.get('thermal') or {}, after.get('thermal') or {})
    for key, identity in [('equipment', 'zone_id'), ('sources', 'file_id')]:
        a = {r[identity]: r for r in before.get(key, [])}
        b = {r[identity]: r for r in after.get(key, [])}
        for record_id in sorted(a.keys() | b.keys()):
            parameters(key, key+'['+record_id+']', a.get(record_id, {}), b.get(record_id, {}), record_id if key == 'equipment' else None)
    for key in ('scope_exclusions', 'reviewed', 'review_note', 'name'):
        parameters(key, key, before.get(key), after.get(key))
    return {'from_revision': before['revision'], 'to_revision': after['revision'], 'changes': changes,
            'affected_room_ids': sorted({c['room_id'] for c in changes if c['room_id']}),
            'categories': dict(Counter(c['category'] for c in changes)),
            'basis': '按稳定空间ID逐字段比较；全局热工/设备变更不推断成局部影响。整版计算绑定仍须核验。'}


class EngineeringReview:
    def __init__(self, domain, modeling):
        self.domain, self.modeling, self.store = domain, modeling, domain.store
        self.lock = threading.RLock()

    def snapshot(self, project_id):
        with self.modeling.lock:
            return self._snapshot(project_id)

    def _snapshot(self, project_id):
        project = self.store.get('project', project_id)
        model = self.modeling.get(project_id)
        evidence = [e for e in self.store.list('evidence', project_id) if e['review_state'] != 'rejected']
        materials = self.store.list('material', project_id)
        findings, sources = [], []
        def finding(key, kind, title, action, *, rooms=None, locator=None, basis=None):
            rooms = rooms or []
            ids = sorted(r['id'] for r in rooms)
            findings.append({'finding_id': 'finding_'+core.hash_json([project_id, key])[:24], 'key': key,
                'kind': kind, 'title': title, 'action': action, 'room_ids': ids,
                'ifc_global_ids': sorted({r['ifc_source'] for r in rooms if r.get('ifc_source')}),
                'source_element_ids': sorted({gid for r in rooms for gid in (r.get('reconstruction') or {}).get('source_elements', [])}),
                'storey_ids': sorted({r['storey_id'] for r in rooms if r.get('storey_id')}),
                'locator': locator, 'basis': basis})
        refs = {s['file_id']: s for s in (model or {}).get('sources', [])}
        for ev in evidence:
            if ev.get('source_file'):
                refs.setdefault(ev['source_file'], {'file_id': ev['source_file'], 'hash': ev.get('hash'), 'name': ev['name']})
        for fid, ref in sorted(refs.items()):
            try:
                current, _ = self.domain.file_record(project_id, fid)
                valid = current['hash'] == ref.get('hash')
                row = {'file_id': fid, 'name': current['name'], 'expected_sha256': ref.get('hash'),
                       'current_sha256': current['hash'], 'valid': valid}
            except (KeyError, OSError, core.ValidationError):
                row = {'file_id': fid, 'name': ref.get('name'), 'expected_sha256': ref.get('hash'),
                       'current_sha256': None, 'valid': False}
            sources.append(row)
            if not row['valid']:
                finding('source:'+fid, 'BLOCKER', '来源文件缺失、损坏或与绑定哈希不符',
                        '核对原件并重新导入；历史版本保留，不改写旧哈希。', locator=fid)
        for ev in evidence:
            source = next((s for s in sources if s['file_id'] == ev.get('source_file')), None)
            if source and (not source['valid'] or source['current_sha256'] != ev.get('hash')):
                finding('evidence-source:'+ev['evidence_id'], 'BLOCKER', ev['name']+'：证据原件绑定无效',
                        '核对登记原件与证据版本，不改写历史哈希。', locator=ev['evidence_id'])
            if ev['review_state'] != 'rejected' and ev['status'] == 'ASSUMED':
                finding('evidence-assumed:'+ev['evidence_id'], 'ASSUMPTION', ev['name']+'：来源性质为假设',
                        '核对项目、地点、工况与适用范围；人工确认不会改变来源性质。', locator=ev['evidence_id'], basis=ev['source_locator'])
        gate = self.domain.gate(project_id)
        for item in gate['blockers']:
            finding('gate:'+item['code']+':'+item['field'], 'BLOCKER', item['message'], item['action'], locator=item['field'])
        if not model:
            finding('model:missing', 'EVIDENCE_GAP', '没有工作区空间模型', '导入授权图纸/BIM；外部IDF可按其独立范围校验，不据此判断整个工程不可计算。')
        else:
            if not model['reviewed']:
                finding('model:review', 'BLOCKER', '空间几何尚未复核', '在建模工作区核对并保存复核版本。')
            thermal = model.get('thermal') or {}
            if not thermal:
                finding('model:thermal', 'BLOCKER', '空间模型热工参数未补齐', '补构造、窗、负荷、时段和来源；不能用默认值代替缺失资料。')
            grouped = {}
            for room in model['rooms']:
                grouped.setdefault(room.get('storey_id') or 'unassigned', []).append(room)
            for floor, rooms in grouped.items():
                label = ' / '.join(x for x in (rooms[0].get('building_name'), rooms[0].get('storey_name')) if x) or floor
                unresolved = [r for r in rooms if r.get('conditioned') is None or r.get('include_floor_area') is None]
                if unresolved:
                    finding('use:'+floor, 'BLOCKER', f'{label}：{len(unresolved)}个空间用途/计面积待确认',
                            '按实际用途逐间或按显示楼层批量复核，填写依据；不依据房名猜测。', rooms=unresolved)
                inferred = [r for r in rooms if r.get('reconstruction') or r.get('drawing') or r.get('geometry_inferred')]
                if inferred:
                    finding('inferred:'+floor, 'ASSUMPTION', f'{label}：{len(inferred)}个推导空间',
                            '回到原图/源构件核对闭合、层高、孔洞和外包络；接受本情景不会将其变成原生或实测。', rooms=inferred)
                opening_issues = [r for r in rooms if r.get('source_opening_issues')]
                if opening_issues:
                    finding('windows:'+floor, 'BLOCKER' if thermal.get('window_geometry') == 'source' else 'EVIDENCE_GAP',
                            f'{label}：源窗映射有未完成项', '核对房间源窗诊断、原窗洞与边界；不把未映射窗当作已覆盖。', rooms=opening_issues,
                            basis=[{'room_id': r['id'], 'issues': r['source_opening_issues']} for r in opening_issues])
            policies = [('basis', 'assumed_scenario', '热工与负荷为明确假设情景'),
                        ('ifc_unpaired_policy', 'adiabatic_scenario', '未配对内部/未知边界采用绝热假设'),
                        ('source_window_exterior_policy', 'outdoor_scenario', '源窗所在墙面采用室外假设'),
                        ('reconstructed_exterior_policy', 'outline_scenario', '楼板外缘采用建筑外包络假设'),
                        ('column_mass_policy', 'lumped_scenario', '内部柱体采用等效热容近似')]
            for key, value, title in policies:
                if thermal.get(key) == value:
                    finding('thermal:'+key, 'ASSUMPTION', title, '核对参数来源、工况和适用范围；只在声明条件下解释结果。', locator='thermal.'+key, basis=thermal.get('source_note'))
            if thermal:
                if thermal.get('window_geometry', 'ratio') == 'ratio':
                    finding('windows:ratio', 'ASSUMPTION', '开窗使用统一窗墙比情景', '核对实际窗数量、面积、朝向及光学；此处不代表已恢复源窗。')
                finding('windows:optics', 'EVIDENCE_GAP', '窗U/SHGC与框、遮阳的实际适用性待外部核对',
                        '当前采用项目统一U/SHGC；源窗投影不等于净玻璃，不含完整框与遮阳自动转译。')
                if not thermal.get('operation'):
                    finding('operation:daily', 'ASSUMPTION', '负荷沿用每日起止时段', '用有来源的运行档案复核工作日/周末、空置温度及新风；未恢复现场实际运行。')
            for source in model.get('sources', []):
                coverage_by_floor = {}
                for row in (source.get('reconstruction_coverage') or {}).get('storeys', []):
                    if row['status'] != 'candidate' or row.get('excluded_subminimum_area_m2', 0) > .01:
                        coverage_by_floor.setdefault(row['storey'], []).append(row)
                for floor, rows in coverage_by_floor.items():
                    excluded = model.get('scope_exclusions', {}).get(floor)
                    name = next((r['name'] for r in rows if r.get('name')), floor)
                    finding('coverage:'+source['file_id']+':'+floor, 'ASSUMPTION' if excluded else 'BLOCKER',
                            name+'：有未恢复或明确排除区域',
                            '依据原图补全或保留排除范围；填写处置说明不代表完整覆盖。',
                            locator=floor, basis={'coverage_rows': rows, 'scope_exclusion': excluded})
            for item in model.get('equipment', []):
                if item['curve_basis'] == 'native_reference':
                    finding('equipment:'+item['zone_id'], 'ASSUMPTION', item['zone_id']+'：设备使用原生参考性能曲线',
                            '补厂家变工况曲线与使用范围；铭牌及参考曲线不能证明已安装实际性能。',
                            rooms=[r for r in model['rooms'] if r['id'] == item['zone_id']], locator=item['source_locator'])
        valid_bill = any(e['type'] == 'bill' and e['review_state'] == 'confirmed' and e['status'] not in {'MISSING', 'AI_INFERRED', 'ASSUMED'} and
                         (not e.get('source_file') or next((s['valid'] for s in sources if s['file_id'] == e['source_file']), False)) for e in evidence)
        finding('calibration', 'EVIDENCE_GAP', '尚未证明模型完成实际账单校准',
                '取得分能源计量、工况与匹配天气，另行执行校准及留出验证；登记账单本身不证明模型拟合有效。',
                basis={'reviewed_bill_registered': valid_bill, 'calibration_verified': False})
        if materials:
            from .materials import Materials
            service = Materials(self.domain)
            for material in materials:
                checked = service.get(project_id, material['material_id'])
                if checked['validation_gaps'] or checked['stale_reasons']:
                    finding('material:'+material['material_id'], 'EVIDENCE_GAP', material['name']+'：材料实测验证链待补齐',
                            '核对批次、热工检测、同工况对照与老化；能模拟参数不代表已证明稀土或现场节能优势。',
                            locator=material['material_id'], basis={'validation_gaps': checked['validation_gaps'],
                                'stale_reasons': checked['stale_reasons'], 'contains_rare_earth': material['contains_rare_earth']})
        binding = {'rules_hash': core.sha(__file__), 'project_revision': project['revision'], 'model_hash': core.hash_json(model),
                   'evidence_hash': core.hash_json(evidence), 'materials_hash': core.hash_json(materials), 'sources': sources, 'findings': findings}
        digest = core.hash_json(binding)
        reviews = self.store.list('review', project_id)
        for finding_row in findings:
            matching = [r for r in reviews if r['finding_id'] == finding_row['finding_id']]
            record = next((r for r in matching if r['snapshot_hash'] == digest), None)
            finding_row['review'] = record
            finding_row['review_revision'] = matching[0]['revision'] if matching else 0
            finding_row['prior_review_stale'] = bool(matching and not record)
        history = self.modeling.history(project_id)
        return {'schema_version': 'vra.engineering-review.v1', 'generated_at': core.now(), 'snapshot_hash': digest,
                'project': {'project_id': project_id, 'name': project['name'], 'revision': project['revision']},
                'model': {'model_id': model['model_id'], 'revision': model['revision'], 'rooms': len(model['rooms'])} if model else None,
                'sources': sources, 'findings': findings, 'counts': dict(Counter(f['kind'] for f in findings)),
                'current_dispositions': sum(f['review'] is not None for f in findings),
                'changes': model_changes(history[-2] if len(history) > 1 else None, model),
                'comparison_inputs': {'basis': '仅列当前已保存输入协议，不代表商业软件已按此协议实跑或完成模型校准。',
                    'model_sha256': core.hash_json(model), 'room_ids': [r['id'] for r in (model or {}).get('rooms', [])],
                    'model_area_m2': (model or {}).get('area_m2'), 'declared_area_m2': project['building']['area_m2'],
                    'thermal_and_operation': (model or {}).get('thermal'),
                    'equipment': (model or {}).get('equipment', []),
                    'registered_simulation_inputs': {role: {k: ev.get(k) for k in ('evidence_id', 'revision', 'source_file', 'hash', 'status', 'review_state', 'source_locator')}
                                                     for role, ev in gate.get('selected_evidence', {}).items()},
                    'source_files': sources, 'scope_exclusions': (model or {}).get('scope_exclusions', {}),
                    'required_matching': ['空间/面积与排除范围', '天气站点、年份和逐时文件哈希', '人员/设备/新风/时段',
                                          '构造/窗/遮阳与边界假设', 'HVAC设备耗电或理想冷热需求口径', '引擎版本、指标与计量边界'],
                    'warning': '同源引擎封装相同不证明现场精度；来源标识不同或缺失须人工核对，不能默认可比。'},
                'calculation_gate': {'can_simulate': gate['can_simulate'], 'basis': '已登记IDF/EPW准入；不表示当前工作区模型几何校验通过。'},
                'engineering_signature': 'UNSIGNED', 'limitations': LIMITS}

    def record(self, project_id, body, actor):
        with self.lock, self.modeling.lock:
            snap = self.snapshot(project_id)
            if body.snapshot_hash != snap['snapshot_hash']:
                raise core.ValidationError('资料或模型已变化，请刷新复核台账；旧复核记录保留')
            finding = next((f for f in snap['findings'] if f['finding_id'] == body.finding_id), None)
            if not finding:
                raise core.ValidationError('当前快照不存在此复核项')
            if body.decision == 'accepted_scenario' and finding['kind'] != 'ASSUMPTION':
                raise core.ValidationError('输入阻断或外推缺证不能通过接受假设解除')
            key = 'review_'+uuid.uuid5(uuid.NAMESPACE_URL, project_id+':'+body.finding_id).hex
            return self.store.put('review', {**body.model_dump(exclude={'expected_revision'}),
                'review_id': key, 'project_id': project_id, 'actor': actor, 'recorded_at': core.now(),
                'finding_snapshot': {k: v for k, v in finding.items() if k not in {'review', 'prior_review_stale'}}}, body.expected_revision)

    def history(self, project_id, finding_id):
        key = 'review_'+uuid.uuid5(uuid.NAMESPACE_URL, project_id+':'+finding_id).hex
        return self.store.history('review', key)


def review_html(snapshot):
    esc = lambda value: html.escape(str(value if value is not None else '—'))
    rows = ''.join('<tr><td>'+esc(LABELS[f['kind']])+'</td><td>'+esc(f['title'])+'</td><td>'+esc(', '.join(f['room_ids']))+'<details><summary>源定位与依据</summary><pre>'+esc(json.dumps({k: f[k] for k in ('ifc_global_ids', 'source_element_ids', 'storey_ids', 'locator', 'basis')}, ensure_ascii=False, indent=2))+'</pre></details></td><td>'+esc(f['action'])+'</td><td>'+esc((f['review'] or {}).get('note'))+'</td></tr>' for f in snapshot['findings'])
    source_summary = '<h2>原件核对</h2><ul>'+''.join('<li>'+esc(s['name'])+' · '+esc('哈希匹配' if s['valid'] else '来源无效')+'<code>'+esc(s['expected_sha256'])+'</code></li>' for s in snapshot['sources'])+'</ul><details><summary>模型版本变化</summary><pre>'+esc(json.dumps(snapshot['changes'], ensure_ascii=False, indent=2))+'</pre></details>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>工程复核交接</title><style>body{font:15px sans-serif;max-width:1200px;margin:40px auto;color:#17233d}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4e0;padding:10px;text-align:left;vertical-align:top}code,pre{overflow-wrap:anywhere;white-space:pre-wrap}</style><h1>'+esc(snapshot['project']['name'])+' · 工程复核交接</h1><p>未签署 · 快照 '+esc(snapshot['generated_at'])+'</p><code>'+esc(snapshot['snapshot_hash'])+'</code><ul>'+''.join('<li>'+esc(x)+'</li>' for x in snapshot['limitations'])+'</ul>'+source_summary+'<h2>当前问题与处置</h2><table><thead><tr><th>性质</th><th>复核项</th><th>空间与来源</th><th>补证/复核动作</th><th>当前处置依据</th></tr></thead><tbody>'+rows+'</tbody></table></html>'


def issue_bcf(snapshot):
    """BCF-XML 2.1 topics without fabricated model coordinates or embedded sources."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        version = ET.Element('Version', VersionId='2.1')
        archive.writestr('bcf.version', ET.tostring(version, encoding='utf-8', xml_declaration=True))
        for index, finding in enumerate(snapshot['findings'], 1):
            guid = str(uuid.uuid5(uuid.NAMESPACE_URL, snapshot['project']['project_id']+finding['finding_id']))
            root = ET.Element('Markup')
            topic = ET.SubElement(root, 'Topic', Guid=guid, TopicType=finding['kind'], TopicStatus='Open')
            description = '\n'.join([finding['action'], 'Snapshot: '+snapshot['snapshot_hash'],
                'Source IFC GlobalIds: '+', '.join(finding['ifc_global_ids']),
                'Source element GlobalIds: '+', '.join(finding['source_element_ids']),
                'Storeys: '+', '.join(finding['storey_ids']), 'Room IDs: '+', '.join(finding['room_ids']),
                'Locator: '+str(finding['locator']), 'Basis: '+json.dumps(finding['basis'], ensure_ascii=False),
                'Disposition (does not resolve issue): '+json.dumps(finding['review'], ensure_ascii=False), *LIMITS])
            for name, value in [('Title', finding['title']), ('Priority', 'High' if finding['kind'] == 'BLOCKER' else 'Normal'),
                                ('Index', str(index)), ('CreationDate', snapshot['generated_at']),
                                ('CreationAuthor', 'VRA-Trust'), ('Description', description)]:
                ET.SubElement(topic, name).text = ''.join(c if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF else '\ufffd' for c in value)
            archive.writestr(guid+'/markup.bcf', ET.tostring(root, encoding='utf-8', xml_declaration=True))
    return stream.getvalue()


def handoff(snapshot):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        files = {'review.json': json.dumps(snapshot, ensure_ascii=False, indent=2).encode(),
                 'review.html': review_html(snapshot).encode(), 'issues.bcfzip': issue_bcf(snapshot),
                 'comparison-inputs.json': json.dumps(snapshot['comparison_inputs'], ensure_ascii=False, indent=2).encode()}
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr('manifest.json', json.dumps({'schema_version': 'vra.review-handoff.v1',
            'snapshot_hash': snapshot['snapshot_hash'], 'unsigned': True, 'includes_source_originals': False,
            'files': {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
            'limitations': LIMITS}, ensure_ascii=False, indent=2))
    return stream.getvalue()
