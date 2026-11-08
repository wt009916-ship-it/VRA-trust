from pathlib import Path
from urllib.request import Request,urlopen
from hashlib import sha256,sha1
import json,shutil

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
meta=json.loads((ROOT/'acquisition-metadata.json').read_text())
info=json.loads((ROOT/'model-remote-manifest.json').read_text())
directory=ROOT/'florence-model'
base=f'https://huggingface.co/{meta["model_id"]}/resolve/{meta["model_revision"]}'
rows=[]
for row in info['siblings']:
    name=row['rfilename']
    if name=='.gitattributes':continue
    assert '/' not in name and name.endswith(('.json','.txt','.safetensors','.md'))
    target=directory/name
    expected=row.get('lfs',{}).get('sha256')
    if not target.exists():
        first=target.with_suffix(target.suffix+'.part')
        start=first.stat().st_size if first.exists() else 0
        headers={'User-Agent':'VRA-Trust-public-reference-evaluation/1.0'}
        if start:headers['Range']=f'bytes={start}-'
        temporary=target.with_suffix(target.suffix+'.attempt2')
        assert not temporary.exists()
        with urlopen(Request(f'{base}/{name}?download=true',headers=headers),timeout=120) as response:
            print(json.dumps({'file':name,'resume_offset':start,'status':response.status,'content_range':response.headers.get('Content-Range')}),flush=True)
            if start:
                failure={'file':name,'expected_bytes':row['size'],'received_bytes':start,'sha256_partial':sha256(first.read_bytes()).hexdigest(),
                         'failure':'First download ended before declared size; not loaded as a model','retry_status':response.status}
                (ROOT/'model-download-first-failure.json').write_text(json.dumps(failure,indent=2),encoding='utf-8')
            if response.status==206:
                assert start and response.headers.get('Content-Range','').startswith(f'bytes {start}-')
                shutil.copyfile(first,temporary);mode='ab';size=start
            else:
                assert response.status==200
                mode='xb';size=0
            with temporary.open(mode) as out:
                while chunk:=response.read(1024*1024):
                    size+=len(chunk);assert size<=row['size'];out.write(chunk)
        assert size==row['size']
        payload=temporary.read_bytes()
        if expected:assert sha256(payload).hexdigest()==expected
        else:assert sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()==row['blobId']
        temporary.rename(target)
    payload=target.read_bytes()
    assert len(payload)==row['size']
    if expected:assert sha256(payload).hexdigest()==expected
    else:assert sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()==row['blobId']
    rows.append({'file':name,'size':len(payload),'sha256':sha256(payload).hexdigest(),'source':f'{base}/{name}'})
    (ROOT/'model-download-complete.json').write_text(json.dumps({'model':meta['model_id'],'revision':meta['model_revision'],'files':rows},indent=2),encoding='utf-8')
print('Fixed-revision model complete and hash-verified; first partial preserved',flush=True)
