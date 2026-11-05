"""Small isolated OS budget probes; never imported into the application."""
import json
import mmap
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import worker_limits

mode=sys.argv[1]
if mode=='startup_failure':
    def fail(*args):raise OSError('deliberate isolated initialization failure')
    worker_limits.apply_limits=fail
    worker_limits.initialize('cad')
    raise AssertionError('Parser must not be reached')

applied=worker_limits.apply_limits(128*1024**2,1 if mode=='cpu' else 5)
print(json.dumps({'installed':applied}),flush=True)
if mode=='memory':
    if sys.platform=='win32':
        import ctypes as c
        kernel=c.WinDLL('kernel32',use_last_error=True)
        kernel.VirtualAlloc.argtypes=[c.c_void_p,c.c_size_t,c.c_ulong,c.c_ulong];kernel.VirtualAlloc.restype=c.c_void_p
        kernel.VirtualFree.argtypes=[c.c_void_p,c.c_size_t,c.c_ulong];kernel.VirtualFree.restype=c.c_int
        block=kernel.VirtualAlloc(None,256*1024**2,0x3000,0x04)
        if block:
            kernel.VirtualFree(block,0,0x8000)
            raise AssertionError('Oversized native private allocation unexpectedly allowed')
        print(json.dumps({'allocation_denied':True,'winerror':c.get_last_error()}),flush=True)
    else:
        try:
            block=mmap.mmap(-1,256*1024**2)
        except (OSError,MemoryError) as exc:
            print(json.dumps({'allocation_denied':True,'error_type':type(exc).__name__}),flush=True)
        else:
            block.close();raise AssertionError('Oversized native mapping unexpectedly allowed')
elif mode=='mapping_gap':
    # Retain the real Windows counterexample: job private-commit limits do not
    # bound anonymous mappings. This is a known gap, not a successful rejection.
    try:
        block=mmap.mmap(-1,256*1024**2)
    except (OSError,MemoryError) as exc:
        print(json.dumps({'mapping_denied':True,'error_type':type(exc).__name__}),flush=True)
    else:
        block.close();print(json.dumps({'mapping_denied':False,'known_gap':True}),flush=True)
elif mode=='cpu':
    while True:
        pass
elif mode=='child':
    try:
        cp=subprocess.run([sys.executable,'-c','print("CHILD_EXECUTED")'],capture_output=True,timeout=3)
        assert cp.returncode!=0 and b'CHILD_EXECUTED' not in cp.stdout
    except OSError:
        pass
    print(json.dumps({'child_denied':True}),flush=True)
elif mode=='file':
    try:
        with Path(sys.argv[2]).open('wb') as stream:
            for _ in range(65):stream.write(b'x'*1024**2)
    except OSError:
        print(json.dumps({'file_growth_denied':True}),flush=True)
    else:raise AssertionError('Oversized file unexpectedly allowed')
elif mode!='normal':
    raise ValueError('Unknown probe mode')
