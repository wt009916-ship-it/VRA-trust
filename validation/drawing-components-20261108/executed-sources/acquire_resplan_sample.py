from pathlib import Path
from urllib.request import Request,urlopen
from hashlib import sha256,sha1
import json,zipfile,pickletools
from itertools import islice

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
meta=json.loads((ROOT/'acquisition-metadata.json').read_text())
splits=json.loads((ROOT/'resplan-split.json').read_text())
test=splits['test']
assert isinstance(test,list) and len(test)>8
ids=sorted(test,key=lambda x:sha256(('VRA-D08-v1:'+str(x)).encode()).hexdigest())[:8]
selection={'source_commit':meta['resplan_commit'],'split':'test','ids':ids,
           'selection':'first 8 after sorting canonical test IDs by SHA256(VRA-D08-v1:<id>), before decoding plans or inference',
           'nature':'rendered geometry reference; not original scans; not training',
           'source_label_limit':'publisher-derived geometry, not independent surveyed building truth',
           'split_sha256':sha256((ROOT/'resplan-split.json').read_bytes()).hexdigest()}
(ROOT/'selection-frozen.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
info=next(x for x in meta['resplan_files'] if x['path']=='ResPlan.zip')
target=ROOT/'ResPlan.zip'
assert not target.exists()
request=Request(f'https://raw.githubusercontent.com/m-agour/ResPlan/{meta["resplan_commit"]}/ResPlan.zip',headers={'User-Agent':'VRA-Trust-public-reference-evaluation/1.0'})
digest=sha256();blob=sha1(f'blob {info["size"]}\0'.encode());size=0
with urlopen(request,timeout=90) as response,target.with_suffix('.part').open('xb') as out:
    while chunk:=response.read(1024*1024):
        size+=len(chunk)
        assert size<=info['size']<=120_000_000
        digest.update(chunk);blob.update(chunk);out.write(chunk)
assert size==info['size'] and blob.hexdigest()==info['sha']
target.with_suffix('.part').rename(target)
with zipfile.ZipFile(target) as archive:
    members=[{'name':i.filename,'size':i.file_size,'compressed':i.compress_size} for i in archive.infolist()]
    print(json.dumps({'selected':ids,'archive_sha256':digest.hexdigest(),'members':members}),flush=True)
    candidates=[i for i in archive.infolist() if i.filename.endswith('.pkl')]
    assert len(candidates)==1 and candidates[0].file_size<600_000_000
    # Inspect the pickle instruction stream only. No constructors or pickle.load.
    raw=archive.read(candidates[0])
    (ROOT/'pickle-first-ops.json').write_text(json.dumps([
        {'op':op.name,'argument':f'<{len(arg)} bytes>' if isinstance(arg,bytes) else arg,'position':pos}
        for op,arg,pos in islice(pickletools.genops(raw),100)
    ],indent=2),encoding='utf-8')
    receipt={'size':size,'sha256':digest.hexdigest(),'git_blob':blob.hexdigest(),'members':members,
             'pickle_sha256':sha256(raw).hexdigest(),'pickle_executed':False}
    (ROOT/'resplan-download.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print('Public geometry acquired; pickle only inspected, not executed',flush=True)
