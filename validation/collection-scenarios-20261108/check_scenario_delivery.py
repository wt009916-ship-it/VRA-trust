from pathlib import Path
import subprocess,sys,os,json
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-collection-scenarios-public-20261108')
commands=[('frontend-all',['node','--test','tests/*.test.js','legacy/tests/*.test.js'],R/'frontend'),
          ('ruff',[sys.executable,'-m','ruff','check','backend','tests'],R),
          ('contract',[sys.executable,'-B','scripts/export_contract.py'],R)]
for name,args,cwd in commands:
    cp=subprocess.run(args,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',env={**os.environ,'VRA_DATA_DIR':str(OUT/'contract-private'),'PYTHONDONTWRITEBYTECODE':'1'})
    (OUT/(name+'.log')).write_text(cp.stdout+cp.stderr,encoding='utf-8')
    print(json.dumps({'check':name,'exit_code':cp.returncode,'tail':(cp.stdout+cp.stderr)[-1100:]}),flush=True)
    if cp.returncode:sys.exit(cp.returncode)
for path in (R/'shared/schemas').glob('*.json'):
    if path.name=='openapi.json':continue
    old=subprocess.check_output(['git','show','HEAD:'+path.relative_to(R).as_posix()],cwd=R)
    if old.replace(b'\r\n',b'\n')==path.read_bytes().replace(b'\r\n',b'\n'):path.write_bytes(old)
