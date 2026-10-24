"""Untouched IFC inventory, importer and production upload acceptance; no repairs."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['VRA_DATA_DIR'] = str(args.output/'private-runtime')
    from backend import core, model_import, model_geometry
    from backend.model_schema import ImportOptions
    from backend.api import create_app
    import ifcopenshell
    from fastapi.testclient import TestClient
    result = {'source': args.source.name, 'sha256': core.sha(args.source),
              'bytes': args.source.stat().st_size, 'ifcopenshell': importlib.metadata.version('ifcopenshell')}
    started = time.perf_counter()
    doc = ifcopenshell.open(str(args.source))
    result['inventory'] = {kind:len(doc.by_type(kind)) for kind in
        ['IfcSpace','IfcWall','IfcWindow','IfcDoor','IfcSlab','IfcRoof','IfcBuildingStorey','IfcRelSpaceBoundary']}
    result['schema'] = doc.schema
    result['native_read_seconds'] = time.perf_counter()-started
    started = time.perf_counter()
    try:
        candidate = model_import.ifc(args.source, ImportOptions(file_id='benchmark'))
        core.write_json(args.output/'candidate.json', candidate)
        result['importer'] = {'status':'ok', 'rooms':len(candidate['rooms']),
            'segments':sum(len(model_geometry.parts(r)) for r in candidate['rooms']), 'warnings':candidate['warnings']}
    except Exception as exc:
        result['importer'] = {'status':'error', 'error':f'{type(exc).__name__}: {exc}'}
    result['importer']['seconds'] = time.perf_counter()-started
    core.write_json(args.output/'results.json', result)
    with TestClient(create_app(args.output/'private-runtime', start_worker=False)) as client:
        auth = client.post('/api/auth/register', json={'username':'isolated_ifc_benchmark',
            'display_name':'Software benchmark', 'password':secrets.token_urlsafe(32)})
        auth.raise_for_status()
        client.headers['X-CSRF-Token'] = auth.json()['csrf_token']
        response = client.post('/api/projects', json={'name':'External input benchmark',
            'building':{'use':'office','location':'Benchmark declaration only','region':'NL','area_m2':1.0}})
        response.raise_for_status()
        base = '/api/projects/'+response.json()['project_id']
        started = time.perf_counter()
        upload = client.post(base+'/files', files={'file':(args.source.name,args.source.read_bytes())})
        result['api_upload'] = {'status':upload.status_code,'body':upload.json(), 'seconds':time.perf_counter()-started,
                                'upload_limit_mb':os.environ.get('VRA_MAX_UPLOAD_MB','20')}
        if upload.status_code == 201:
            imported = client.post(base+'/imports', json={'file_id':upload.json()['file_id']})
            result['api_import'] = {'status':imported.status_code,'body':imported.json()}
    result['source_unchanged'] = result['sha256'] == core.sha(args.source)
    core.write_json(args.output/'results.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['api_import']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
