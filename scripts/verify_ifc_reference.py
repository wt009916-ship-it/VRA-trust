"""Pinned Duplex: raw STEP declarations and Decimal prism oracle vs actual API.

This intentionally does not validate arbitrary STEP syntax or all model geometry.
"""
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.api import create_app

SHA = 'b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed'
TYPES = {'IFCBEAM','IFCCOVERING','IFCDOOR','IFCFOOTING','IFCMEMBER','IFCRAILING','IFCROOF',
         'IFCSLAB','IFCSTAIR','IFCSTAIRFLIGHT','IFCWALL','IFCWALLSTANDARDCASE','IFCWINDOW',
         'IFCOPENINGELEMENT','IFCFURNISHINGELEMENT','IFCBUILDING','IFCBUILDINGSTOREY','IFCSITE','IFCSPACE'}


def fields(text):
    parts = []; start = depth = 0; quoted = False; i = 0
    while i < len(text):
        char = text[i]
        if char == "'":
            if quoted and i+1 < len(text) and text[i+1] == "'":
                i += 2; continue
            quoted = not quoted
        elif not quoted:
            if char == '(': depth += 1
            elif char == ')': depth -= 1
            elif char == ',' and depth == 0:
                parts.append(text[start:i].strip()); start = i+1
        i += 1
    assert depth == 0 and not quoted
    return parts + [text[start:].strip()]


def raw_oracle(text):
    entities = {int(i): (kind, fields(args)) for i, kind, args in re.findall(r'^#(\d+)\s*=\s*(\w+)\((.*)\);\s*$', text, re.M)}
    def ref(token): return entities[int(token.removeprefix('#'))]
    def refs(token): return fields(token[1:-1])
    counts = Counter(kind for kind, _ in entities.values() if kind in TYPES)
    assert sum(counts.values()) == 295
    assert entities[15][1][1:] == ['.LENGTHUNIT.','$','.METRE.']
    assert entities[16][1][1:] == ['.AREAUNIT.','$','.SQUARE_METRE.']
    hosts = {args[4] for kind, args in entities.values() if kind == 'IFCRELVOIDSELEMENT'}
    prisms = []
    for eid, (kind, args) in entities.items():
        if kind not in TYPES or args[6] == '$' or '#'+str(eid) in hosts: continue
        shape_kind, shape = ref(args[6]); assert shape_kind == 'IFCPRODUCTDEFINITIONSHAPE'
        bodies = [ref(r)[1] for r in refs(shape[2]) if ref(r)[1][1] == "'Body'"]
        if len(bodies) != 1: continue
        items = refs(bodies[0][3])
        if len(items) != 1: continue
        item_kind, item = ref(items[0])
        if item_kind != 'IFCEXTRUDEDAREASOLID': continue
        profile_kind, profile = ref(item[0])
        if profile_kind != 'IFCRECTANGLEPROFILEDEF': continue
        direction = [Decimal(x) for x in refs(ref(item[2])[1][0])]
        if direction != [0,0,1]: continue
        a,b,h = map(Decimal, (profile[3],profile[4],item[3]))
        prisms.append({'id':eid, 'source_extrusion_id':int(items[0][1:]),
                       'volume_m3':float(a*b*h),'surface_area_m2':float(2*(a*b+a*h+b*h))})
    quantities = {i:float(Decimal(args[3])) for i,(kind,args) in entities.items() if kind == 'IFCQUANTITYAREA'}
    assert len(quantities) == 21 and len(prisms) > 90
    spatial = {eid:[] for eid,(kind,_) in entities.items() if kind in TYPES}
    for rid,(kind,args) in entities.items():
        if kind in {'IFCRELAGGREGATES','IFCRELNESTS'}:
            parent,children=args[4],refs(args[5])
        elif kind == 'IFCRELCONTAINEDINSPATIALSTRUCTURE':
            parent,children=args[5],refs(args[4])
        else: continue
        for child in children:
            child_id=int(child[1:])
            if child_id in spatial:
                spatial[child_id].append((rid,kind,int(parent[1:])))
    return counts, prisms, quantities, spatial


def main():
    source, output = map(Path, sys.argv[1:3])
    data = source.read_bytes(); assert hashlib.sha256(data).hexdigest() == SHA, 'Unexpected reference bytes'
    output.mkdir(parents=True, exist_ok=False)
    expected_counts, prisms, quantities, spatial = raw_oracle(data.decode('utf-8-sig'))
    start = time.perf_counter()
    with TestClient(create_app(output/'runtime', start_worker=False)) as client:
        r = client.post('/api/auth/register', json={'username':'ifc_reference_test','password':'Reference-local-test-2026!','display_name':'IFC reference'})
        assert r.status_code == 200, r.text
        client.headers['X-CSRF-Token'] = r.json()['csrf_token']
        r = client.post('/api/projects', json={'name':'Public Duplex IFC reference', 'data_nature':'engineering_reference',
                        'building':{'use':'reference','location':'Public model, not field measurements','region':'reference',
                                    'area_m2':1}}); assert r.status_code == 201, r.text
        pid = r.json()['project_id']; base = f'/api/projects/{pid}'
        r = client.post(base+'/files', files={'file':('duplex.ifc',data)}); assert r.status_code == 201, r.text
        r = client.post(base+'/cad-inspections',json={'file_id':r.json()['file_id']}); assert r.status_code == 201, r.text
        record = r.json(); (output/'api.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    result = record['result']
    assert {k.upper():v for k,v in result['counts'].items()} == expected_counts
    geometry = {x['id']:x for x in result['ifc_geometry']['objects']}
    checks = []
    for expected in prisms:
        row = geometry[expected['id']]
        match = all(row[k] is not None and math.isclose(row[k],expected[k],rel_tol=1e-8,abs_tol=1e-10) for k in ('volume_m3','surface_area_m2'))
        checks.append({**expected,'actual_volume_m3':row['volume_m3'],'actual_area_m2':row['surface_area_m2'],'match':match})
    actual_q = {q['source_id']:q for e in result['objects'] for q in e['quantities']}
    spatial_checks = [{'id':e['id'],'match':sorted((r['relation_id'],r['relation_type'].upper(),r['parent_id'])
                       for r in e['spatial_relations']) == sorted(spatial[e['id']])} for e in result['objects']]
    quantity_checks = [{'id':i,'expected':v,'actual':actual_q.get(i,{}).get('value_si'),
                        'match':i in actual_q and actual_q[i]['value_si'] == v} for i,v in quantities.items()]
    summary = {'sha256':SHA,'seconds':time.perf_counter()-start,'products':sum(expected_counts.values()),
               'prism_checks':checks,'quantity_checks':quantity_checks,'spatial_checks':spatial_checks,
               'geometry_status':dict(Counter(x['status'] for x in geometry.values())),
               'boundary':'Prism subset and declared area values only; other geometry not independently verified.'}
    (output/'independent.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    assert len(actual_q) == len(quantities) and all(x['match'] for x in checks+quantity_checks+spatial_checks), 'Independent mismatch; outputs retained'
    print(json.dumps({'products':summary['products'],'matched_prisms':len(checks),'matched_quantities':len(quantity_checks),
                      'matched_spatial_relations':len(spatial_checks),'seconds':summary['seconds']}))


if __name__ == '__main__':
    main()
