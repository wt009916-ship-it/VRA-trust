"""Check the exact candidate Git blob bytes, including CRLF normalization."""
import hashlib,io,json,subprocess,tarfile,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).parent
head=(out/'candidate-head.txt').read_text().strip()
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==head
snapshot=json.loads((out/'integration-source-v1.json').read_text());frozen=Path(snapshot['root'])
names=['backend','frontend/src','frontend/tests','frontend/index.html','frontend/package.json','frontend/package-lock.json','tests','fixtures','scripts','shared']
archive=subprocess.check_output(['git','archive','--format=tar',head,*names])
with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
 blobs={item.name:stream.extractfile(item).read() for item in stream.getmembers() if item.isfile()}
checks=[];normalizations=[]
for item in snapshot['files']:
 name=item['path']
 if name not in blobs:continue
 raw=(frozen/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==item['sha256']
 blob=blobs[name]
 if raw!=blob:
  assert name == 'frontend/src/main.js' or name.endswith('.json'),name
  assert raw.replace(b'\r\n',b'\n')==blob,name
  if name.endswith('.json'):assert json.loads(raw)==json.loads(blob)
  normalizations.append(name)
 checks.append({'path':name,'frozen_sha256':item['sha256'],'git_sha256':hashlib.sha256(blob).hexdigest()})
assert len(checks)>100
root=Path(tempfile.gettempdir())/('vra-git-designload-'+uuid.uuid4().hex);root.mkdir()
for name,raw in blobs.items():
 if not name.startswith('frontend/'):continue
 path=root/name;assert path.resolve().is_relative_to(root.resolve())
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
record={'candidate':head,'root':str(root),'checked_files':len(checks),'normalizations':normalizations,'files':checks}
with (out/'git-source-v2.json').open('x') as stream:json.dump(record,stream,indent=2)
print(json.dumps({k:v for k,v in record.items() if k!='files'}))
