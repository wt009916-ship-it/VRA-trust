"""Project-authorized read-only file inspection with immutable source binding."""
import threading
import uuid
from importlib.metadata import version
from pathlib import Path
from typing import Annotated
from pydantic import Field, model_validator
from . import core
from .schema import Contract
from . import parser_runtime


class Inspection(Contract):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')


class CurrentStates(Contract):
    cad_ids: list[Annotated[str, Field(pattern=r'^cad_[a-f0-9]{32}$')]] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_ids(self):
        if len(set(self.cad_ids)) != len(self.cad_ids):
            raise ValueError('Duplicate CAD records in current-state request')
        return self


def parser_version():
    return core.hash_json({'code': core.sha(Path(__file__).with_name('cad_worker.py')),
        'isolated_runtime':parser_runtime.identity('cad'),
        'resource_policy':core.sha(Path(__file__).with_name('worker_limits.py')),
        'dxf_geometry':core.sha(Path(__file__).with_name('dxf_geometry.py')),
        'ifc_details':core.sha(Path(__file__).with_name('ifc_details.py')),
        'ifc_geometry':core.sha(Path(__file__).with_name('ifc_geometry.py')),
        'ifc_union':core.sha(Path(__file__).with_name('ifc_union.py')),
        'mesh_topology':core.sha(Path(__file__).with_name('mesh_topology.py')),
        'ezdxf': version('ezdxf'), 'ifcopenshell': version('ifcopenshell')})


class Cad:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store
        self.capacity = threading.BoundedSemaphore(2)

    def inspect(self, pid, body):
        source, path = self.domain.file_record(pid, body.file_id)
        if path.suffix.lower() not in {'.dxf', '.ifc'} or source['size'] > 10*1024*1024:
            raise core.ValidationError('Only DXF/IFC up to 10 MiB can be inspected')
        if not self.capacity.acquire(False):
            raise core.ValidationError('File parsers busy; retry later')
        try:
            before=parser_version()
            with parser_runtime.run('cad',path) as scope:
                output = scope['work']/'result.json'
                if not output.exists() or output.stat().st_size > 8*1024*1024:
                    raise core.ValidationError('File parsing failed or output exceeded limit')
                result = core.read_json(output)
                if 'error' in result:
                    raise core.ValidationError('File rejected: '+result.get('error', 'parser failure')+'; original preserved')
                result['resource_limits']=scope['resource_limits']
            self.domain.file_record(pid, body.file_id)
            if parser_version()!=before:
                raise core.ValidationError('File parser changed during processing; retry')
            obj = {'cad_id': 'cad_'+uuid.uuid4().hex, 'project_id': pid, 'source': source,
                'created_at': core.now(), 'parser_hash': before, 'result': result}
            obj['hash'] = core.hash_json(obj)
            self.store.put('cad', obj)
            return self.view(pid, obj['cad_id'])
        finally:
            self.capacity.release()

    def _record(self, pid, cid):
        obj = self.store.get('cad', cid)
        if obj['project_id'] != pid:
            raise core.ValidationError('Cross-project CAD record rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}}) != obj['hash']:
            raise core.ValidationError('Inspection record integrity failed')
        return obj

    def _state(self, pid, obj, current_parser, source_cache):
        reasons = []
        if current_parser is None:
            reasons.append('parser_unavailable')
        elif obj['parser_hash'] != current_parser:
            reasons.append('parser_changed')
        fid = obj['source']['file_id']
        if fid not in source_cache:
            try:
                current, _ = self.domain.file_record(pid, fid)
                source_cache[fid] = current['hash']
            except (OSError, ValueError, KeyError):
                source_cache[fid] = None
        if source_cache[fid] is None:
            reasons.append('source_unavailable')
        elif source_cache[fid] != obj['source']['hash']:
            reasons.append('source_binding_changed')
        status = 'unverified' if current_parser is None else ('stale' if reasons else 'parsed')
        return {'cad_id': obj['cad_id'], 'status': status, 'reasons': reasons,
                'inspection_hash': obj['hash'], 'source_hash': obj['source']['hash'],
                'parser_hash': obj['parser_hash'], 'current_parser_hash': current_parser}

    @staticmethod
    def _current_parser():
        try:
            return parser_version()
        except (OSError, ValueError, ImportError):
            return None

    def current_states(self, pid, body):
        # Validate every requested record's ownership/integrity before checking
        # source data; no partial cross-project replies and no record mutations.
        objects = [self._record(pid, cid) for cid in body.cad_ids]
        current_parser, source_cache = self._current_parser(), {}
        states = [self._state(pid, obj, current_parser, source_cache) for obj in objects]
        return {'checked_at': core.now(), 'states': states, 'poll_after_ms': 5000}

    def view(self, pid, cid):
        obj = self._record(pid, cid)
        state = self._state(pid, obj, self._current_parser(), {})
        return {**obj, 'status': state['status'], 'stale_reasons': state['reasons'],
                'result': obj['result'] if state['status'] == 'parsed' else None,
                'assessment': 'READ_ONLY_EXTRACTION_NOT_ENGINEERING_APPROVAL'}
