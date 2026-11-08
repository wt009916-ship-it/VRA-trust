from pathlib import Path
from urllib.request import Request,urlopen
from hashlib import sha256,sha1
import json

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
meta=json.loads((ROOT/'acquisition-metadata.json').read_text())
base=f'https://huggingface.co/{meta["model_id"]}/resolve/{meta["model_revision"]}'
headers={'User-Agent':'VRA-Trust-public-reference-evaluation/1.0'}
url=f'https://huggingface.co/api/models/{meta["model_id"]}/revision/{meta["model_revision"]}?blobs=true'
with urlopen(Request(url,headers=headers),timeout=90) as r:info=json.load(r)
assert info['sha']==meta['model_revision']
directory=ROOT/'florence-model'
directory.mkdir(exist_ok=False)
(ROOT/'model-remote-manifest.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
rows=[]
for row in info['siblings']:
    name=row['rfilename']
    if name=='.gitattributes':continue
    assert '/' not in name and (name.endswith(('.json','.txt','.safetensors','.md')))
    assert 0 < row['size'] <= 700_000_000
    path=directory/name;digest=sha256();blob=sha1(f'blob {row["size"]}\0'.encode());size=0
    print('Downloading '+name,flush=True)
    with urlopen(Request(f'{base}/{name}',headers=headers),timeout=120) as r,path.with_suffix(path.suffix+'.part').open('xb') as out:
        while chunk:=r.read(1024*1024):
            size+=len(chunk);assert size<=row['size']
            digest.update(chunk);blob.update(chunk);out.write(chunk)
    assert size==row['size']
    if row.get('lfs'):assert digest.hexdigest()==row['lfs']['sha256']
    else:assert blob.hexdigest()==row['blobId']
    path.with_suffix(path.suffix+'.part').rename(path)
    rows.append({'file':name,'size':size,'sha256':digest.hexdigest(),'source':f'{base}/{name}'})
    (ROOT/'model-download.json').write_text(json.dumps({'model':meta['model_id'],'revision':meta['model_revision'],'files':rows},indent=2),encoding='utf-8')
print('Pinned safetensors and tokenizer downloaded; no model code downloaded/executed',flush=True)
