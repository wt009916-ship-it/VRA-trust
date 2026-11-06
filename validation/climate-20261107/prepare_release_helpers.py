"""Preparation only: no GitHub mutation or service stop/start."""
from pathlib import Path
out=Path(__file__).resolve().parent;old=out.parent/'ifc-topology-20261107'
for name in ['capture_remote.py','merge_release.py','ui_graceful_stop.py','ui_launch.py','release_assets.py','verify_served_assets.py','inspect_runtime.py']:
    text=(old/name).read_text(encoding='utf-8').replace('ifc-topology-20261107','climate-20261107')
    if name=='merge_release.py':text=text.replace('cd6a7f77e0ef0fb36926871be752da58e7da2f81','7504d8cb450f551581698b7c4094e013e3530761')
    if name=='ui_graceful_stop.py':text=text.replace('11660','9552').replace('21832','71168')
    if name=='release_assets.py':
        text=text.replace('release-final/windows-source.json','windows-source-v2.json')
        text=text.replace("Path(json.loads((base/'browser-prepared.json').read_text())['dist'])", "Path(json.loads((base/'browser-prepared-v2.json').read_text())['source'])/'frontend/dist'")
    if name=='inspect_runtime.py':text=text.replace('browser-runtime-receipt.json','browser-runtime-v2.json')
    (out/name).write_text(text,encoding='utf-8',newline='\n')
print('Prepared helpers; no service or remote mutation')
