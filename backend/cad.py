"""Project-authorized read-only file inspection with immutable source binding."""
import threading
import uuid
from importlib.metadata import version
from pathlib import Path
from pydantic import Field
from . import core
from .schema import Contract
from . import parser_runtime


class Inspection(Contract):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')


def parser_version():
    return core.hash_json({'code': core.sha(Path(__file__).with_name('cad_worker.py')),
        'isolated_runtime':parser_runtime.identity('cad'),
        'resource_policy':core.sha(Path(__file__).with_name('worker_limits.py')),
        'dxf_geometry':core.sha(Path(__file__).with_name('dxf_geometry.py')),
        'ifc_details':core.sha(Path(__file__).with_name('ifc_details.py')),
        'ifc_geometry':core.sha(Path(__file__).with_name('ifc_geometry.py')),
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

    def view(self, pid, cid):
        obj = self.store.get('cad', cid)
        if obj['project_id'] != pid:
            raise core.ValidationError('Cross-project CAD record rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}}) != obj['hash']:
            raise core.ValidationError('Inspection record integrity failed')
        stale = obj['parser_hash'] != parser_version()
        try:
            self.domain.file_record(pid, obj['source']['file_id'])
        except (OSError, ValueError, KeyError):
            stale = True
        return {**obj, 'status': 'stale' if stale else 'parsed', 'result': None if stale else obj['result'],
            'assessment': 'READ_ONLY_EXTRACTION_NOT_ENGINEERING_APPROVAL'}
