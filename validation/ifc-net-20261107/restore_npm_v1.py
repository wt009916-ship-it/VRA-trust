import base64,hashlib,io,json,tarfile,tempfile,urllib.request,uuid
from pathlib import Path
out=Path(__file__).resolve().parent
meta=json.load(urllib.request.urlopen('https://registry.npmjs.org/npm/11.6.2',timeout=30))
url=meta['dist']['tarball']
assert url=='https://registry.npmjs.org/npm/-/npm-11.6.2.tgz'
raw=urllib.request.urlopen(url,timeout=30).read()
assert meta['dist']['integrity']=='sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode()
root=Path(tempfile.gettempdir())/('vra-npm-'+uuid.uuid4().hex);root.mkdir()
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
    tar.extractall(root,filter='data')
record={'root':str(root),'version':meta['version'],'sha512':meta['dist']['integrity'],'source':url}
with (out/'npm-runtime-v1.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(str(root/'package/bin/npm-cli.js'))
