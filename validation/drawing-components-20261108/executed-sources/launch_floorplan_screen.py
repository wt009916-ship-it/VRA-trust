from pathlib import Path
import subprocess,json,time
root=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
assert not (root/'florence-screen').exists()
start=time.perf_counter()
with (root/'florence-screen.log').open('x',encoding='utf-8') as out:
    try:
        process=subprocess.run([str(root/'vision-venv/Scripts/python.exe'),'-B','-u','-X','utf8',str(Path(__file__).parent/'run_floorplan_screen.py')],
                               stdout=out,stderr=subprocess.STDOUT,timeout=1800)
        result={'exit_code':process.returncode,'seconds':time.perf_counter()-start,'timeout':False}
    except subprocess.TimeoutExpired:
        result={'exit_code':None,'seconds':time.perf_counter()-start,'timeout':True}
(root/'screen-process.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
