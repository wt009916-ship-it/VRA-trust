"""Windows-only native restricted-token read probe in a disposable child process."""
import ctypes as c
import json
import sys
from ctypes import wintypes as w
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.private_storage import _windows

_,_,adv,kernel=_windows()
class SidAttributes(c.Structure):
    _fields_=[('sid',c.c_void_p),('attributes',w.DWORD)]
adv.ConvertStringSidToSidW.argtypes=[w.LPCWSTR,c.POINTER(c.c_void_p)];adv.ConvertStringSidToSidW.restype=w.BOOL
adv.CreateRestrictedToken.argtypes=[w.HANDLE,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,c.c_void_p,w.DWORD,c.c_void_p,c.POINTER(w.HANDLE)]
adv.CreateRestrictedToken.restype=w.BOOL
adv.ImpersonateLoggedOnUser.argtypes=[w.HANDLE];adv.ImpersonateLoggedOnUser.restype=w.BOOL
adv.RevertToSelf.argtypes=[];adv.RevertToSelf.restype=w.BOOL
token,restricted=w.HANDLE(),w.HANDLE()
everyone=c.c_void_p()
private,control=Path(sys.argv[1]),Path(sys.argv[2])
assert private.read_bytes()==b'private probe' and control.read_bytes()==b'public probe'
try:
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(),0xE,c.byref(token)):raise c.WinError(c.get_last_error())
    if not adv.ConvertStringSidToSidW('S-1-1-0',c.byref(everyone)):raise c.WinError(c.get_last_error())
    restrict=SidAttributes(everyone,0)
    # DISABLE_MAX_PRIVILEGE only. Never SANDBOX_INERT or policy weakening.
    if not adv.CreateRestrictedToken(token,1,0,None,0,None,1,c.byref(restrict),c.byref(restricted)):
        raise c.WinError(c.get_last_error())
    if not adv.ImpersonateLoggedOnUser(restricted):raise c.WinError(c.get_last_error())
    try:
        allowed=control.read_bytes()==b'public probe'
        try:private.read_bytes();denied=False
        except PermissionError:denied=True
    finally:
        if not adv.RevertToSelf():raise c.WinError(c.get_last_error())
    assert allowed and denied
    print(json.dumps({'control_read_allowed':allowed,'private_read_denied':denied,'identity':'restricted_current_token_with_Everyone_restriction','separate_physical_account_test':False}))
finally:
    if everyone.value:kernel.LocalFree(everyone)
    if restricted.value:kernel.CloseHandle(restricted)
    if token.value:kernel.CloseHandle(token)
