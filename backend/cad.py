"""Project-authorized read-only file inspection with immutable source binding."""
import subprocess
import os
import sys
import tempfile
import threading
import uuid
from importlib.metadata import version
from pathlib import Path
from pydantic import Field
from . import core
from .schema import Contract


class Inspection(Contract):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')


def parser_version():
    return core.hash_json({'code': core.sha(Path(__file__).with_name('cad_worker.py')),
        'dxf_geometry':core.sha(Path(__file__).with_name('dxf_geometry.py')),
        'ifc_details':core.sha(Path(__file__).with_name('ifc_details.py')),
        'ifc_geometry':core.sha(Path(__file__).with_name('ifc_geometry.py')),
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
            with tempfile.TemporaryDirectory(prefix='vra-cad-') as tmp:
                output = Path(tmp)/'result.json'
                try:
                    cp = subprocess.run([sys.executable, str(Path(__file__).with_name('cad_worker.py')), str(path), str(output)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        cwd=tmp, env={**{k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL'}}, 'USERPROFILE':tmp, 'XDG_CONFIG_HOME':tmp},
                        timeout=30, check=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except subprocess.TimeoutExpired:
                    raise core.ValidationError('File parsing timed out; original preserved') from None
                if not output.exists() or output.stat().st_size > 8*1024*1024:
                    raise core.ValidationError('File parsing failed or output exceeded limit')
                result = core.read_json(output)
                if cp.returncode:
                    raise core.ValidationError('File rejected: '+result.get('error', 'parser failure')+'; original preserved')
            self.domain.file_record(pid, body.file_id)
            obj = {'cad_id': 'cad_'+uuid.uuid4().hex, 'project_id': pid, 'source': source,
                'created_at': core.now(), 'parser_hash': parser_version(), 'result': result}
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
