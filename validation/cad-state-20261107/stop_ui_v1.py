"""Graceful stop of a previously verified dedicated local test/prototype console."""
import ctypes as c,json,sqlite3,subprocess,sys
from ctypes import wintypes as w
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1];which=sys.argv[1]
assert which == 'isolated'
if which=='isolated':
    plan=json.loads((out/'ui-runtime-v1.json').read_text());parent,child,port=1012,45952,18774
    assert plan['launcher_pid']==parent and plan['port']==port
    data=Path(plan['data'])
else:
    parent,child,port=26940,41608,18772
    data=Path(json.loads((out/'runtime-context-v1.json').read_text())['prototype_data'])
command=f"[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-CimInstance Win32_Process -Filter 'ProcessId = {parent} OR ProcessId = {child}' | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"
processes=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-Command',command],creationflags=subprocess.CREATE_NO_WINDOW))
assert {p['ProcessId'] for p in processes}=={parent,child}
assert next(p for p in processes if p['ProcessId']==child)['ParentProcessId']==parent
assert all('uvicorn backend.api:app' in p['CommandLine'] and f'--port {port}' in p['CommandLine'] for p in processes)
with sqlite3.connect((data/'vra.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as con:
    assert con.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]==0
    for body, in con.execute("SELECT body FROM records r WHERE kind IN ('agent','search') AND revision=(SELECT MAX(revision) FROM records s WHERE s.kind=r.kind AND s.id=r.id)"):
        assert json.loads(body).get('status') not in {'queued','running'}
k=c.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.WaitForSingleObject.restype=w.DWORD
k.GetExitCodeProcess.argtypes=[w.HANDLE,c.POINTER(w.DWORD)];k.CloseHandle.argtypes=[w.HANDLE]
handle=k.OpenProcess(0x100000|0x1000,False,parent);assert handle
k.FreeConsole();assert k.AttachConsole(parent)
try:
    ids=(w.DWORD*32)();count=k.GetConsoleProcessList(ids,32)
    assert set(ids[:count])=={parent,child,k.GetCurrentProcessId()}
    assert k.SetConsoleCtrlHandler(None,True) and k.GenerateConsoleCtrlEvent(0,0)
    assert k.WaitForSingleObject(handle,30000)==0,'Graceful shutdown incomplete; no force kill'
    code=w.DWORD();assert k.GetExitCodeProcess(handle,c.byref(code))
    record={'which':which,'parent_pid':parent,'child_pid':child,'port':port,'method':'CTRL_C to verified dedicated console','forced_kill':False,'exit_code':code.value}
    with (out/(which+'-stopped-v1.json')).open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
finally:k.FreeConsole();k.CloseHandle(handle)
print(json.dumps(record))
