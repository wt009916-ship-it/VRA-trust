"""Immutable selected IFC union records, bound to a current CAD inspection."""
import html
import json
import uuid
from pydantic import Field, StrictInt, model_validator
from . import core, parser_runtime
from .schema import Contract
from .cad import parser_version


class UnionRequest(Contract):
    cad_id: str = Field(pattern=r'^cad_[a-f0-9]{32}$')
    product_ids: list[StrictInt] = Field(min_length=2, max_length=64)

    @model_validator(mode='after')
    def check_ids(self):
        from .ifc_union import validate_selection
        self.product_ids = validate_selection(self.product_ids)
        return self


class IfcUnions:
    def __init__(self, cad):
        self.cad, self.domain, self.store = cad, cad.domain, cad.store

    def create(self, pid, body):
        source = self.cad.view(pid, body.cad_id)
        if source['status'] != 'parsed' or source['result']['format'] != 'IFC':
            raise core.ValidationError('A current IFC inspection is required')
        eligible = {r['id'] for r in source['result']['objects']}
        if not set(body.product_ids) <= eligible:
            raise core.ValidationError('Selected entity is not in this IFC inspection')
        if not self.cad.capacity.acquire(False):
            raise core.ValidationError('File parsers busy; retry later')
        try:
            _, path = self.domain.file_record(pid, source['source']['file_id'])
            before = parser_version()
            with parser_runtime.run('cad', path, options={'operation': 'ifc_union', 'product_ids': body.product_ids}) as scope:
                output = scope['work']/'result.json'
                if not output.exists() or output.stat().st_size > 8*1024**2:
                    raise core.ValidationError('IFC union output unavailable')
                result = core.read_json(output)
                if 'error' in result:
                    raise core.ValidationError('IFC union rejected; original preserved')
                result['resource_limits'] = scope['resource_limits']
            current = self.cad.view(pid, body.cad_id)
            if current['status'] != 'parsed' or current['hash'] != source['hash'] or parser_version() != before:
                raise core.ValidationError('IFC source changed during union calculation; retry from current inspection')
            obj = {'union_id': 'union_'+uuid.uuid4().hex, 'project_id': pid,
                'created_at': core.now(), 'cad_id': body.cad_id, 'inspection_hash': source['hash'],
                'parser_hash': before, 'source': source['source'], 'product_ids': body.product_ids, 'result': result}
            obj['hash'] = core.hash_json(obj)
            self.store.put('union', obj)
            return self.view(pid, obj['union_id'])
        finally:
            self.cad.capacity.release()

    def view(self, pid, uid):
        obj = self.store.get('union', uid)
        if obj['project_id'] != pid:
            raise core.ValidationError('Cross-project IFC union rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash', 'revision'}}) != obj['hash']:
            raise core.ValidationError('IFC union integrity failed')
        stale = obj['parser_hash'] != parser_version()
        try:
            current = self.cad.view(pid, obj['cad_id'])
            stale |= current['status'] != 'parsed' or current['hash'] != obj['inspection_hash']
        except (OSError, ValueError, KeyError):
            stale = True
        return {**obj, 'status': 'stale' if stale else obj['result']['status'],
                'result': None if stale else obj['result'],
                'assessment': 'SELECTED_GEOMETRY_NOT_CERTIFIED_MATERIAL_QUANTITY'}


def union_report(record):
    escaped = html.escape(json.dumps(record, ensure_ascii=False, indent=2))
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>IFC选定构件几何并集</title>' + (
        '<body><h1>IFC选定构件几何并集</h1><p>这是明确选定构件的近似几何并集，不是材料净用量或专业计价认证。'
        '开洞沿用原模型，未套用施工计量扣减规则。</p><p>当前状态：' + html.escape(record['status']) +
        '；失效或未核验的数量保持未知。</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">' +
        escaped + '</pre></body></html>')
