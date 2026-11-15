"""Local PSPLIB evaluation references only; no product solver and no redistribution."""
import hashlib,io,json,re,zipfile
from datetime import datetime,timezone
from pathlib import Path
import httpx
root=Path(__file__).parent/'public-reference';root.mkdir(exist_ok=False)
urls={'library.html':'https://www.om-db.wi.tum.de/psplib/library.php',
 'datasets.html':'https://www.om-db.wi.tum.de/psplib/getdata.php?mode=sm',
 'j30.zip':'https://www.om-db.wi.tum.de/psplib/download_dataset.php?format=zip&mode=sm&set=j30',
 'j30-opt.txt':'https://www.om-db.wi.tum.de/psplib/download_solution.php?mode=sm&set=j30&type=opt'}
receipt={'retrieved_utc':datetime.now(timezone.utc).isoformat(),'sources':{},'scope':'Research evaluation permitted by the official library page; raw archive retained locally, redistribution not inferred','product_solver_run':False}
with httpx.Client(timeout=40,follow_redirects=True) as c:
 for name,url in urls.items():
  chunks=[];size=0
  with c.stream('GET',url) as response:
   response.raise_for_status()
   for block in response.iter_bytes():
    size+=len(block)
    if size>10*1024*1024:raise ValueError('Source exceeds bounded download')
    chunks.append(block)
  data=b''.join(chunks);(root/name).write_bytes(data)
  receipt['sources'][name]={'url':url,'final_url':str(response.url),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
  print('Downloaded',name,len(data),flush=True)
with zipfile.ZipFile(io.BytesIO((root/'j30.zip').read_bytes())) as archive:
 names=[n for n in archive.namelist() if re.fullmatch(r'j30[0-9]+_[0-9]+\.sm',n)]
 assert len(names)==480,len(names)
 chosen=sorted(names,key=lambda n:hashlib.sha256(('vra-resource-leveling-20261115|'+n).encode()).hexdigest())[:6]
 optimum={}
 for line in (root/'j30-opt.txt').read_text(encoding='utf-8').splitlines():
  m=re.fullmatch(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+[0-9.]+\s*',line)
  if m:optimum[(int(m[1]),int(m[2]))]=int(m[3])
 assert len(optimum)==480
 rows=[]
 for name in chosen:
  info=archive.getinfo(name);assert info.file_size<100000
  data=archive.read(name);(root/name).write_bytes(data)
  m=re.fullmatch(r'j30(\d+)_(\d+)\.sm',name)
  rows.append({'file':name,'sha256':hashlib.sha256(data).hexdigest(),'published_optimum':optimum[(int(m[1]),int(m[2]))]})
receipt.update(selection='first six ascending sha256 of vra-resource-leveling-20261115|filename, from all 480 official j30 instances; fixed before product solver',cases=rows,
 acceptance='Independently verify every resource/time/precedence constraint and report gap to reference; deterministic feasible schedule is not claimed optimal; no outcome-based exclusions')
(root/'frozen-public-reference.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_cases':rows,'product_solver_run':False}))
