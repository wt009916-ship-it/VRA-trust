from pathlib import Path
import json, hashlib, urllib.request, datetime, time
root=Path(__file__).parent
revision='929e7a309e300fbf1d8c77fb2277e5744cdca43e'
files=['LICENSE','pytorch/README.md','pytorch/requirements.txt','pytorch/models/model.py','pytorch/models/drn.py','pytorch/models/modules.py','pytorch/utils.py','pytorch/datasets/floorplan_dataset.py','pytorch/options.py']
receipt={'revision':revision,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{},'weight_license':'not separately verified; research preflight only; not redistribution','inference_ran':False}
try:
 for name in files:
  url='https://raw.githubusercontent.com/art-programmer/FloorplanTransformation/'+revision+'/'+name
  with urllib.request.urlopen(url,timeout=30) as response: data=response.read(1000000)
  target=root/'upstream'/name
  target.parent.mkdir(exist_ok=True,parents=True)
  target.write_bytes(data)
  receipt['files'][name]={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
 url='https://drive.usercontent.google.com/download?id=1e5c7308fdoCMRv0w-XduWqyjYPV4JWHS&export=download&confirm=t'
 req=urllib.request.Request(url,headers={'User-Agent':'VRA-public-reference-preflight/1.0'})
 total=0; digest=hashlib.sha256(); start=time.monotonic()
 with urllib.request.urlopen(req,timeout=45) as response:
  receipt['weight_response']={'status':response.status,'content_type':response.headers.get('Content-Type'),'content_length':response.headers.get('Content-Length')}
  if 'text/' in response.headers.get('Content-Type',''): raise ValueError('Download returned text, not a checkpoint')
  with (root/'checkpoint.pth.partial').open('xb') as out:
   while True:
    chunk=response.read(1024*1024)
    if not chunk: break
    total+=len(chunk)
    if total>350*1024*1024 or time.monotonic()-start>240: raise ValueError('Download budget exceeded')
    out.write(chunk);digest.update(chunk)
  if response.headers.get('Content-Length') and total!=int(response.headers['Content-Length']): raise ValueError('Incomplete download')
  if total<1000000: raise ValueError('Unexpectedly small checkpoint')
 (root/'checkpoint.pth.partial').rename(root/'checkpoint.pth')
 receipt['weight']={'bytes':total,'sha256':digest.hexdigest(),'seconds':time.monotonic()-start,'upstream_expected_hash':None}
except Exception as exc:
 receipt['error']=type(exc).__name__+': '+str(exc)
finally:
 receipt['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (root/'acquisition.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 print(json.dumps(receipt),flush=True)
