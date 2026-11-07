import json,os,shutil,subprocess,sys
from pathlib import Path
assert os.getuid()==65534
out=Path(__file__).resolve().parent
root=Path(json.loads((out/'linux-source-v1.json').read_text())['root'])
dest=root/'public-reference-v1'
env=dict(os.environ,VRA_DATA_DIR=str(root/'public-bootstrap-v2'),PYTHONDONTWRITEBYTECODE='1')
with (out/'public-linux-v2.log').open('xb') as log:
    cp=subprocess.run([sys.executable,'-B','-X','utf8','scripts/verify_ifc_reference.py','/mnt/d/稀土agent-稀土制暖全流程/vra-trust/validation/ifc-20261105/duplex.ifc',str(dest)],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
copy=out/'public-linux-v2';copy.mkdir()
for name in ['api.json','independent.json']:
    if (dest/name).exists():shutil.copyfile(dest/name,copy/name)
with (out/'public-linux-checks-v2.json').open('x',encoding='utf-8') as f:json.dump({'exit_code':cp.returncode,'native_output':str(dest),'uid':os.getuid(),'prior_failure':'Windows-mounted output did not satisfy original storage permissions; retained v1'},f,indent=2)
raise SystemExit(cp.returncode)
