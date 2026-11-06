import hashlib,json,urllib.request
from pathlib import Path
base=Path(__file__).resolve().parent
receipt=json.loads((base/'released-assets.json').read_text());checks=[]
for row in receipt['files']:
 path='/' if row['path']=='index.html' else '/'+row['path']
 with urllib.request.urlopen('http://127.0.0.1:18772'+path,timeout=10) as response:raw=response.read()
 assert hashlib.sha256(raw).hexdigest()==row['sha256'],path
 checks.append({'url_path':path,'sha256':row['sha256']})
(base/'served-assets-verified.json').write_text(json.dumps({'main':receipt['main'],'verified':checks},indent=2),encoding='utf-8')
print(json.dumps({'served_assets_verified':len(checks),'main':receipt['main']}))
