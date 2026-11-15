"""Append-only schedule variants; the original CPM calculator and its hashes stay unchanged."""
import html
import json
from pathlib import Path

from pydantic import Field, StrictBool, model_validator

from . import core, construction, construction_leveling
from .calculation_provenance import persist, validity, version as provenance_version
from .domain import identifier
from .schema import Contract


class LevelingRequest(Contract):
    name: str = Field(min_length=1, max_length=160)
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    priority: list[str] = Field(min_length=1, max_length=250)
    resource_demands_complete: StrictBool
    demand_basis: str = Field(min_length=20, max_length=2000)

    @model_validator(mode='after')
    def distinct(self):
        if len(self.priority) != len(set(self.priority)) or any(not k or len(k) > 60 for k in self.priority):
            raise ValueError('List distinct source task IDs, up to 60 characters each')
        return self


def version():
    paths = [Path(__file__), Path(construction_leveling.__file__), Path(construction.__file__)]
    return core.hash_json({p.name: provenance_version(p) for p in paths})


class ScheduleRecords(construction.Schedules):
    def _source(self, pid, sid, expected):
        raw = self.store.get('schedule', sid)
        if raw.get('calculation_type'):
            raise core.ValidationError('Select the original CPM plan, not a derived resource schedule')
        source = super().view(pid, sid)
        if source['hash'] != expected or source['status'] == 'stale' or source['result'] is None:
            raise core.ValidationError('Current matching source plan required')
        return source

    def level(self, pid, sid, body):
        source = self._source(pid, sid, body.source_hash)
        inputs = construction.ScheduleInput.model_validate(source['input'])
        if len(body.priority) != len(inputs.tasks) or set(body.priority) != {t.task_id for t in inputs.tasks}:
            raise core.ValidationError('Priority must include every source task exactly once')
        leveled = construction_leveling.calculate(inputs, body.priority, body.resource_demands_complete)
        record = {'schedule_id': identifier('schedule'), 'project_id': pid,
            'project_revision': source['project_revision'], 'input': {**source['input'], 'name': body.name},
            'calculation_type': 'resource_leveling', 'leveling_request': body.model_dump(),
            'leveling_source': {'schedule_id': sid, 'hash': source['hash'], 'revision': source['revision']},
            'source_snapshot': source['source_snapshot'], 'import_source': source.get('import_source'),
            'calculator_hash': version(), 'created_at': core.now(),
            'result': {'status': leveled['status'], 'planned': source['result'].get('planned'), 'forecast': None,
                'resource_leveling': leveled['method'], 'leveled': leveled,
                'site_safety': 'NOT_ASSESSED', 'limitations': leveled['limitations']}}
        record['hash'] = core.hash_json(record)
        persist(self.domain, 'schedule', record,
                pre_insert_check=lambda: self._source(pid, sid, body.source_hash))
        return self.view(pid, record['schedule_id'])

    def view(self, pid, sid):
        record = self.store.get('schedule', sid)
        if record.get('calculation_type') != 'resource_leveling':
            return super().view(pid, sid)
        if record['project_id'] != pid: raise core.ValidationError('Cross-project schedule rejected')
        if core.hash_json({k: v for k, v in record.items() if k not in {'hash', 'revision'}}) != record['hash']:
            raise core.ValidationError('Schedule integrity check failed')
        provenance = validity(self.domain, record, version())
        reference = record['leveling_source']
        try:
            self._source(pid, reference['schedule_id'], reference['hash'])
        except (KeyError, ValueError, OSError):
            provenance['stale_reasons'].append('leveling_source_unavailable')
            provenance['stale_details'].append({'code': 'leveling_source_unavailable',
                'subject_id': reference['schedule_id'], 'expected': reference['hash'], 'current': None})
        stale = bool(provenance['stale_reasons'])
        return {**record, **provenance, 'status': 'stale' if stale else record['result']['status'],
                'result': None if stale else record['result']}


def report(record):
    if record.get('calculation_type') != 'resource_leveling': return construction.report(record)
    esc = lambda value: html.escape(str(value))
    leveled = (record.get('result') or {}).get('leveled') or {}
    schedule = leveled.get('schedule')
    content = '<p>当前资源受限方案不可用；原因：' + esc(', '.join(record.get('stale_reasons') or leveled.get('reasons', []))) + '</p>'
    if schedule:
        content = '<h2>资源受限方案：' + esc(schedule['duration_days']) + ' 连续经过日</h2><p>原CPM下界：' + esc(schedule['cpm_duration_days']) + ' 日；本方案相对CPM延后 ' + esc(schedule['delay_vs_cpm_days']) + ' 日。</p>'
        content += '<p>数学下界（向下显示6位小数）：' + esc(leveled['lower_bound']['days_floor_6dp']) + ' 日；' + ('本方案达到精确下界，仅在声明模型内证明最短。' if leveled['lower_bound']['attained'] else '尚未证明全局最优。') + '</p>'
        content += '<table><tr><th>工序</th><th>开始日</th><th>完成日</th><th>相对CPM开始延后</th></tr>'
        content += ''.join('<tr>' + ''.join('<td>' + esc(v) + '</td>' for v in (r['task_id'] + ' ' + r['name'], r['start_day'], r['finish_day'], r['start_delay_days'])) + '</tr>' for r in schedule['rows']) + '</table>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>资源受限排程记录</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:30px auto;padding:20px}td,th{padding:8px;border:1px solid #ccc}table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>' + esc(record['input']['name']) + '</h1><p>用户声明资料；不是施工安全批准或履约保证。状态：' + esc(record['status']) + '</p>' + content + '<h2>方法、原计划引用与完整来源</h2><pre>' + esc(json.dumps(record, ensure_ascii=False, indent=2)) + '</pre></html>'
