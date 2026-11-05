"""Independent ASCII group-code oracle for the pinned public LibreCAD symbol.

Usage: python scripts/verify_dxf_reference.py INPUT_DXF NEW_OUTPUT_DIRECTORY
Input is not redistributed or downloaded by this script. See DXF_GEOMETRY_DELIVERY.md.
"""
import hashlib
import json
import math
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.api import create_app

HASH='49ce8ea9f4c75d50c25229397f21f8e90e84da4a984cbb8505f8873bf9d1e9de'


def oracle(raw):
    lines=raw.decode('utf-8').splitlines();pairs=[(int(lines[i]),lines[i+1].strip()) for i in range(0,len(lines),2)]
    unit_index=pairs.index((9,'$INSUNITS'));assert pairs[unit_index+1]==(70,'4')
    start=pairs.index((2,'ENTITIES'))+1;entities=[]
    for code,value in pairs[start:]:
        if code==0 and value=='ENDSEC':break
        if code==0:entities.append({'type':value,'fields':{}})
        else:entities[-1]['fields'][code]=value
    expected=[]
    for e in entities:
        f=e['fields'];kind=e['type'];area=None
        if kind=='LINE':length=math.sqrt(sum((float(f.get(a,0))-float(f.get(b,0)))**2 for a,b in [(10,11),(20,21),(30,31)]))
        elif kind=='ARC':length=math.radians((float(f[51])-float(f[50]))%360)*float(f[40])
        elif kind=='ELLIPSE':
            a=math.sqrt(sum(float(f.get(k,0))**2 for k in [11,21,31]));b=a*float(f[40]);begin,end=float(f[41]),float(f[42]);sweep=end-begin
            assert sweep>0
            nodes,weights=np.polynomial.legendre.leggauss(128);angles=begin+(nodes+1)*sweep/2
            length=float(np.dot(weights,np.hypot(a*np.sin(angles),b*np.cos(angles)))*sweep/2)
            if math.isclose(sweep,2*math.pi):area=math.pi*a*b*1e-6
        else:raise ValueError('Unexpected entity in pinned reference; do not silently omit')
        expected.append(dict(handle=f[5],type=kind,length_m=length*.001,area_m2=area))
    return expected


def main():
    path,output=map(Path,sys.argv[1:3]);raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==HASH
    expected=oracle(raw);output.mkdir(parents=True,exist_ok=False)
    with TestClient(create_app(output/'runtime',start_worker=False)) as client:
        auth=client.post('/api/auth/register',json=dict(username='dxf_reference',display_name='Isolated reference audit',password='Reference-audit-only-2026!')).json();client.headers['X-CSRF-Token']=auth['csrf_token']
        project=client.post('/api/projects',json=dict(name='Public symbol, not real building',building=dict(use='reference',location='Public CAD symbol',region='reference',area_m2=1))).json()
        base='/api/projects/'+project['project_id'];fid=client.post(base+'/files',files={'file':('librecad-toilet.dxf',raw)}).json()['file_id']
        started=perf_counter();response=client.post(base+'/cad-inspections',json={'file_id':fid});elapsed=perf_counter()-started
        (output/'api.json').write_text(json.dumps(dict(status=response.status_code,record=response.json(),seconds=elapsed),ensure_ascii=False,indent=2),encoding='utf-8')
        assert response.status_code==201,response.text
        rows=response.json()['result']['geometry']['objects'];assert len(rows)==len(expected)
        for e in expected:
            row=next(r for r in rows if r['source_handle']==e['handle'])
            assert math.isclose(e['length_m'],row['length_m'],rel_tol=1e-9,abs_tol=1e-10)
            assert e['area_m2'] is None and row['area_m2'] is None or math.isclose(e['area_m2'],row['area_m2'],rel_tol=1e-9)
        (output/'independent.json').write_text(json.dumps(dict(sha256=HASH,expected=expected,matched=len(rows),seconds=elapsed),indent=2),encoding='utf-8')
        print(json.dumps(dict(matched=len(rows),seconds=elapsed)))


if __name__=='__main__':main()
