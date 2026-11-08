from pathlib import Path
from urllib.request import Request, urlopen
import json
import hashlib
import sys
import subprocess
import os

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
ROOT.mkdir(exist_ok=True)

def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'VRA-Trust-public-reference-evaluation/1.0'}),timeout=90) as r:
        return r.read()

def get_json(url):
    return json.loads(fetch(url))

commit=get_json('https://api.github.com/repos/m-agour/ResPlan/commits/main')['sha']
tree=get_json(f'https://api.github.com/repos/m-agour/ResPlan/git/trees/{commit}')['tree']
model=get_json('https://huggingface.co/api/models/florence-community/Florence-2-base-ft')
metadata={'resplan_commit':commit,'resplan_files':[{k:r[k] for k in ('path','type','sha','size') if k in r} for r in tree],
          'model_id':model['id'],'model_revision':model['sha'],'model_files':[r['rfilename'] for r in model['siblings']],
          'model_license':model.get('cardData',{}).get('license'),
          'purpose':'fixed small evaluation only; no training; not application deployment'}
path=ROOT/'acquisition-metadata.json'
assert not path.exists()
path.write_text(json.dumps(metadata,indent=2),encoding='utf-8')
for name in ['README.md','LICENSE','split.json']:
    data=fetch(f'https://raw.githubusercontent.com/m-agour/ResPlan/{commit}/{name}')
    (ROOT/('resplan-'+name)).write_bytes(data)
for name in ['config.json','README.md']:
    data=fetch(f'https://huggingface.co/{model["id"]}/resolve/{model["sha"]}/{name}')
    (ROOT/('florence-'+name)).write_bytes(data)
print(json.dumps(metadata),flush=True)
venv=ROOT/'vision-venv'
assert not venv.exists()
subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
python=venv/'Scripts/python.exe'
env=os.environ.copy();env['PIP_DISABLE_PIP_VERSION_CHECK']='1';env['PYTHONUNBUFFERED']='1'
for name,args in [
    ('torch',['torch==2.10.0','torchvision==0.25.0','--index-url','https://download.pytorch.org/whl/cu128']),
    ('transformers',['transformers==4.57.3','Pillow==13.0.0'])]:
    print('Installing isolated '+name,flush=True)
    with (ROOT/f'install-{name}.log').open('w',encoding='utf-8') as out:
        subprocess.run([str(python),'-m','pip','install','--no-cache-dir','--progress-bar','off',*args],env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
with (ROOT/'vision-packages.txt').open('w',encoding='utf-8') as out:
    subprocess.run([str(python),'-m','pip','freeze'],stdout=out,check=True)
print('Isolated vision environment installed',flush=True)
