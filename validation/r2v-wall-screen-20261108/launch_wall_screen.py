from pathlib import Path
import subprocess,json,time
root=Path(__file__).parent
start=time.monotonic()
with (root/'wall-screen.log').open('x',encoding='utf-8') as log:
 try:
  result=subprocess.run(['C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108/vision-venv/Scripts/python.exe','-B','-u','-X','utf8',str(root/'run_wall_screen.py')],stdout=log,stderr=subprocess.STDOUT,timeout=240)
  receipt={'exit_code':result.returncode,'timeout':False,'seconds':time.monotonic()-start}
 except subprocess.TimeoutExpired:
  receipt={'exit_code':None,'timeout':True,'seconds':time.monotonic()-start}
(root/'wall-screen-process.json').write_text(json.dumps(receipt),encoding='utf-8')
print(json.dumps(receipt))
if (root/'wall-screen/result.json').exists():
 result=json.loads((root/'wall-screen/result.json').read_text());print(json.dumps({k:result[k] for k in ('summary','gates','wall_screen_passed','seconds')}))
else: print((root/'wall-screen.log').read_text()[-2500:])
