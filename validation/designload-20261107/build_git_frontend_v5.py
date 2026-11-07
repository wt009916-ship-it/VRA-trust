import hashlib, json, subprocess
from pathlib import Path
repo=Path.cwd(); out=Path(__file__).parent
record=json.loads((out/'git-source-v3.json').read_text()); root=Path(record['root'])
assert root.name.startswith('vra-git-designload-')
front=root/'frontend'; assert not (front/'node_modules').exists()
quote=lambda value: chr(39)+str(value).replace(chr(39),chr(39)*2)+chr(39)
command='New-Item -ItemType Junction -Path '+quote(front/'node_modules')+' -Target '+quote(repo/'frontend/node_modules')+' | Out-Null'
p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True)
assert p.returncode==0,p.stderr.decode(errors='replace')
with (out/'git-build-v5.log').open('xb') as log:
    p=subprocess.run(['node',str(repo/'frontend/node_modules/vite/bin/vite.js'),'build'],cwd=front,stdout=log,stderr=subprocess.STDOUT)
assert p.returncode==0
browser=json.loads((out/'browser-prepared-v2.json').read_text())
accepted=Path(browser['source'])/'frontend/dist'; built=front/'dist'
hashes={str(p.relative_to(built)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in built.rglob('*') if p.is_file()}
expected={str(p.relative_to(accepted)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in accepted.rglob('*') if p.is_file()}
assert hashes==expected,'Git-built assets differ from accepted browser bytes'
with (out/'git-assets-v5.json').open('x',encoding='utf-8') as handle:
    json.dump({'candidate':record['candidate'],'root':str(root),'assets':hashes,'same_as_browser_tested_bytes':True,
               'normalized_source_files':record['normalizations']},handle,indent=2)
print(json.dumps({'files':len(hashes),'same_as_browser':True}))
