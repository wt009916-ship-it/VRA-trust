"""Signal only the verified dedicated prototype console; never force termination."""
import ctypes as c, json, sqlite3
from ctypes import wintypes as w
from pathlib import Path

out = Path(__file__).parent
db = Path('validation/thermal-20261104/ui-runtime/vra.sqlite3').resolve()
with sqlite3.connect('file:' + db.as_posix() + '?mode=ro', uri=True) as con:
    assert con.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0] == 0
    for body, in con.execute("SELECT body FROM records r WHERE kind IN ('agent','search') AND revision=(SELECT MAX(revision) FROM records s WHERE s.kind=r.kind AND s.id=r.id)"):
        assert json.loads(body).get('status') not in {'queued', 'running'}, 'Active original task; do not stop'
k = c.WinDLL('kernel32', use_last_error=True)
k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; k.WaitForSingleObject.restype = w.DWORD
k.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
k.CloseHandle.argtypes = [w.HANDLE]
handle = k.OpenProcess(0x100000 | 0x1000, False, 40380)
assert handle
k.FreeConsole(); assert k.AttachConsole(40380)
try:
    ids = (w.DWORD * 32)(); count = k.GetConsoleProcessList(ids, 32)
    assert set(ids[:count]) == {40380, 56268, k.GetCurrentProcessId()}, list(ids[:count])
    assert k.SetConsoleCtrlHandler(None, True)
    assert k.GenerateConsoleCtrlEvent(0, 0)
    assert k.WaitForSingleObject(handle, 30000) == 0, 'Graceful shutdown incomplete; no forced kill'
    code = w.DWORD(); assert k.GetExitCodeProcess(handle, c.byref(code))
    data = {'server_pid': 40380, 'child_pid': 56268, 'exit_code': code.value,
            'method': 'CTRL_C to verified dedicated console', 'forced_kill': False}
    with (out / 'ui-graceful-stop.json').open('x', encoding='utf-8') as stream:
        json.dump(data, stream)
finally:
    k.FreeConsole(); k.CloseHandle(handle)
print(json.dumps(data))
