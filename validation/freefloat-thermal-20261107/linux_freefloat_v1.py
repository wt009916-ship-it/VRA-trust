import json,os,runpy,shutil,uuid
from pathlib import Path
assert os.getuid()==65534
out=Path(__file__).resolve().parent;repo=out.parents[1]
root=Path(json.loads((repo/'validation/dynamic-thermal-20261107/linux-source-v1.json').read_text())['root'])
ctx=json.loads((repo/'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
os.environ['ENERGYPLUS_EXE']=ctx['engine']
script=root/'scripts/verify_freefloat_thermal.py'
assert not script.exists()
shutil.copyfile(repo/'scripts/verify_freefloat_thermal.py',script)
inputs=Path('/mnt/c/Users/18483/AppData/Local/Temp/vra-freefloat-20fdb6d2532d4df98e0efe23b2e1da4e')
output=root/('freefloat-'+uuid.uuid4().hex)
receipt=runpy.run_path(str(script))['run'](inputs,output)
(out/'linux-v1.json').write_text(json.dumps({'root':str(output),'uid':os.getuid(),**receipt},indent=2))
